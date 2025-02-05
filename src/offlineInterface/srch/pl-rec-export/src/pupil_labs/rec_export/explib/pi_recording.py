import json
import logging
import os
import re
import struct
import typing as T
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import more_itertools
import numpy as np

from .utils import closest_matches_iterative, skip_non_monotonic
from .video import (
    ResizeAlgorithm,
    mjpeg_video_frame_generator,
    mp4_video_frame_generator,
    resize_image,
)

log = logging.getLogger(__name__)
VideoPath = T.Union[str, Path]


def matched_stream_samples(stream_a, stream_b, max_dispersion=int(1e9 // 200)):
    def _get_sample_timestamp(sample):
        timestamp, frame = sample
        return timestamp

    yield from closest_matches_iterative(
        stream_a,
        stream_b,
        max_dispersion=max_dispersion,
        key=_get_sample_timestamp,
    )


class InvisibleEyeReader:
    def __init__(self, rec_path):
        self.rec_path = Path(rec_path)

    def read(self):
        matched_samples = matched_stream_samples(
            pi_sensor_sample_generator(self.rec_path, "PI left v1"),
            pi_sensor_sample_generator(self.rec_path, "PI right v1"),
        )
        yield from matched_samples


class NeonEyeReader(object):
    def __init__(self, rec_path):
        self.rec_path = Path(rec_path)

    def read(self):
        for timestamp, eye_pair_image in pi_sensor_sample_generator(
            self.rec_path, "Neon Sensor Module v1"
        ):
            left_image, right_image = np.hsplit(eye_pair_image, 2)
            yield (timestamp, left_image), (timestamp, right_image)


def get_parted_files(recording_path):
    regex = re.compile(r"(?P<prefix>.+) ps(?P<part_number>\d+)(?P<extension>\..*)")
    result = {}
    parts = []
    for filename in os.listdir(recording_path):
        regex_match = regex.search(filename)
        if regex_match:
            prefix, part_number, extension = regex_match.groups()
            part_number = int(part_number)
            parts.append((part_number, prefix, extension, filename))

    for part_number, prefix, extension, filename in sorted(parts):
        result.setdefault(prefix, {}).setdefault(part_number, {})[extension] = filename
    return result


def binary_array_file_reader(filepath, format, chunk_size=1024 * 1024):
    size_of_item = struct.calcsize(format)
    chunk_size_aligned = chunk_size // size_of_item * size_of_item
    with open(filepath, "rb", buffering=chunk_size_aligned) as filebuffer:
        yield from struct.iter_unpack(format, filebuffer.read())


def pi_time_file_reader(filepath):
    for item in binary_array_file_reader(filepath, format="<Q"):
        yield item[0]


def pi_sensor_part_sources(rec_path, sensor_prefix):
    parted_files = get_parted_files(Path(rec_path))
    sensor_files = parted_files.get(f"{sensor_prefix}") or {}

    def _rec_file_path(filename):
        return Path(rec_path) / filename

    for part_number, files_by_extension in sorted(sensor_files.items()):
        timestamp_source = None
        frame_source = None
        part_desc = f"{sensor_prefix} part:{part_number}"
        errors = []

        time_file_name = files_by_extension.get(".time")
        if time_file_name:
            time_file_path = _rec_file_path(time_file_name)
            timestamp_source = {
                "path": time_file_path,
                "generator": pi_time_file_reader(time_file_path),
            }

        mp4_video_filename = files_by_extension.get(".mp4")
        if mp4_video_filename:
            video_file_path = _rec_file_path(mp4_video_filename)
            frame_source = {
                "path": video_file_path,
                "generator": mp4_video_frame_generator(video_file_path),
            }

        mjpeg_video_filename = files_by_extension.get(".mjpeg")
        if mjpeg_video_filename:
            video_file_path = _rec_file_path(mjpeg_video_filename)
            frame_source = {
                "path": video_file_path,
                "generator": mjpeg_video_frame_generator(video_file_path),
            }

        if mp4_video_filename and mjpeg_video_filename:
            log.warning(f"found both .mp4/.mjpeg for {part_desc}")
            # TODO(dan): maybe be smart here and use the one that looks correct?

        if not frame_source:
            errors.append(f"missing video .mp4/.mjpeg file for {part_desc}")

        if not timestamp_source:
            errors.append(f"missing timestamp .time file for {part_desc}")

        if errors:
            log.warning(f"skipping {part_desc}, errors: {errors}")
            continue

        yield part_desc, timestamp_source, frame_source


def pi_sensor_sample_generator(rec_path, sensor, skip_non_monotonic=True):  # noqa
    previous_timestamp = 0
    seen_timestamps = {}
    skipped_samples = 0
    duplicated_timestamps = 0
    sensor_desc = f"sensor:{sensor}"

    for part_desc, timestamp_source, frame_source in pi_sensor_part_sources(
        rec_path, sensor
    ):
        log.info(f"reading times for {part_desc} from {timestamp_source['path']}")
        log.info(f"reading frames for {part_desc} from {frame_source['path']}")

        timestamp_stream_finished = False
        video_stream_finished = False

        part_non_monotonic_samples = 0
        part_duplicate_timestamps = 0
        part_failed_frames = 0
        index = 0
        frames_generator = frame_source["generator"]
        timestamps_generator = timestamp_source["generator"]
        try:
            while True:
                index += 1
                try:
                    timestamp = next(timestamps_generator)
                except StopIteration:
                    timestamp_stream_finished = True
                try:
                    frame = next(frames_generator)
                except StopIteration:
                    video_stream_finished = True

                if video_stream_finished and timestamp_stream_finished:
                    log.info(f"reading {part_desc} finished, timestamps/frames:{index}")
                    break
                if video_stream_finished and not timestamp_stream_finished:
                    log.warning(f"{part_desc} had extra timestamps")
                    break
                if timestamp_stream_finished and not video_stream_finished:
                    log.warning(f"{part_desc} had extra video frames")
                    break

                if timestamp in seen_timestamps:
                    part_duplicate_timestamps += 1
                    log.debug(f"found duplicate timestamp:{timestamp} in {part_desc}")
                    continue

                seen_timestamps[timestamp] = seen_timestamps.get(timestamp, 0) + 1

                if previous_timestamp >= timestamp:
                    err_msg = (
                        f"non monotonic timestamp: "
                        f"{previous_timestamp} >= {timestamp} in {part_desc}"
                    )
                    if skip_non_monotonic:
                        log.debug(f"skipping sample for {err_msg}")
                        part_non_monotonic_samples += 1
                        continue
                    else:
                        raise Exception(err_msg)

                if frame is None:
                    log.debug(
                        f"no video frame returned for frame:{index}"
                        f" in file:{frame_source['path']}"
                    )
                    part_failed_frames += 1
                    continue

                yield timestamp, frame
                previous_timestamp = timestamp

        except Exception as exc:
            log.error(f"error when reading from sources for {part_desc}: {exc}")
            continue

        if part_duplicate_timestamps:
            skipped_samples += part_duplicate_timestamps
            log.warning(
                f"found {part_duplicate_timestamps} duplicate timestamps in {part_desc}"
            )

        if part_non_monotonic_samples:
            skipped_samples += part_non_monotonic_samples
            log.warning(
                f"skipped {part_non_monotonic_samples} non monotonic "
                f"samples for {part_desc}"
            )

        if part_failed_frames:
            skipped_samples += part_failed_frames
            log.warning(
                f"skipped {part_failed_frames} failed video frame "
                f"samples for {part_desc}"
            )

    if skipped_samples:
        log.warning(f"skipped {skipped_samples} for {sensor_desc}")

    duplicated_timestamps = sum(1 for count in seen_timestamps.values() if count > 1)
    if duplicated_timestamps:
        log.warning(f"found {duplicated_timestamps} for {sensor_desc}")


def all_valid_part_timestamps(recording_path, sensor):
    return list(
        skip_non_monotonic(
            chain(
                *(
                    timestamp_source["generator"]
                    for _, timestamp_source, _ in pi_sensor_part_sources(
                        recording_path, sensor
                    )
                )
            )
        )
    )


def matching_valid_eye_timestamps(recording_path):
    """
    Returns all monotonic left, right, matching timestamps for a recording
    """
    if is_neon(recording_path):
        timestamp_matches = ts_left = ts_right = all_valid_part_timestamps(
            recording_path, "Neon Sensor Module v1"
        )
    else:
        ts_left = all_valid_part_timestamps(recording_path, "PI left v1")
        ts_right = all_valid_part_timestamps(recording_path, "PI right v1")
        timestamp_matches = list(closest_matches_iterative(ts_left, ts_right))
    return {
        "closest": timestamp_matches,
        "left": ts_left,
        "right": ts_right,
    }


@dataclass
class VideoFrame:
    timestamp: int
    image: np.ndarray

    def __post_init__(self):
        self._resize_cache = {}

    def resized(self, size, interpolation: ResizeAlgorithm):
        key = (size, interpolation)
        if key not in self._resize_cache:
            self._resize_cache[key] = resize_image(self.image, size, interpolation)
        return self._resize_cache[key]


EyePair = T.Tuple[VideoFrame, VideoFrame]


@dataclass
class EyePairProcessor:
    """Class for processing eye pair frames"""

    name: str
    func: T.Any
    batch_size: int
    input: T.List[EyePair] = None
    output: T.List[T.Any] = None

    def __post_init__(self):
        self.input = []
        self.output = []

    def process(self):
        for eye_pairs in more_itertools.chunked(self.input, self.batch_size):
            self.output.extend(self.func(eye_pairs))
        self.input = []

    def put(self, eye_pair):
        self.input.append(eye_pair)
        if len(self.input) >= self.batch_size:
            # print(f"processing {len(self.input)} for {self.name}")
            self.process()


def is_neon(recording: Path) -> bool:
    metadata = json.loads((recording / "info.json").read_bytes())
    return metadata.get("data_format_version", "").startswith("2.")
