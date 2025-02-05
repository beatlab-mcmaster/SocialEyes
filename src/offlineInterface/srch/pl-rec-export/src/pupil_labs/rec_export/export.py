import json
import logging
import math
import pathlib
import re
import threading
import traceback
from collections import defaultdict
from itertools import chain
from typing import List, Optional

import click
import numpy as np
import pandas as pd
import rich
from more_itertools import pairwise
from rich.logging import RichHandler
from rich.progress import Progress, track
from rich.traceback import install

from pupil_labs.rec_export.explib.orientation import (
    OrientationEstimation,
    euler_from_quaternion,
)

from . import __version__
from .explib import neon
from .explib.blinks import detect_blinks_match_before_optic_flow
from .explib.calibration import InvisibleCalibration, NeonCalibration
from .explib.fixation_detector.invisible import detect_fixations_invisible
from .explib.fixation_detector.neon import detect_fixations_neon
from .explib.pi_recording import is_neon
from .explib.spherical_coordinates import cart_to_spherical, unproject_points

install(show_locals=False, suppress=[pd, click, rich])

FILE_PATTERN = re.compile(
    r"(PI world v1|Neon Scene Camera v1|gaze|worn|extimu) ps(?P<part>\d*)\.(raw|time|time_aux)"
)


@click.command()
@click.argument(
    "recordings",
    nargs=-1,
    type=click.Path(
        exists=True,
        writable=True,
        file_okay=False,
        dir_okay=True,
        path_type=pathlib.Path,
    ),
)
@click.option(
    "-e",
    "--export-folder",
    default="export",
    help="Relative export path",
    show_default="<recording>/export",
)
@click.option("-f", "--force", is_flag=True, help="Overwrite an existing export")
@click.option(
    "-v", "--verbose", count=True, help="Show more log messages (repeat for even more)"
)
@click.option("--blinks/--no-blinks", default=True)
@click.option("--fixations/--no-fixations", default=True)
@click.option("--pdb", is_flag=True, help="Run debugger on error")
def main(
    recordings: List[pathlib.Path],
    export_folder: str,
    force: bool,
    verbose: int,
    blinks: bool,
    fixations: bool,
    pdb: bool,
):
    try:
        click.echo(f"pl-rec-export version: {__version__}", err=True)
        _setup_logging(verbose_option_count=verbose)
        if not recordings:
            logging.error("No recordings provided")
            raise SystemExit(2)
        logging.info(f"Processing {len(recordings)} recordings")
        with Progress(transient=True) as progress:
            for rec in progress.track(
                recordings, description="Processing recordings..."
            ):
                process_recording(
                    rec, export_folder, force, progress, blinks, fixations
                )
    except Exception:
        if pdb:
            traceback.print_exc()
            import pdb

            pdb.post_mortem()
        else:
            raise


def process_recording(
    recording: pathlib.Path,
    export_folder: str,
    force: bool,
    progress: Optional[Progress] = None,
    blinks: bool = True,
    fixations: bool = True,
) -> None:
    if isinstance(recording, bytes):
        # Fix reported case of Click passing bytes instead of pathlib.Path
        recording = pathlib.Path(recording.decode("utf-8"))
    logging.info(f"Processing {recording.resolve()}")

    export_path = recording / export_folder
    if export_path.exists():
        if force:
            logging.warning(f"'{export_path}' exists. Overwriting.")
        else:
            logging.warning(
                f"'{export_path}' exists. No -f/--force provided. Skipping."
            )
            raise SystemExit(3)
    else:
        export_path.mkdir()

    logging.info(f"File list")
    for file in sorted(recording.iterdir()):
        logging.info(f"    {file.name.ljust(50)} - {file.stat().st_size}")

    try:
        info = json.loads((recording / "info.json").read_text())
    except json.JSONDecodeError:
        logging.exception("info.json not valid")
        return

    logging.info(f"Recording info")
    for key in [
        "start_time",
        "duration",
        "data_format_version",
        "gaze_offset",
        "pipeline_version",
        "scene_camera_serial_number",
        "module_serial_number",
    ]:
        logging.info(f"    {key.ljust(50)}: {info.get(key)}")

    blink_thread = threading.Thread(
        target=_process_blinks, args=(recording, export_path, progress)
    )
    fixation_thread = threading.Thread(
        target=_process_fixations, args=(recording, export_path, progress)
    )

    try:
        _process_events(recording, export_path)
        _process_template(recording, export_path)
        _process_gaze(recording, export_path)
        _process_imu(recording, export_path)
        _process_world(recording, export_path)
        if blinks:
            blink_thread.start()
        if fixations:
            fixation_thread.start()
        if blinks:
            blink_thread.join()
            fixation_thread.join()
    except FileNotFoundError:
        logging.exception(
            "Did not encounter expected files. "
            "An unmodified Invisible or Neon recording is required."
        )


def _process_template(recording: pathlib.Path, export_path: pathlib.Path) -> None:
    template_questions = json.loads((recording / "template.json").read_text())
    info = json.loads((recording / "info.json").read_text())
    template_responses = info["template_data"]
    assert (
        template_questions["id"] == template_responses["id"]
    ), "Template data is inconsistent"

    merged = {
        "name": template_questions["name"],
        "description": template_questions["description"],
        "template_id": template_questions["id"],
        "Q&A": [
            {
                "question": next(
                    item
                    for item in template_questions["items"]
                    if item["id"] == question_id
                ),
                "responses": responses,
            }
            for question_id, responses in template_responses["data"].items()
        ],
    }
    export_path /= "template.json"
    logging.info(f"Exporting template data to '{export_path}'")
    export_path.write_text(json.dumps(merged, indent=4))


def _process_events(recording: pathlib.Path, export_path: pathlib.Path) -> None:
    event_names = (recording / "event.txt").read_text().splitlines()
    event_timestamps = np.fromfile(recording / "event.time", dtype="<u8")

    export_path /= "events.csv"
    events = pd.DataFrame({"timestamp [ns]": event_timestamps, "name": event_names})
    events["type"] = "recording"
    logging.info(f"Exporting event data to '{export_path}'")
    events.to_csv(export_path, index=False)


def _process_gaze(recording: pathlib.Path, export_path: pathlib.Path) -> None:
    logging.debug(f"Processing gaze")
    files_raw = sorted(recording.glob("gaze ps*.raw"), key=_file_sorter_by_part)
    files_ts = sorted(recording.glob("gaze ps*.time"), key=_file_sorter_by_part)
    files_worn = sorted(recording.glob("worn ps*.raw"), key=_file_sorter_by_part)
    assert (
        len(files_raw) == len(files_ts) == len(files_worn) > 0
    ), f"Inconsistent number of files: {files_raw}, {files_ts}, {files_worn}"
    dfs = {
        raw.stem: _process_gaze_file(raw, ts, worn)
        for raw, ts, worn in zip(files_raw, files_ts, files_worn)
    }

    data = pd.concat(dfs.values(), keys=dfs.keys(), names=["file"]).reset_index("file")
    _calculate_gaze_directions(recording, data)

    export_path = export_path / "gaze.csv"
    logging.info(f"Exporting gaze to '{export_path}'")
    data.to_csv(export_path, index=False)


def _get_calibration(recording: pathlib.Path):
    metadata = json.loads((recording / "info.json").read_bytes())
    is_neon_recording = is_neon(recording)

    if is_neon_recording:
        serial = metadata.get("module_serial_number")
    else:
        serial = metadata.get("scene_camera_serial_number")
    calib_path = recording / "calibration.bin"
    if calib_path.exists():
        CalibrationClass = (
            NeonCalibration if is_neon_recording else InvisibleCalibration
        )
        return CalibrationClass.from_file(calib_path)

    if is_neon_recording:
        raise FileNotFoundError("could not find camera calibration file")

    serial = metadata["scene_camera_serial_number"]
    logging.warning(
        f"Could not find calibration file for {serial}. Fetching from cloud"
    )
    return InvisibleCalibration.from_cloud(serial)


def _calculate_gaze_directions(recording: pathlib.Path, gaze: pd.DataFrame):
    gaze["azimuth [deg]"] = None
    gaze["elevation [deg]"] = None

    try:
        camera = _get_calibration(recording)
    except Exception:
        logging.warning(f"Could not calculate spherical gaze direction. Skipping!")
        logging.debug(traceback.format_exc())
        return
    logging.info(f"Calculating spherical gaze directions...")
    gaze_3d = unproject_points(
        gaze[["gaze x [px]", "gaze y [px]"]],
        camera.scene_camera_matrix,
        camera.scene_distortion_coefficients,
    )
    _, elevation, azimuth = cart_to_spherical(gaze_3d)
    gaze["azimuth [deg]"] = azimuth
    gaze["elevation [deg]"] = elevation


def _process_gaze_file(
    raw: pathlib.Path, time: pathlib.Path, worn: pathlib.Path
) -> pd.DataFrame:
    coords = np.fromfile(raw, dtype="<f4").reshape((-1, 2))
    ts = np.fromfile(time, dtype="<u8")
    onoff = (np.fromfile(worn, dtype="<u1") / 255).astype(bool)
    is_consistent = coords.shape[0] == ts.shape[0] == onoff.shape[0]
    if not is_consistent:
        sample_numbers = {
            "gaze": coords.shape[0],
            "time": ts.shape[0],
            "worn": onoff.shape[0],
        }
        num_min_samples = min(sample_numbers.values())
        coords = coords[:num_min_samples, :]
        ts = ts[:num_min_samples]
        onoff = onoff[:num_min_samples]
        logging.warning(
            "Inconsistent sample numbers detected. Reducing to largest consistent "
            f"sample number: {num_min_samples}"
        )
        logging.debug(f"Inconsistent {sample_numbers=}")

    result = pd.DataFrame(
        {
            "timestamp [ns]": ts,
            "gaze x [px]": coords[:, 0],
            "gaze y [px]": coords[:, 1],
            "worn": onoff,
        }
    )
    result["fixation id"] = None
    result["blink id"] = None
    return result


def _process_imu(recording: pathlib.Path, export_path: pathlib.Path) -> None:
    logging.debug(f"Processing IMU")
    files_raw = sorted(recording.glob("extimu ps*.raw"), key=_file_sorter_by_part)
    files_ts = sorted(recording.glob("extimu ps*.time"), key=_file_sorter_by_part)
    assert len(files_raw) == len(
        files_ts
    ), f"Inconsistent number of files: {files_raw=}, {files_ts=}"

    if not files_raw:
        logging.warning("No IMU data found. Skipping.")
        return
    if is_neon(recording):
        process_imu_file = _process_neon_imu_file
    else:
        process_imu_file = _process_pi_imu_file

    dfs = {raw.stem: process_imu_file(raw, ts) for raw, ts in zip(files_raw, files_ts)}

    export_path = export_path / "imu.csv"
    logging.info(f"Exporting IMU to '{export_path}'")
    data = pd.concat(dfs.values(), keys=dfs.keys(), names=["file"]).reset_index("file")
    data.to_csv(export_path, index=False)


def _process_pi_imu_file(raw: pathlib.Path, time: pathlib.Path) -> pd.DataFrame:
    coords = np.fromfile(raw, dtype="<f4").reshape((-1, 6))
    ts = np.fromfile(time, dtype="<u8")
    assert coords.shape[0] == ts.shape[0], "Inconsistent IMU and time data"
    logging.debug(f"'{raw.stem}': {ts.shape[0]} data points")

    result = pd.DataFrame(
        {
            "timestamp [ns]": ts,
            "gyro x [deg/s]": coords[:, 0],
            "gyro y [deg/s]": coords[:, 1],
            "gyro z [deg/s]": coords[:, 2],
            "acceleration x [G]": coords[:, 3],
            "acceleration y [G]": coords[:, 4],
            "acceleration z [G]": coords[:, 5],
        }
    )

    orientation_estimation = OrientationEstimation()
    rolls, pitches = [], []
    for item, next_item in pairwise(chain(result.iterrows(), [None])):
        if item is None:
            break

        idx, datum = item
        duration_ns = 5e6
        if next_item is not None:
            duration_ns = next_item[1]["timestamp [ns]"] - datum["timestamp [ns]"]

        orientation_estimation.update(
            accel=[
                datum["acceleration x [G]"],
                datum["acceleration y [G]"],
                datum["acceleration z [G]"],
            ],
            gyro=[
                datum["gyro x [deg/s]"],
                datum["gyro y [deg/s]"],
                datum["gyro z [deg/s]"],
            ],
            duration_ns=duration_ns,
        )
        rolls.append(orientation_estimation.roll)
        pitches.append(orientation_estimation.pitch)

    result["roll [deg]"] = rolls
    result["pitch [deg]"] = pitches
    return result


def _process_neon_imu_file(raw: pathlib.Path, time: pathlib.Path) -> pd.DataFrame:
    imu_data = neon.raw_imu_file_to_numpy(raw)
    ts = np.fromfile(time, dtype="<u8")
    assert imu_data.shape[0] == ts.shape[0], "Inconsistent IMU and time data"
    logging.debug(f"'{raw.stem}': {ts.shape[0]} data points")

    result = pd.DataFrame(
        {
            "timestamp [ns]": ts,
            "protots [ns]": imu_data["unix_time_ns"],
            "gyro x [deg/s]": imu_data["gyro_x"],
            "gyro y [deg/s]": imu_data["gyro_y"],
            "gyro z [deg/s]": imu_data["gyro_z"],
            "acceleration x [G]": imu_data["accel_x"],
            "acceleration y [G]": imu_data["accel_y"],
            "acceleration z [G]": imu_data["accel_z"],
            "quaternion w": imu_data["quaternion_w"],
            "quaternion x": imu_data["quaternion_x"],
            "quaternion y": imu_data["quaternion_y"],
            "quaternion z": imu_data["quaternion_z"],
        }
    )

    deg_per_rad = 180 / math.pi
    yaws, pitches, rolls = [], [], []
    for idx, datum in result.iterrows():
        roll_rad, pitch_rad, yaw_rad = euler_from_quaternion(
            datum["quaternion x"],
            datum["quaternion y"],
            datum["quaternion z"],
            datum["quaternion w"],
        )
        roll_deg = roll_rad * deg_per_rad
        pitch_deg = pitch_rad * deg_per_rad
        yaw_deg = yaw_rad * deg_per_rad
        rolls.append(roll_deg)
        pitches.append(pitch_deg)
        yaws.append(yaw_deg)

    result["roll [deg]"] = rolls
    result["pitch [deg]"] = pitches
    result["yaw [deg]"] = yaws
    return result


def _process_blinks(
    recording: pathlib.Path,
    export_path: pathlib.Path,
    progress: Optional[Progress] = None,
) -> None:
    logging.debug(f"Detecting blinks")
    metadata = json.loads((recording / "info.json").read_bytes())
    pipline_version = metadata["pipeline_version"]

    blinks = detect_blinks_match_before_optic_flow(recording, pipline_version, progress)

    result = pd.DataFrame(list(blinks))
    result.index.rename("blink id", inplace=True)
    result.reset_index("blink id", inplace=True)
    result["blink id"] += 1

    gaze_path = export_path / "gaze.csv"
    gaze = pd.read_csv(gaze_path, dtype={"fixation id": object, "blink id": object})
    track_fn = progress.track if progress else track
    for idx, blink in track_fn(
        result.iterrows(),
        description="Adding blink ids to gaze.csv...",
        total=result.shape[0],
    ):
        gaze.loc[
            gaze["timestamp [ns]"].between(
                blink["start timestamp [ns]"],
                blink["end timestamp [ns]"],
                inclusive="left",
            ),
            "blink id",
        ] = blink["blink id"]
    gaze.to_csv(gaze_path, index=False)
    logging.info(f"Added blink ids to '{gaze_path}'")

    export_path /= "blinks.csv"
    logging.info(f"Exporting blinks to '{export_path}'")
    result.to_csv(export_path, index=False)


def _process_world(
    recording: pathlib.Path,
    export_path: pathlib.Path,
    progress: Optional[Progress] = None,
) -> None:
    metadata = json.loads((recording / "info.json").read_bytes())
    start_time = metadata["start_time"]
    export_path /= "world.csv"

    ts_files = sorted(
        list(recording.glob("PI world v1 ps*.time"))
        + list(recording.glob("Neon Scene Camera v1 ps*.time")),
        key=_file_sorter_by_part,
    )
    if len(ts_files) == 0:
        ts_files = sorted(
            list(recording.glob("PI world v1 ps*.time_aux"))
            + list(recording.glob("Neon Scene Camera v1 ps*.time_aux")),
            key=_file_sorter_by_part,
        )
    all_ts = []
    filenames = []
    video_offsets = []
    for ts_file in ts_files:
        part_ts = np.fromfile(ts_file, "<u8")
        video_ts = part_ts - part_ts[0]
        all_ts.append(part_ts)
        filenames.append(len(part_ts) * [ts_file])
        video_offsets.append(video_ts)

    all_ts = np.concatenate(all_ts)
    filenames = np.concatenate(filenames)
    video_offsets = np.concatenate(video_offsets)

    result = pd.DataFrame(
        {
            "file": filenames,
            "timestamp [ns]": all_ts,
            "recording offset [secs]": (all_ts - start_time) / 1e9,
            "video offset [secs]": video_offsets / 1e9,
        }
    )
    logging.info(f"Exporting world data to '{export_path}'")
    result.to_csv(export_path, index=False)


def _process_fixations(
    recording: pathlib.Path,
    export_path: pathlib.Path,
    progress: Optional[Progress] = None,
) -> None:
    logging.debug(f"Detecting fixations")
    is_neon_recording = is_neon(recording)
    detect_fixations = (
        detect_fixations_neon if is_neon_recording else detect_fixations_invisible
    )

    _, events = detect_fixations(
        recording,
        use_cached_optic_flow=True,
        progress=progress,
    )
    events = pd.DataFrame(events)

    # Common fields
    events.rename(
        columns={"start_t": "start timestamp [ns]", "end_t": "end timestamp [ns]"},
        inplace=True,
    )
    events["duration [ms]"] = round(
        (events["end timestamp [ns]"] - events["start timestamp [ns]"]) / 1e6
    )

    # Saccades
    gap_events = events.query("label == 'gap'").reset_index(drop=True)
    gap_events.index.rename("saccade id", inplace=True)
    gap_events.reset_index("saccade id", inplace=True)
    gap_events["saccade id"] += 1
    gap_events.rename(
        columns={
            "amplitude_px": "amplitude [px]",
            "amplitude_deg": "amplitude [deg]",
            "mean_vel": "mean velocity [px/s]",
            "peak_vel": "peak velocity [px/s]",
        },
        inplace=True,
    )
    gap_events.drop(
        columns=[
            "label",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "duration_sec",
            "instance",
        ],
        inplace=True,
    )
    saccade_export_path = export_path / "saccades.csv"
    logging.info(f"Exporting saccades to '{saccade_export_path}'")
    gap_events.to_csv(saccade_export_path, index=False)

    # Fixations
    events = events.query("label == 'fixation'").reset_index(drop=True)
    events.index.rename("fixation id", inplace=True)
    events.reset_index("fixation id", inplace=True)
    events["fixation id"] += 1
    events["object conversion work around"] = None

    events["fixation x [px]"] = 0.0
    events["fixation y [px]"] = 0.0
    gaze_path = export_path / "gaze.csv"
    gaze = pd.read_csv(gaze_path, dtype={"fixation id": object, "blink id": object})
    track_fn = progress.track if progress else track
    for idx, fixation in track_fn(
        events.iterrows(),
        description="Adding fixation ids to gaze.csv...",
        total=events.shape[0],
    ):
        gaze_mask = gaze["timestamp [ns]"].between(
            fixation["start timestamp [ns]"],
            fixation["end timestamp [ns]"],
            inclusive="left",
        )
        gaze.loc[gaze_mask, "fixation id"] = int(fixation["fixation id"])

        fixation_loc = gaze.loc[gaze_mask, ["gaze x [px]", "gaze y [px]"]].mean(axis=0)
        azimuth_elevation_loc = gaze.loc[
            gaze_mask, ["azimuth [deg]", "elevation [deg]"]
        ].mean(axis=0)
        # .values is necessary here, otherwise pandas will try to match the row label
        # and fail the assignment
        events.loc[idx, ["fixation x [px]", "fixation y [px]"]] = fixation_loc.values
        events.loc[
            idx, ["azimuth [deg]", "elevation [deg]"]
        ] = azimuth_elevation_loc.values

    gaze.to_csv(gaze_path, index=False)
    logging.info(f"Added fixation ids to '{gaze_path}'")

    events.drop(
        columns=[
            "label",
            "start_x",
            "start_y",
            "end_x",
            "end_y",
            "amplitude_deg",
            "amplitude_px",
            "duration_sec",
            "mean_vel",
            "peak_vel",
            "instance",
            "object conversion work around",
        ],
        inplace=True,
    )
    export_path /= "fixations.csv"
    logging.info(f"Exporting fixations to '{export_path}'")
    events.to_csv(export_path, index=False)


def _setup_logging(verbose_option_count):
    levels = defaultdict(lambda: "WARNING")
    levels[1] = "INFO"
    levels[2] = "DEBUG"
    logging.basicConfig(
        level=levels[verbose_option_count],
        format="%(message)s",
        handlers=[RichHandler()],
    )


def _file_sorter_by_part(file_path: pathlib.Path):
    match = FILE_PATTERN.fullmatch(file_path.name)
    assert match, f"Unexpected file name: '{file_path}'"
    return int(match.group("part"))


if __name__ == "__main__":
    main()
