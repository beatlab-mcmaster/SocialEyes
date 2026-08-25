import datetime
from dataclasses import dataclass
from enum import Enum

from .scripts.statistics_schema import Mp4File, NeonRecording


class RecordingState(Enum):
    UNKNOWN = 0,
    IDLE = 1,
    RECORDING_IN_PROGRESS = 2,
    RECORDING_HAS_NO_MP4 = 3,
    RECORDING_UNSAVED_OR_FAILED = 4,

@dataclass
class RecordingInfo:
    workspace_id: str
    recording_id: str
    state: RecordingState
    started_at: datetime.datetime | None = None
    duration: float | None = None
    details: dict[str, Mp4File] | None = None
    red_light_indicator_detected: bool | None = None

def determine_recording_state(neon_recording: NeonRecording, old_recording_info: RecordingInfo | None) -> RecordingState:
        result = None
        if old_recording_info is None:
            # If we haven't seen this recording before, we don't know if it's still recording or not
            result = RecordingState.UNKNOWN
        else:
            if len(neon_recording.mp4_files) == 0:
                # If there are no mp4 files, then the recording has failed to save any mp4 files
                result = RecordingState.RECORDING_HAS_NO_MP4
            else:
                any_size_increased = check_if_mp4_sizes_increased(neon_recording, old_recording_info)
                result = RecordingState.RECORDING_IN_PROGRESS if any_size_increased else RecordingState.RECORDING_UNSAVED_OR_FAILED
        return result

def check_if_mp4_sizes_increased(neon_recording: NeonRecording, old_recording_info: RecordingInfo) -> bool:
    # Check if any of the mp4 files have increased in size since the last time we checked
    any_size_increased = False
    for mp4 in neon_recording.mp4_files:
        if old_recording_info.details is not None:
            old_mp4_file_obj = old_recording_info.details.get(mp4.file_name)
            if old_mp4_file_obj is not None and mp4.file_size_bytes > old_mp4_file_obj.file_size_bytes:
                any_size_increased = True
                break
    return any_size_increased
