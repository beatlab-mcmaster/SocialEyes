from itertools import zip_longest

import click

from .. import pass_recording
from .. import recording_cli
from ...lib.sensors import WornSample
from ...lib.tools.writer import EXPORT_FORMATS
from ...lib.tools.writer import row_writer
from ...recording import Recording


@recording_cli.group()
def export():
    """Export raw files to csv and other formats"""


RECORDING_FRAME_COLUMNS = [
    "row",
    "recording_id",
    "datetime",
    "epoch_ns",
    "epoch_s",
    "offset_s",
    "offset_ms",
    "offset_ns",
]

GAZE_EXPORT_COLUMNS = RECORDING_FRAME_COLUMNS + [
    "gaze_x_dist",
    "gaze_y_dist",
    "gaze_x_norm",
    "gaze_y_norm",
    "gaze_x_rectified",
    "gaze_y_rectified",
    "worn",
]

IMU_EXPORT_COLUMNS = RECORDING_FRAME_COLUMNS + [
    "imu_accel_x",
    "imu_accel_y",
    "imu_accel_z",
    "imu_gyro_x",
    "imu_gyro_y",
    "imu_gyro_z",
]


def parse_column_arguments(include_columns, exclude_columns, available_columns):
    include_columns = parse_string_list(include_columns) or available_columns
    exclude_columns = set(parse_string_list(exclude_columns))
    export_columns = [
        column for column in include_columns if column not in exclude_columns
    ]

    invalid_columns = set(export_columns) - set(available_columns)

    if invalid_columns:
        click.echo(f"invalid column(s) found: {invalid_columns}")
        exit(1)
    return export_columns


def parse_string_list(string_list, separator=","):
    """
    Parses a string "foo,bar" into ["foo", "bar"]
    """
    if not string_list:
        return []
    result = []
    for entry in string_list.split(separator):
        entry = entry.strip()
        if not entry:
            continue
        result.append(entry)
    return result


@export.command()
@pass_recording
@click.option(
    "-f",
    "--format",
    default="tsv",
    type=click.Choice(EXPORT_FORMATS, case_sensitive=False),
    show_default=True,
)
@click.option("-l", "--limit", type=int, default=None, show_default=True)
@click.option("-s", "--skip", type=int, default=0, show_default=True)
@click.option(
    "-c",
    "--columns",
    default=",".join(GAZE_EXPORT_COLUMNS),
    help=(
        """
    Comma seperated list of columns to export.
    """
    ),
    show_default=True,
)
@click.option(
    "-C",
    "--exclude-columns",
    help=(
        """
    Comma seperated list of columns to exclude from export.
    """
    ),
    show_default=True,
)
@click.option("-o", "--outfile", type=click.File("w"), default="-", show_default=True)
def gaze(
    recording: Recording,
    outfile,
    format: str,
    limit: int,
    skip: int,
    columns: str,
    exclude_columns: str,
):
    """Export Gaze data"""

    export_columns = parse_column_arguments(
        columns, exclude_columns, GAZE_EXPORT_COLUMNS
    )

    def _get_gaze_rows():

        for rownum, (gaze, worn_sample) in enumerate(
            zip_longest(recording.gaze, recording.worn)
        ):
            if skip and skip < rownum:
                continue

            if limit is not None and limit < rownum:
                break

            if not gaze:
                break

            if not worn_sample:
                worn_sample = WornSample(
                    recording=gaze.recording,
                    timestamp=gaze.timestamp,
                    duration=gaze.duration,
                    worn=255,  # assume headset was worn if no worn value was written
                )

            rownum += 1
            row = {
                "row": rownum + skip,
                "recording_id": gaze.recording.id,
                "epoch_s": gaze.timestamp.epoch_s,
                "epoch_ns": gaze.timestamp.epoch_ns,
                "datetime": gaze.timestamp.datetime,
                "offset_s": gaze.timestamp.offset_s,
                "offset_ns": gaze.timestamp.offset_ns,
                "offset_ms": gaze.timestamp.offset_ms,
                "gaze_x_dist": gaze.position.distorted.x,
                "gaze_y_dist": gaze.position.distorted.y,
                "gaze_x_norm": gaze.position.normalized.x,
                "gaze_y_norm": gaze.position.normalized.y,
                "gaze_x_rectified": gaze.position.rectified.x,
                "gaze_y_rectified": gaze.position.rectified.y,
                "worn": worn_sample.worn,
            }

            yield {key: value for key, value in row.items() if key in export_columns}

    row_writer(outfile, _get_gaze_rows, export_columns, format)


@export.command()
@pass_recording
@click.option(
    "-f",
    "--format",
    default="tsv",
    type=click.Choice(EXPORT_FORMATS, case_sensitive=False),
    show_default=True,
)
@click.option("-l", "--limit", type=int, default=None, show_default=True)
@click.option("-s", "--skip", type=int, default=0, show_default=True)
@click.option(
    "-c",
    "--columns",
    default=",".join(IMU_EXPORT_COLUMNS),
    help=(
        """
    Comma seperated list of columns to export.
    """
    ),
    show_default=True,
)
@click.option(
    "-C",
    "--exclude-columns",
    help=(
        """
    Comma seperated list of columns to exclude from export.
    """
    ),
    show_default=True,
)
@click.option("-o", "--outfile", type=click.File("w"), default="-", show_default=True)
def imu(
    recording: Recording,
    outfile,
    format: str,
    limit: int,
    skip: int,
    columns: str,
    exclude_columns: str,
):
    """Export IMU data"""

    export_columns = parse_column_arguments(
        columns, exclude_columns, IMU_EXPORT_COLUMNS
    )

    def _get_imu_rows():
        for rownum, imu in enumerate(recording.imu):
            if skip and skip < rownum:
                continue

            if limit is not None and limit < rownum:
                break

            rownum += 1
            row = {
                "row": rownum + skip,
                "recording_id": imu.recording.id,
                "epoch_s": imu.timestamp.epoch_s,
                "epoch_ns": imu.timestamp.epoch_ns,
                "datetime": imu.timestamp.datetime,
                "offset_s": imu.timestamp.offset_s,
                "offset_ns": imu.timestamp.offset_ns,
                "offset_ms": imu.timestamp.offset_ms,
                "imu_accel_x": imu.acceleration.x,
                "imu_accel_y": imu.acceleration.y,
                "imu_accel_z": imu.acceleration.z,
                "imu_gyro_x": imu.gyroscope.x,
                "imu_gyro_y": imu.gyroscope.y,
                "imu_gyro_z": imu.gyroscope.z,
            }

            yield {key: value for key, value in row.items() if key in export_columns}

    row_writer(outfile, _get_imu_rows, export_columns, format)
