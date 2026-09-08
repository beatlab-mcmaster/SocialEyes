from datetime import datetime, timezone

import pytest

from glassesRecord.monitoring.recording_state import (
    RecordingInfo,
    RecordingState,
    check_if_mp4_sizes_increased,
    determine_recording_state,
)
from glassesRecord.monitoring.scripts.statistics_schema import Mp4File, NeonRecording


@pytest.fixture
def current_recording() -> NeonRecording:
    return NeonRecording(
        workspace_id="workspace-1",
        recording_id="recording-1",
        mp4_files=[
            Mp4File(
                file_name="video.mp4",
                file_size_bytes=200,
                creation_time=datetime(2026, 8, 25, tzinfo=timezone.utc),
                modification_time=datetime(2026, 8, 25, 0, 1, tzinfo=timezone.utc),
            )
        ],
    )


def previous_info(
    *,
    file_size_bytes: int = 100,
    details: dict[str, Mp4File] | None = None,
) -> RecordingInfo:
    if details is None:
        details = {
            "video.mp4": Mp4File(
                file_name="video.mp4",
                file_size_bytes=file_size_bytes,
                creation_time=datetime(2026, 8, 25, tzinfo=timezone.utc),
                modification_time=datetime(2026, 8, 25, 0, 1, tzinfo=timezone.utc),
            )
        }

    return RecordingInfo(
        workspace_id="workspace-1",
        recording_id="recording-1",
        state=RecordingState.UNKNOWN,
        details=details,
    )


def test_new_recording_is_unknown(current_recording):
    result = determine_recording_state(current_recording, None)

    assert result is RecordingState.UNKNOWN


def test_recording_without_mp4_is_detected():
    recording = NeonRecording(
        workspace_id="workspace-1",
        recording_id="recording-1",
        mp4_files=[],
    )

    result = determine_recording_state(
        recording,
        previous_info(),
    )

    assert result is RecordingState.RECORDING_HAS_NO_MP4


def test_recording_is_in_progress_when_mp4_grows(current_recording):
    result = determine_recording_state(
        current_recording,
        previous_info(file_size_bytes=100),
    )

    assert result is RecordingState.RECORDING_IN_PROGRESS


def test_recording_is_unsaved_or_failed_when_mp4_does_not_grow(current_recording):
    result = determine_recording_state(
        current_recording,
        previous_info(file_size_bytes=200),
    )

    assert result is RecordingState.RECORDING_UNSAVED_OR_FAILED


def test_mp4_growth_is_detected(current_recording):
    result = check_if_mp4_sizes_increased(
        current_recording,
        previous_info(file_size_bytes=100),
    )

    assert result is True


def test_mp4_growth_is_not_detected_when_size_is_unchanged(current_recording):
    result = check_if_mp4_sizes_increased(
        current_recording,
        previous_info(file_size_bytes=200),
    )

    assert result is False


def test_mp4_growth_is_not_detected_without_previous_details(current_recording):
    result = check_if_mp4_sizes_increased(
        current_recording,
        previous_info(details=None),
    )

    assert result is True
