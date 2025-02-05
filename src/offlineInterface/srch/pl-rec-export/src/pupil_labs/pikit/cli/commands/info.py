import json

import click
from pikit import Recording
from pikit.lib.readers import TimeReader

from .. import pass_recording
from .. import recording_cli


@recording_cli.command()
@pass_recording
def silent(recording: Recording):
    if recording.is_silent():
        click.echo("silent: yes")
    else:
        click.echo("silent: no")


@recording_cli.command()
@pass_recording
def info(recording: Recording):
    """Show overview of recording files"""
    click.echo("recording")
    duration_s = round(recording.duration_ns / 1e9, 3)
    attrs = [
        ("id", recording.id),
        ("start", f"{recording.start_epoch_ns} ({recording.start_datetime})"),
        ("duration", f"{recording.duration_ns} ({duration_s}s)"),
    ]
    for attr, value in attrs:
        click.echo(f"    {attr}: {value}")
    click.echo("--")

    click.echo("info.json")
    click.echo(json.dumps(recording.info, indent=2))
    click.echo("--")

    _echo_world_part_info(recording)
    _echo_eye_part_info(recording)
    _echo_gaze_part_info(recording)
    _echo_worn_part_info(recording)
    _echo_imu_part_info(recording)
    _echo_events_info(recording)
    _echo_template_info(recording)


def _echo_worn_part_info(recording: Recording):
    click.echo("worn")
    for worn_part in recording.worn.parts:
        click.echo(f"    ps{worn_part.number}:")
        worn_info = "missing!"
        if worn_part.values:
            gaze_values = worn_part.values
            worn_info = ", ".join(
                (f"values={len(gaze_values)}", f"size={gaze_values.size}")
            )
        click.echo("         .raw: " + worn_info)
    click.echo("--")


def _echo_gaze_part_info(recording: Recording):
    click.echo("gaze")
    for gaze_part in recording.gaze.parts:
        click.echo(f"    ps{gaze_part.number}:")
        _echo_time_file_data(gaze_part.times, recording.start_epoch_ns)
        gaze_info = "missing!"
        if gaze_part.values:
            gaze_values = gaze_part.values
            gaze_info = ", ".join(
                (f"values={len(gaze_values)}", f"size={gaze_values.size}")
            )
        click.echo("         .raw: " + gaze_info)
    click.echo("--")


def _echo_imu_part_info(recording: Recording):
    click.echo("imu")
    for imu_part in recording.imu.parts:
        click.echo(f"    ps{imu_part.number}:")
        _echo_time_file_data(imu_part.times, recording.start_epoch_ns)
        imu_info = "missing!"
        if imu_part.values:
            imu_values = imu_part.values
            imu_info = ", ".join(
                (f"values={len(imu_values)}", f"size={imu_values.size}")
            )
        click.echo("         .raw: " + imu_info)
    click.echo("--")


def _echo_world_part_info(recording: Recording):
    click.echo("world")
    for world_part in recording.world.parts:
        click.echo(f"    ps{world_part.number}:")
        video_info = []
        _echo_time_file_data(world_part.times, recording.start_epoch_ns)

        if world_part.video:
            if world_part.video.duration_ns:
                v_duration_s = (
                    f"{round(float(world_part.video.duration_ns * 1e-9), 3)}s"
                )
            else:
                v_duration_s = "?"
            video_info.extend(
                [
                    f"vframes={world_part.video.n_frames_video}",
                    f"vduration={v_duration_s}",
                ]
            )
            has_audio = world_part.video.has_audio
            if not has_audio:
                video_info.append("no audio")
            else:
                a_duration_s = round(
                    float(world_part.video.duration_audio_ns * 1e-9), 3
                )
                video_info.extend(
                    [
                        f"aframes={world_part.video.n_frames_audio}",
                        f"aduration={a_duration_s}s",
                    ]
                )
            video_info.append(f"size={world_part.video.reader.size}")
            video_extension = "  .mp4" if world_part.video.is_mp4 else ".mjpeg"
        else:
            video_extension = " video"
            video_info.append("missing/broken")
        click.echo(f"       {video_extension}: " + ", ".join(video_info))
    click.echo("--")


def _echo_eye_part_info(recording: Recording):
    for eye in ["left", "right"]:
        click.echo(f"eye_{eye}")
        for eye_part in recording.recording_parts.eye(eye):
            click.echo(f"    ps{eye_part.number}:")
            _echo_time_file_data(eye_part.times, recording.start_epoch_ns)

            video_info = []
            video_extension = ""
            if eye_part.video:
                if eye_part.video.duration_ns:
                    v_duration_s = (
                        f"{round(float(eye_part.video.duration_ns * 1e-9), 3)}s"
                    )
                else:
                    v_duration_s = "?"
                video_info.extend(
                    [
                        f"vframes={eye_part.video.n_frames_video}",
                        f"vduration={v_duration_s}",
                    ]
                )
                video_extension = "  .mp4" if eye_part.video.is_mp4 else ".mjpeg"
                video_info.append(f"size={eye_part.video.reader.size}")
            else:
                video_extension = " video"
                video_info.append("missing/broken")
            click.echo(f"       {video_extension}: " + ", ".join(video_info))
        click.echo("--")


def _echo_events_info(recording: Recording):
    click.echo("events")
    for event in recording.events:
        event_info = ", ".join(
            (
                f"time={event.epoch_ns}",
                f"name={event.name}",
                f"offset_s={round(event.offset_ns/1e9, 3)}s",
                f"offset_ns={event.offset_ns}",
            )
        )
        click.echo("    " + event_info)
    click.echo("--")


def _echo_template_info(recording: Recording):
    click.echo("template")
    template_file = recording.files.get("template.json")
    if template_file:
        template = json.load(recording.files.get("template.json").open("rb"))
        template_data = recording.info.get("template_data") or {}
        for item in template.get("items") or []:
            answer = (template_data.get("data") or {}).get(item["id"])
            click.echo(f"    {item['title']}: {answer}")


def _echo_time_file_data(times: TimeReader, start_epoch_ns: int = 0):
    if not times:
        click.echo("        .time: missing!")
        return
    first_epoch_ns = times.first
    last_epoch_ns = times.last
    duration_ns = last_epoch_ns - first_epoch_ns
    offset_ns = first_epoch_ns - start_epoch_ns
    click.echo(
        "        .time: "
        + ", ".join(
            (
                f"duration={round(duration_ns/1e9, 3)}s",
                f"values={len(times.values)}",
                f"offset={round(offset_ns/1e9, 3)}s",
                f"first={first_epoch_ns}",
                f"last={last_epoch_ns}",
                f"size={times.size}",
            )
        )
    )
