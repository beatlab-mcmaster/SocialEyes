import json
import logging
import os
from pathlib import Path

import av
import click

from .. import pass_recording
from .. import recording_cli
from ...lib.sensors import EyeSensor
from ...lib.sensors import WorldSensor
from ...lib.tools.video.av_writer import default_av_output
from ...lib.tools.video.av_writer import MPEG_Audio_Writer
from ...lib.tools.writer import row_writer

logger = logging.getLogger(__name__)


@recording_cli.command()
@pass_recording
@click.option(
    "-o",
    "--out-folder",
    type=click.Path(file_okay=False, writable=True, allow_dash=True, exists=False),
    help="destination folder of recording crop",
)
@click.option(
    "-s",
    "--start",
    default=0,
    type=click.FLOAT,
    show_default=True,
    help="start time of crop in offset-seconds",
)
@click.option(
    "-e",
    "--end",
    default=-1,
    type=click.FLOAT,
    show_default=True,
    help="end time of crop in offset-seconds",
)
@click.option(
    "-ve",
    "--video-encoder",
    default="h264_nvenc",
    type=click.Choice(["h264", "h264_nvenc"], case_sensitive=False),
    show_default=True,
    help="video encoder, h264_nvenc for gpu acceleration",
)
@click.option(
    "-br",
    "--bit-rate",
    default="2500000",
    type=click.INT,
    show_default=True,
    help="bit rate for world video",
)
@click.option(
    "--times-from-time-files",
    is_flag=True,
    help=(
        "use time files of world video as timestamps to overwrite mp4 timestamps"
        "(only needed if they are wrong)"
    ),
)
def crop(
    recording, out_folder, start, end, video_encoder, bit_rate, times_from_time_files
):
    """Crop recording from `start` to `end` and write result to `out-folder`"""
    if end < 0:
        end = recording.duration_s
    end_epoch_ns = recording.timestamp_at_offset(seconds=end)
    start_epoch_ns = recording.timestamp_at_offset(seconds=start)

    logger.info(
        f"Crop recording "
        f"(start_epoch_ns={start_epoch_ns}, end_epoch_ns={end_epoch_ns},"
        f" duration={(end_epoch_ns-start_epoch_ns)/1e9}s)"
    )
    os.makedirs(out_folder, exist_ok=True)
    out_folder = Path(out_folder)

    write_info(recording, start_epoch_ns, end_epoch_ns, out_folder)
    write_gaze(recording, start_epoch_ns, end_epoch_ns, out_folder)
    write_gaze200(recording, start_epoch_ns, end_epoch_ns, out_folder)
    write_imu(recording, start_epoch_ns, end_epoch_ns, out_folder)
    write_world(
        recording,
        start_epoch_ns,
        end_epoch_ns,
        out_folder,
        video_encoder,
        times_from_time_files,
        bit_rate,
    )
    write_eyes(recording, start_epoch_ns, end_epoch_ns, out_folder, video_encoder)
    write_events(recording, start_epoch_ns, end_epoch_ns, out_folder)
    copy_template_json(recording, out_folder)
    copy_wearer_json(recording, out_folder)


def write_info(recording, start_epoch_ns, end_epoch_ns, out_folder):
    logger.info("write info.json...")
    info = recording.info
    info["start_time"] = start_epoch_ns
    info["duration"] = end_epoch_ns - start_epoch_ns
    with open(out_folder / "info.json", "w") as info_file:
        json.dump(info, info_file)


def copy_template_json(recording, out_folder):
    logger.info("copy template.json...")
    with open(out_folder / "template.json", "w") as template_file:
        json.dump(recording.template_json, template_file)


def copy_wearer_json(recording, out_folder):
    logger.info("copy wearer.json...")
    with open(out_folder / "wearer.json", "w") as wearer_file:
        json.dump(recording.wearer_json, wearer_file)


def write_events(recording, start_epoch_ns, end_epoch_ns, out_folder):
    event_times = []
    event_file = open(out_folder / "event.txt", "w")
    for event in recording.events:
        if start_epoch_ns <= event.epoch_ns <= end_epoch_ns:
            event_file.writelines([event.name])
            event_times.append(event.epoch_ns)
    with open(out_folder / "event.time", "wb") as time_file:
        row_writer(
            time_file,
            lambda: ({"epoch_ns": time} for time in event_times),
            ["epoch_ns"],
            "<Q",
        )


def write_gaze(recording, start_epoch_ns, end_epoch_ns, out_folder):
    logger.info("write gaze...")

    def _get_gaze_timestamps():
        for gaze in recording.gaze.read(start_epoch_ns, end_epoch_ns):
            yield {"epoch_ns": gaze.timestamp.epoch_ns}

    def _get_gaze_positions():
        for gaze in recording.gaze.read(start_epoch_ns, end_epoch_ns):
            yield {
                "gaze_x_dist": gaze.position.distorted.x,
                "gaze_y_dist": gaze.position.distorted.y,
            }

    with open(out_folder / "gaze ps1.time", "wb") as time_file:
        row_writer(time_file, _get_gaze_timestamps, ["epoch_ns"], "<Q")
    with open(out_folder / "gaze ps1.raw", "wb") as gaze_file:
        row_writer(
            gaze_file, _get_gaze_positions, ["gaze_x_dist", "gaze_y_dist"], "<2f"
        )


def write_gaze200(recording, start_epoch_ns, end_epoch_ns, out_folder):
    if not recording.gaze200.sensor_part_readers:
        logger.info("no gaze200 data -> skip")
        return
    logger.info("write gaze200...")

    def _get_gaze_timestamps():
        for gaze200 in recording.gaze200.read(start_epoch_ns, end_epoch_ns):
            yield {"epoch_ns": gaze200.timestamp.epoch_ns}

    def _get_gaze_positions():
        for gaze200 in recording.gaze200.read(start_epoch_ns, end_epoch_ns):
            yield {
                "gaze_x_dist": gaze200.position.distorted.x,
                "gaze_y_dist": gaze200.position.distorted.y,
            }

    with open(out_folder / "gaze_200hz.time", "wb") as time_file:
        row_writer(time_file, _get_gaze_timestamps, ["epoch_ns"], "<Q")
    with open(out_folder / "gaze_200hz.raw", "wb") as gaze_file:
        row_writer(
            gaze_file, _get_gaze_positions, ["gaze_x_dist", "gaze_y_dist"], "<2f"
        )


def write_imu(recording, start_epoch_ns, end_epoch_ns, out_folder):
    logger.info("write imu...")

    def _get_imu_timestamps():
        for imu in recording.imu.read(start_epoch_ns, end_epoch_ns):
            yield {"epoch_ns": imu.timestamp.epoch_ns}

    def _get_imu_data():
        for imu in recording.imu.read(start_epoch_ns, end_epoch_ns):
            yield {
                "imu_accel_x": imu.acceleration.x,
                "imu_accel_y": imu.acceleration.y,
                "imu_accel_z": imu.acceleration.z,
                "imu_gyro_x": imu.gyroscope.x,
                "imu_gyro_y": imu.gyroscope.y,
                "imu_gyro_z": imu.gyroscope.z,
            }

    with open(out_folder / "extimu ps1.time", "wb") as time_file:
        row_writer(time_file, _get_imu_timestamps, ["epoch_ns"], "<Q")
    with open(out_folder / "extimu ps1.raw", "wb") as imu_file:
        row_writer(
            imu_file,
            _get_imu_data,
            [
                "imu_gyro_x",
                "imu_gyro_y",
                "imu_gyro_z",
                "imu_accel_x",
                "imu_accel_y",
                "imu_accel_z",
            ],
            "<6f",
        )


def write_world(
    recording,
    start_epoch_ns,
    end_epoch_ns,
    out_folder,
    video_encoder,
    times_from_time_files,
    bit_rate,
):
    logger.info("write world video...")
    video_filename = str(out_folder / "PI world v1 ps1.mp4")
    av_output = []
    av_output.append(
        default_av_output(
            recording,
            video_filename,
            video_encoder,
            with_audio=True,
            audio_codec="aac",
            bit_rate=bit_rate,
        )
    )

    MPEG_Audio_Writer(
        video=WorldSensor(recording, times_from_time_files=times_from_time_files),
        audio=recording.audio,
        start_epoch_ns=start_epoch_ns,
        end_epoch_ns=end_epoch_ns,
        output=av_output,
        show_progress=True,
    ).encode()

    # timestamps
    def _get_world_timestamps():
        world_video = av.open(video_filename)
        for packet in world_video.demux(video=0):
            # for frame in packet.decode():
            if packet.pts is not None:
                timestamp = int(packet.pts * packet.time_base * 1e9) + start_epoch_ns
                yield {"epoch_ns": timestamp}

    with open(out_folder / "PI world v1 ps1.time", "wb") as time_file:
        row_writer(time_file, _get_world_timestamps, ["epoch_ns"], "<Q")


def write_eyes(recording, start_epoch_ns, end_epoch_ns, out_folder, video_encoder):
    for eye in ("left", "right"):
        logger.info(f"write {eye} eye video...")
        eye_sensor = EyeSensor(recording, eye, fill_gaps=True)
        video_filename = str(out_folder / f"PI {eye} v1 ps1.mp4")
        av_output = []
        av_output.append(
            default_av_output(
                recording,
                video_filename,
                video_encoder,
                frame_height=eye_sensor.video_info.format.height,
                frame_width=eye_sensor.video_info.format.width,
                with_audio=False,
                bit_rate=eye_sensor.video_info.bit_rate,
            )
        )

        MPEG_Audio_Writer(
            video=eye_sensor,
            audio=None,
            start_epoch_ns=start_epoch_ns,
            end_epoch_ns=end_epoch_ns,
            output=av_output,
            show_progress=True,
        ).encode()

        # timestamps
        def _get_eye_timestamps():
            eye_video = av.open(video_filename)
            for packet in eye_video.demux(video=0):
                # for frame in packet.decode():
                if packet.pts is not None:
                    timestamp = (
                        int(packet.pts * packet.time_base * 1e9) + start_epoch_ns
                    )
                    yield {"epoch_ns": timestamp}

        with open(out_folder / f"PI {eye} v1 ps1.time", "wb") as time_file:
            row_writer(time_file, _get_eye_timestamps, ["epoch_ns"], "<Q")
