import ast
import logging

import click

from ...lib.sensors import WorldSensorProcessor
from ...lib.tools.sample_utils import GazeUtils
from ...lib.tools.sample_utils import WornUtils
from ...lib.tools.video.av_writer import AV_Output
from ...lib.tools.video.av_writer import MPEG_Audio_Writer
from ...lib.tools.video.av_writer import ThumbsVideoSampling
from ...lib.tools.video.av_writer import default_av_output
from ...lib.tools.video.frame_processors import FixationScanpathBurner
from ...lib.tools.video.frame_processors import FrameProcessor
from ...lib.tools.video.frame_processors import FrameTimeBurner
from ...lib.tools.video.frame_processors import FrameUndistorter
from ...lib.tools.video.frame_processors import GazeCircleBurner
from .. import pass_recording
from .. import recording_cli

logger = logging.getLogger(__name__)


@recording_cli.group(chain=True, invoke_without_command=True)
@pass_recording
@click.option("-o", "--out-file", default="scene.mp4", show_default=True)
@click.option("--start", default=0, type=click.FLOAT, show_default=True)
@click.option("--end", default=-1, type=click.FLOAT, show_default=True)
@click.option("--audio/--no-audio", default=True, show_default=True)
@click.option("--audio-codec", default="aac", type=click.Choice(["aac", "flac"]))
@click.option(
    "-ve",
    "--video-encoder",
    default="h264_nvenc",
    type=click.Choice(["h264", "h264_nvenc"], case_sensitive=False),
    show_default=True,
)
@click.option("--use-time-files", is_flag=True)
@click.option("-br", "--bit-rate", default="2500000", type=click.INT, show_default=True)
@click.option("-t", "--thumbs-file", default=None, type=click.STRING, show_default=True)
@click.option(
    "--num-frames-thumbs",
    default=1800,
    show_default=True,
    help="number of frames in video (roughly)",
)
@click.option(
    "--frame-size-thumbs",
    default=150,
    show_default=True,
    help="frame size in video (frame-size x frame-size)",
)
@click.option(
    "--file-size-thumbs",
    default=3,
    show_default=True,
    help="approx. file size of video in MB",
)
@click.pass_context
def merge_world_video(
    ctx,
    recording,
    out_file,
    start,
    end,
    audio,
    audio_codec,
    use_time_files,
    bit_rate,
    video_encoder,
    thumbs_file,
    num_frames_thumbs,
    frame_size_thumbs,
    file_size_thumbs,
):
    """Merge world videos for a recording into a single video"""
    if end < 0:
        end = recording.duration_s
    end_epoch_ns = recording.timestamp_at_offset(seconds=end)
    start_epoch_ns = recording.timestamp_at_offset(seconds=start)

    logger.info(
        f"Merge world video "
        f"(start_epoch_ns={start_epoch_ns},"
        f" end_epoch_ns={end_epoch_ns},"
        f" duration={(end_epoch_ns-start_epoch_ns)/1e9}s)"
    )
    ctx.ensure_object(dict)
    ctx.obj["start_epoch_ns"] = start_epoch_ns
    ctx.obj["end_epoch_ns"] = end_epoch_ns


@merge_world_video.result_callback()
@pass_recording
@click.pass_context
def encode_video(
    ctx,
    recording,
    frame_processors,
    out_file,
    start,
    end,
    audio,
    audio_codec,
    use_time_files,
    bit_rate,
    video_encoder,
    thumbs_file,
    num_frames_thumbs,
    frame_size_thumbs,
    file_size_thumbs,
):
    start_epoch_ns = ctx.obj["start_epoch_ns"]
    end_epoch_ns = ctx.obj["end_epoch_ns"]

    logger.info("encode video")

    av_output = []
    av_output.append(
        default_av_output(
            recording,
            out_file,
            video_encoder,
            audio,
            audio_codec=audio_codec,
            bit_rate=bit_rate,
        )
    )
    if thumbs_file:
        section_duration = (end_epoch_ns - start_epoch_ns) / 1e9

        wanted_fps = min(30, num_frames_thumbs / section_duration)

        thumbs_frame_sampler = ThumbsVideoSampling(
            1 / wanted_fps / recording.world.video_info.time_base
        )
        bit_rate_thumbs = 1_000_000
        if section_duration:
            bit_rate_thumbs = min(
                1_000_000, file_size_thumbs * 1e6 * 8 / section_duration
            )

        thumbs_av_output = AV_Output.create_output(
            output_path=thumbs_file,
            video_info=recording.world.video_info,
            audio_info=None,
            encoder=video_encoder,
            gop_size=12,
            bit_rate=bit_rate_thumbs,
            frame_size=(frame_size_thumbs, frame_size_thumbs),
            audio=False,
            audio_codec=None,
            video_sampler=thumbs_frame_sampler,
        )
        av_output.append(thumbs_av_output)

    MPEG_Audio_Writer(
        video=WorldSensorProcessor(
            recording, frame_processors, times_from_time_files=use_time_files
        ),
        audio=recording.audio,
        start_epoch_ns=start_epoch_ns,
        end_epoch_ns=end_epoch_ns,
        output=av_output,
        show_progress=True,
    ).encode()


@merge_world_video.command()
@pass_recording
@click.option(
    "--radius", "-r", default=40, show_default=True, help="radius of gaze circle"
)
@click.option(
    "--width", "-w", default=8, show_default=True, help="stroke width of gaze circle"
)
@click.option(
    "--color",
    "-c",
    default="(255,0,25,124)",
    help="color of the gaze circle in (r,g,b,a)",
)
@click.option(
    "--gaze-selection",
    default="average",
    type=click.Choice(["average", "first", "all"], case_sensitive=False),
    help="select which gaze position to draw in frame",
)
@click.option(
    "--clickhouse-db",
    "-db",
    envvar="CLICKHOUSE_DB",
    show_default=True,
    help="clickhouse connection to fetch gaze data",
)
@click.pass_context
def with_gaze(
    ctx, recording, radius, width, color, gaze_selection, clickhouse_db
) -> FrameProcessor:
    logger.info("Add `GazeCircleBurner`-FrameProcessor to render pipeline")

    start_epoch_ns = ctx.obj["start_epoch_ns"]
    end_epoch_ns = ctx.obj["end_epoch_ns"]

    rgba = ast.literal_eval(color)
    assert len(rgba) == 4, "color does not have 4 channels"
    assert all(
        isinstance(channel, int) for channel in rgba
    ), "channel data type not int"
    assert all(0 <= channel <= 255 for channel in rgba), "channel value not in [0, 255]"

    gaze = recording.gaze
    worn = recording.worn
    if clickhouse_db:
        logger.info("Read gaze data from clickhouse db")
        gaze = recording.gaze200_db
        logger.info("Read worn data from clickhouse db")
        worn = recording.worn_db

    gaze_data = list(
        gaze.read(min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns)
    )
    worn_data = list(
        worn.read(min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns)
    )

    if not gaze_data:
        logger.warning("No gaze found, try reading gaze from files.")
        gaze_data = list(
            recording.gaze.read(
                min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns
            )
        )
    if not worn_data:
        logger.warning("No worn found, try reading worn from files.")
        worn_data = list(
            recording.worn.read(
                min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns
            )
        )

    if gaze_selection == "average":
        gaze_selection_method = GazeUtils.average_gaze_sample
        worn_selection_method = WornUtils.average_worn_sample
    elif gaze_selection == "first":
        gaze_selection_method = GazeUtils.first_gaze_sample
        worn_selection_method = WornUtils.first_worn_sample
    elif gaze_selection == "all":
        gaze_selection_method = GazeUtils.all_gaze_sample
        worn_selection_method = WornUtils.all_worn_sample

    gaze_burner = GazeCircleBurner(
        radius=radius,
        width=width,
        color=rgba,
        gaze_data=gaze_data,
        worn_data=worn_data,
        gaze_selection=gaze_selection_method,
        worn_selection=worn_selection_method,
    )
    return gaze_burner


@merge_world_video.command()
@pass_recording
@click.option(
    "--radius",
    "-r",
    default=30,
    show_default=True,
    help="radius of fixation scanpath circle",
)
@click.option(
    "--width",
    "-w",
    default=2,
    show_default=True,
    help="stroke width of fixation scanpath circle",
)
@click.option(
    "--color",
    "-c",
    default="(18,99,204,255)",
    help="color of the fixation scanpath circle in (r,g,b,a)",
)
@click.option(
    "--clickhouse-db",
    "-db",
    envvar="CLICKHOUSE_DB",
    show_default=True,
    help="clickhouse connection to fetch fixation data",
)
@click.pass_context
def with_scanpath(
    ctx, recording, radius, width, color, clickhouse_db
) -> FrameProcessor:
    logger.info("Add `FixationScanpathBurner`-FrameProcessor to render pipeline")

    start_epoch_ns = ctx.obj["start_epoch_ns"]
    end_epoch_ns = ctx.obj["end_epoch_ns"]

    rgba = ast.literal_eval(color)
    assert len(rgba) == 4, "color does not have 4 channels"
    assert all(
        isinstance(channel, int) for channel in rgba
    ), "channel data type not int"
    assert all(0 <= channel <= 255 for channel in rgba), "channel value not in [0, 255]"

    worn = recording.worn
    scanpath_data = recording.scanpath_data
    if clickhouse_db:
        # logger.info("Read gaze data from clickhouse db")
        # fixations = recording.fixations_db
        logger.info("Read worn data from clickhouse db")
        worn = recording.worn_db

    worn_data = list(
        worn.read(min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns)
    )

    if not worn_data:
        logger.warning("No worn found, try reading worn from files.")
        worn_data = list(
            recording.worn.read(
                min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns
            )
        )

    scanpath_burner = FixationScanpathBurner(
        radius=radius,
        width=width,
        color=rgba,
        scanpath_data=scanpath_data,
        worn_data=worn_data,
    )
    return scanpath_burner


@merge_world_video.command()
def burn_in_timestamps() -> FrameProcessor:
    logger.info("Add `FrameTimeBurner`-FrameProcessor to render pipeline")
    time_burner = FrameTimeBurner()
    return time_burner


@merge_world_video.command()
@pass_recording
def undistort_frames(recording) -> FrameProcessor:
    logger.info("Add `FrameUndistorter`-FrameProcessor to render pipeline")
    frame_undistorter = FrameUndistorter(recording.scene_camera)
    return frame_undistorter
