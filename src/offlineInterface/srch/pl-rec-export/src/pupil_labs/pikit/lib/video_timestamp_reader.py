import collections
import logging

import av

from .recording_parts import VideoPart
from .tools.iterfuncs import iter_with_next

logger = logging.getLogger(__name__)


# used frame duration in mjpeg/mp4 for last frame if no frame duration known
DEFAULT_FRAME_DURATION_S = 1 / 20


class VideoTimestampReader:
    """Factory class to select source for video frames and timestamps"""

    def __init__(
        self,
        video_part: VideoPart,
        strict_decoding: bool = False,
        times_from_time_files: bool = False,
    ):
        self.reader = self.get_video_timestamp_reader(
            video_part, strict_decoding, times_from_time_files
        )
        self.strict_decoding = strict_decoding

    @staticmethod
    def get_video_timestamp_reader(
        video_part: VideoPart,
        strict_decoding: bool,
        times_from_time_files: bool = False,
    ):
        is_mp4 = video_part.is_mp4

        if not is_mp4:
            return MjpegFileTimeReader(video_part, strict_decoding)

        if times_from_time_files:
            return MP4FileTimeReader(video_part, strict_decoding)

        return MP4FrameTimeReader(video_part, strict_decoding)

    @property
    def duration_ns(self):
        return self.reader.duration_ns

    @property
    def num_frames(self):
        return self.reader.num_frames

    @property
    def current_timestamp(self):
        return self.reader.current_timestamp

    def seek(self, timestamp_ns: int):
        self.reader.seek(timestamp_ns)

    def decode(self):
        return self.reader.decode()


class MjpegFileTimeReader:
    """
    Class to read a mjpeg sensor stream based on frames from mjpeg and
    timestamps from .time file

    Note:
    eye video mjpeg files are saved with constant fps, they do not resemble the
    actual frame timestamps, so all mjpeg video files use their according
    .time files to retrive the frame timestamps
    """

    def __init__(self, video_part: VideoPart, strict_decoding: bool):
        logger.info(f"mjpeg file time reader for {video_part}")
        self.__current_timestamp = video_part.start_epoch_ns
        self.video = video_part.video
        self.times = video_part.times

    @property
    def duration_ns(self):
        return int(
            (self.times[self.num_frames - 1] - self.times[0])
            + DEFAULT_FRAME_DURATION_S * 1e9
        )

    @property
    def num_frames(self):
        return min(self.video.n_frames_video, len(self.times))

    @property
    def current_timestamp(self):
        return self.__current_timestamp

    def seek(self, timestamp_ns):
        self.__current_timestamp = timestamp_ns

    def decode(self):
        # TODO use TurboJPEG
        self.video.container.seek(0)
        for (timestamp, frame), (next_timestamp, _) in iter_with_next(
            zip(self.times, self.video.container.decode(video=0)), (None, None)
        ):
            if next_timestamp and next_timestamp < self.__current_timestamp:
                continue

            duration = int(DEFAULT_FRAME_DURATION_S * 1e9)
            if next_timestamp:
                duration = next_timestamp - timestamp
            self.__current_timestamp = timestamp + duration
            yield timestamp, duration, frame


class MP4FileTimeReader:
    """
    Class to read an mp4 sensor stream based on frames from .mp4 file and
    timestamps from .time file

    Note:
    - Transcoded eye videos do save their frames with the variable fps frame
      timestamps, they accumulate however a shift, so it is recommended to use
      .time files for transcoded eye videos.
      Latest measurement of the shift is 6ms per 4 minute of recording

    - Transcoded world video files do have correct mp4 frame timestamps.

    """

    def __init__(self, video_part: VideoPart, strict_decoding: bool = False):
        logger.info(f"mp4 file time reader for {video_part}")
        self.__current_timestamp = video_part.start_epoch_ns
        self.video = video_part.video
        self.times = video_part.times
        self.strict_decoding = strict_decoding

    @property
    def duration_ns(self):
        return int(
            (self.times[self.num_frames - 1] - self.times[0])
            + DEFAULT_FRAME_DURATION_S * 1e9  # TODO
        )

    @property
    def num_frames(self):
        return min(self.video.n_frames_video, len(self.times))

    @property
    def current_timestamp(self):
        return self.__current_timestamp

    def seek(self, timestamp_ns):
        self.__current_timestamp = timestamp_ns

    def decode(self):
        self.video.container.seek(0)
        self.times.seek(0)
        timestamps = iter(self.times)
        prev_timestamp = None
        prev_frame = None
        current_index = 0
        for packet in self.video.container.demux(video=0):
            try:
                for frame in packet.decode():
                    timestamp = next(timestamps)

                    if timestamp and timestamp < self.__current_timestamp:
                        prev_timestamp = timestamp
                        prev_frame = frame
                        continue

                    if prev_timestamp and prev_frame:
                        self.__current_timestamp = timestamp

                        duration = timestamp - prev_timestamp
                        yield prev_timestamp, duration, prev_frame

                    current_index += 1

                    prev_timestamp = timestamp
                    prev_frame = frame

            except StopIteration:
                break
            except av.error.InvalidDataError as e:
                if self.strict_decoding:
                    raise
                logger.warning(f"decoding video frame error {e}")

        yield prev_timestamp, int(DEFAULT_FRAME_DURATION_S * 1e9), prev_frame


class MP4FrameTimeReader:
    """
    Class to read an mp4 sensor stream based on frames and timestamps from .mp4 file

    Note:
    Currently only transcoded world video files have correct timestamps, only for those
    this class should be used.
    """

    def __init__(self, video_part: VideoPart, strict_decoding: bool):
        logger.info(f"mp4 frame time reader for {video_part}")
        self.recording = video_part.recording
        self.video = video_part.video
        self.video_part_start_ns = video_part.start_epoch_ns
        self.strict_decoding = strict_decoding
        self.__current_timestamp = self.video_part_start_ns

    @property
    def duration_ns(self):
        return self.video.duration_ns

    @property
    def num_frames(self):
        return self.video.n_frames_video

    @property
    def current_timestamp(self):
        return self.__current_timestamp

    def seek(self, timestamp_ns: int):
        self.video.container.seek(
            int((timestamp_ns - self.video_part_start_ns) / 1e9 * av.time_base)
        )
        self.__current_timestamp = timestamp_ns

    def decode(self):
        prev_frame = None
        prev_timestamp = None
        for packet in self.video.container.demux(video=0):
            try:
                for frame in packet.decode():
                    # use frame pts as .time file might not be as precise
                    timestamp = (
                        int(frame.pts * frame.time_base * 1e9)
                        + self.video_part_start_ns
                    )
                    if prev_frame and prev_timestamp:
                        duration = timestamp - prev_timestamp
                        self.__current_timestamp = timestamp
                        result = AttributableTuple(
                            (prev_timestamp, duration, prev_frame)
                        )
                        result.source = self.video
                        yield result

                    prev_timestamp = timestamp
                    prev_frame = frame

            except av.error.InvalidDataError as e:
                if self.strict_decoding:
                    raise
                logger.warning(f"decoding video frame error {e}")
        if prev_frame and prev_timestamp:
            duration = int(self.video.last_frame_duration_video * 1e9)
            self.__current_timestamp = prev_timestamp + duration
            result = AttributableTuple((prev_timestamp, duration, prev_frame))
            result.source = self.video
            yield result


class AttributableTuple(tuple):
    """A wrapper for tuple that allows adding an attribute"""

    pass
