import enum
import logging
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import semver
from rich.progress import Progress
from semver import VersionInfo

from .blink_detector.blink_detector import blink_detection_pipeline
from .pi_recording import (
    EyePair,
    EyePairProcessor,
    InvisibleEyeReader,
    NeonEyeReader,
    VideoFrame,
    is_neon,
    matching_valid_eye_timestamps,
)


def parse_version_string(version_string: str):
    version_string = version_string.lstrip("v")
    if version_string.count(".") == 1:
        version_string += ".0"
    version_info = VersionInfo.parse(version_string)
    return version_info


log = logging.getLogger(__name__)


def cv2_calcOpticalFlowPyrLK(
    img_prev: np.ndarray,
    img_curr: np.ndarray,
    pts_prev: np.ndarray,
    window_size: int,
    stop_steps: int,
) -> np.ndarray:
    lk_params = dict(
        winSize=(window_size, window_size),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, stop_steps, 0.03),
    )
    img_prev = img_prev.astype(np.uint8)
    img_curr = img_curr.astype(np.uint8)
    pts_next, status, err = cv2.calcOpticalFlowPyrLK(
        img_prev, img_curr, pts_prev, None, **lk_params
    )
    return pts_next - pts_prev


class ResizeAlgorithm(enum.Enum):
    AREA = cv2.INTER_AREA
    CUBIC = cv2.INTER_CUBIC
    NEAREST = cv2.INTER_NEAREST
    LINEAR = cv2.INTER_LINEAR
    LANCZOS = cv2.INTER_LANCZOS4


def resize_image(img, size, interpolation: ResizeAlgorithm):
    img = cv2.resize(img, size, interpolation=interpolation.value)
    img = img.astype(np.float32)
    return img


def image_resize_method_for_pipeline(pipeline_version: semver.VersionInfo):
    pipeline_major_minor = pipeline_version.major, pipeline_version.minor
    if pipeline_major_minor <= (1, 8):
        return ResizeAlgorithm.LINEAR
    if pipeline_major_minor == (1, 10):
        return ResizeAlgorithm.LINEAR
    else:
        return ResizeAlgorithm.AREA


def detect_blinks_match_before_optic_flow(
    recpath: Path, pipeline_version_string: str, progress: Optional[Progress] = None
):
    is_neon_recording = is_neon(recpath)
    eye_timestamps = matching_valid_eye_timestamps(recpath)
    total_frames = len(eye_timestamps["closest"])

    if is_neon_recording:
        matched_eye_samples = NeonEyeReader(recpath).read()
    else:
        matched_eye_samples = InvisibleEyeReader(recpath).read()

    pipeline_version = parse_version_string(pipeline_version_string)
    if pipeline_version_string <= "1.2.0":  # old recs with 1.0 pipeline do not work
        pipeline_version = parse_version_string("1.2.0")

    gaze_pipeline_resize_method = image_resize_method_for_pipeline(pipeline_version)
    if progress:
        blink_task_id = progress.add_task(
            description="Detecting blinks...", total=total_frames
        )

    def blink_classifier(eye_pairs: List[EyePair]):
        if progress:
            progress.update(blink_task_id, advance=len(eye_pairs))

        if is_neon_recording:
            clf_path = (
                Path(__file__).resolve().parent
                / "blink_detector/weights/xgb_17_neon.json"
            )
            preprocess_frame = lambda frame: frame.resized(
                (64, 64), gaze_pipeline_resize_method
            )

        else:
            clf_path = (
                Path(__file__).resolve().parent
                / "blink_detector/weights/xgb_17_invisible.json"
            )

            preprocess_frame = lambda frame: cv2.rotate(
                frame.resized((64, 64), gaze_pipeline_resize_method),
                cv2.ROTATE_90_COUNTERCLOCKWISE,
            )

        eye_left_images = np.array(
            [preprocess_frame(left_frame) for left_frame, _ in eye_pairs]
        )

        eye_right_images = np.array(
            [preprocess_frame(right_frame) for _, right_frame in eye_pairs]
        )

        batch_timestamps = np.array([left.timestamp for left, _ in eye_pairs])
        blink_events = blink_detection_pipeline(
            eye_left_images, eye_right_images, batch_timestamps, clf_path
        )

        return blink_events

    processors = {
        "times": EyePairProcessor(
            "times", lambda pairs: [left.timestamp for left, _ in pairs], 1000
        ),
        "blink": EyePairProcessor("blink", blink_classifier, 1000),
    }
    for left_eye_sample, right_eye_sample in matched_eye_samples:
        l_ts, l_img = left_eye_sample
        r_ts, r_img = right_eye_sample
        l_frame = VideoFrame(timestamp=l_ts, image=l_img)
        r_frame = VideoFrame(timestamp=r_ts, image=r_img)
        for processor in processors.values():
            processor.put((l_frame, r_frame))

    for processor in processors.values():
        processor.process()

    blink_events = np.array(processors["blink"].output)

    for blink_event in blink_events:
        if blink_event.label != "blink":
            continue

        yield (
            {
                "start timestamp [ns]": blink_event.start_time,
                "end timestamp [ns]": blink_event.end_time,
                "duration [ms]": (
                    (blink_event.end_time - blink_event.start_time) // 1_000_000
                ),
            }
        )


if __name__ == "__main__":
    # recpath = "/recs/longrec"
    # recpath = "/recs/2min_timer-d05aa117"
    # recpath = "/recs/2books1-ee550727"
    recpath = "/recs/sync3"
    result = list(detect_blinks_match_before_optic_flow(recpath))
    for x in result:
        print(x["start"], x["stop"], x["label"])
    print(len(result))
