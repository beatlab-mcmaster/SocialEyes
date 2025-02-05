import datetime
import logging
import typing as T
from abc import ABC
from abc import abstractmethod
from abc import abstractproperty
from dataclasses import dataclass

import av
import more_itertools
import numpy as np

from . import stream_info
from .clickhouse_db import NoDBConnectionException
from .clickhouse_db import get_clickhouse_client
from .clickhouse_db import get_gaze_data
from .clickhouse_db import get_worn_data
from .recording_parts import ArrayPart
from .recording_parts import Part
from .recording_parts import VideoPart
from .stream_info import DEFAULT_NEON_AUDIO_STREAM_INFO
from .stream_info import DEFAULT_PI_AUDIO_STREAM_INFO
from .stream_info import AudioStreamInfo
from .stream_info import VideoStreamInfo
from .tools.iterfuncs import iter_with_next
from .util import cached_property
from .video_timestamp_reader import VideoTimestampReader

# from .video.frame_processor import FrameProcessor


logger = logging.getLogger(__name__)

MAX_TIMESTAMP = 2**63 - 1


@dataclass
class Point2D:
    __slots__ = ["x", "y"]
    x: float
    y: float

    def __add__(self, other):
        return Point2D(self.x + other.x, self.y + other.y)

    def __radd__(self, other):
        # to support sum(): # TODO
        if isinstance(other, int) and other == 0:
            return self
        return Point2D(self.x + other.x, self.y + other.y)

    def __mul__(self, factor):
        if isinstance(factor, (float, int)):
            self.x *= factor
            self.y *= factor
            return self

    def __rmul__(self, factor):
        if isinstance(factor, (float, int)):
            self.x *= factor
            self.y *= factor
            return self


@dataclass
class GazePosition:
    __slots__ = ["distorted", "normalized", "rectified"]
    distorted: Point2D
    normalized: Point2D
    rectified: Point2D


@dataclass
class Point3D:
    __slots__ = ["x", "y", "z"]
    x: float
    y: float
    z: float

    def __add__(self, other):
        return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __radd__(self, other):
        # to support sum(): # TODO
        if isinstance(other, int) and other == 0:
            return self
        return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, factor):
        if isinstance(factor, (float, int)):
            self.x *= factor
            self.y *= factor
            self.z *= factor
            return self

    def __rmul__(self, factor):
        if isinstance(factor, (float, int)):
            self.x *= factor
            self.y *= factor
            self.z *= factor
            return self


@dataclass
class Acceleration(Point3D):
    pass


@dataclass
class Gyroscope(Point3D):
    pass


@dataclass
class RecordingTimestamp(object):
    __slots__ = ["recording", "timestamp"]
    recording: None
    timestamp: int

    @property
    def offset_ns(self):
        return self.epoch_ns - self.recording.start_epoch_ns

    @property
    def datetime(self):
        return datetime.datetime.fromtimestamp(
            self.epoch_ns / 1e9, tz=datetime.timezone.utc
        )

    @property
    def offset_ms(self):
        return self.offset_ns / 1e6

    @property
    def offset_s(self):
        return self.offset_ns / 1e9

    @property
    def epoch_ns(self):
        return self.timestamp

    @property
    def epoch_s(self):
        return self.epoch_ns / 1e9

    def __lt__(self, other):
        if hasattr(other, "timestamp"):
            return self.timestamp < other.timestamp
        return self.timestamp < other

    def __le__(self, other):
        if hasattr(other, "timestamp"):
            return self.timestamp <= other.timestamp
        return self.timestamp <= other

    def __gt__(self, other):
        if hasattr(other, "timestamp"):
            return self.timestamp > other.timestamp
        return self.timestamp > other

    def __ge__(self, other):
        if hasattr(other, "timestamp"):
            return self.timestamp >= other.timestamp
        return self.timestamp >= other

    def __sub__(self, other):
        if isinstance(other, RecordingTimestamp):
            # RecordingTimestamp - RecordingTimestamp = duration
            return self.epoch_ns - other.epoch_ns
        if isinstance(other, int):
            # RecordingTimestamp - duration = RecoringTimestamp
            return RecordingTimestamp(self.recording, self.epoch_ns - other)

    def __add__(self, duration):
        assert isinstance(duration, int)
        return RecordingTimestamp(self.recording, self.epoch_ns + duration)


@dataclass
class Sample:
    __slots__ = ["recording", "timestamp", "duration"]
    recording: None
    timestamp: RecordingTimestamp
    duration: int

    @property
    def end_timestamp(self) -> RecordingTimestamp:
        return RecordingTimestamp(
            recording=self.recording, timestamp=self.timestamp.epoch_ns + self.duration
        )


@dataclass
class GazeSample(Sample):
    __slots__ = ["position"]
    position: GazePosition


@dataclass
class IMUSample(Sample):
    __slots__ = ["acceleration", "gyroscope"]
    acceleration: Acceleration
    gyroscope: Gyroscope


@dataclass
class WornSample(Sample):
    __slots__ = ["worn"]
    worn: int


@dataclass
class AudioFrame(Sample):
    __slots__ = ["av_frame"]
    av_frame: av.AudioFrame

    @staticmethod
    def padding_frame(stream_info: AudioStreamInfo) -> av.AudioFrame:
        """Silent audio frame used for padding when no audio sensor data is availble.

        Args:
            stream_info (AudioStreamInfo): audio stream info defining the format of
                the silent frame.

        Returns:
            av.AudioFrame: av audio frame containing slilence
        """
        av_frame = av.AudioFrame(
            samples=stream_info.frame_size,
            format=stream_info.av_format,
            layout=stream_info.av_layout,
        )
        av_frame.pts = None
        av_frame.sample_rate = stream_info.sample_rate

        for plane in av_frame.planes:
            buffer = np.frombuffer(plane, dtype=stream_info.dtype)
            buffer[:] = 0

        return av_frame


@dataclass
class VideoFrame(Sample):
    __slots__ = ["av_frame", "source"]
    av_frame: av.VideoFrame
    source: T.Any


class VideoFrameFactory:
    """Generate grey padding frames for world sensor disconnects"""

    def __init__(self, stream_info: VideoStreamInfo, frame_color: T.Tuple):
        """Video Frame Facotry for padding frames

        Args:
            stream_info (VideoStreamInfo): video stream info defining the format
                of the padding frame.
            frame_color (T.Tuple): rgb color values of the padding frame
        """
        self.stream_info = stream_info
        height, width = stream_info.format.height, stream_info.format.width
        grey_array = np.ones((height, width, 3)) * frame_color
        grey_array = grey_array.astype(np.uint8)
        self.frame = av.VideoFrame.from_ndarray(grey_array, format="rgb24")

    def padding_frame(self):
        return self.frame


@dataclass
class AlteringVideoFrame(VideoFrame):
    __slots__ = ["properties"]
    properties: set


class PartReader(ABC):
    @abstractproperty
    def start_epoch_ns(self) -> int:
        """Start timestamp in epoch ns"""
        pass

    @abstractproperty
    def end_epoch_ns(self) -> int:
        """End timestamp in epoch ns"""
        pass

    @abstractproperty
    def duration_ns(self) -> int:
        """Duration in nanoseconds"""
        pass

    @property
    def duration_s(self) -> int:
        """Duration in seconds"""
        return self.duration_ns / 1e9

    @abstractproperty
    def offset_ns(self) -> int:
        """Offset in ns"""
        pass

    @property
    def offset_s(self) -> int:
        """Offset in seconds"""
        return self.offset_ns / 1e9

    @abstractproperty
    def part(self) -> Part:
        """Part that is read

        Returns:
            Part: Sensor part
        """
        pass

    def __len__(self):
        raise NotImplementedError()

    @abstractmethod
    def decode(self) -> T.Sequence[T.Tuple]:
        """Decode data stream from raw files and yield a sequence of data"""
        pass

    @abstractmethod
    def seek(self, timestamp_ns: int):
        """Seek to timestamp

        Args:
            timestamp_ns (int): timestamp in epoch_ns
        """
        pass

    @abstractproperty
    def current_timestamp(self):
        """
        Approximate current timestamp after seeking, exact current timestamp
        after decoding

        Returns:
            int: timestamp in epoch_ns
        """
        pass

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in ["start_epoch_ns", "offset_s", "duration_s", "part"]
                ]
            )
            + ">"
        )


class VideoPartReader(PartReader):
    def __init__(
        self,
        video_part: VideoPart,
        times_from_time_files: bool,
        strict_decoding: bool = False,
    ):
        """
        VideoPartReader wraps a PI video part (video and timestamps)

        Args:
            video_part: The VideoPart
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        self.recording = video_part.recording
        self._video_part = video_part
        self.video = video_part.video
        self.times = video_part.times

        self._video_time_reader = VideoTimestampReader(
            video_part, strict_decoding, times_from_time_files=times_from_time_files
        )

    @property
    def start_epoch_ns(self) -> int:
        return self._video_part.start_epoch_ns

    @property
    def end_epoch_ns(self) -> int:
        return self.start_epoch_ns + self.duration_ns

    @property
    def offset_ns(self) -> int:
        return self._video_part.offset_ns

    @property
    def current_timestamp(self) -> int:
        return self._video_time_reader.current_timestamp

    @property
    def duration_ns(self):
        return self._video_time_reader.duration_ns

    @property
    def part(self):
        return self._video_part

    def __len__(self):
        return self._video_time_reader.num_frames

    def decode(self) -> T.Sequence[T.Tuple[int, int, av.VideoFrame]]:
        """Decode video stream

        Yields:
            Iterator[T.Sequence[T.Tuple[int, int, av.VideoFrame]]]: yields (timestamp
                in epoch_ns, duration in ns, av.VideoFrame) for every frame
        """
        return self._video_time_reader.decode()

    def seek(self, timestamp_ns: int):
        self._video_time_reader.seek(timestamp_ns)


class VideoGapReader(PartReader):
    GAP_FPS = 20
    GAP_FRAME_COLOR = (100, 100, 100)

    def __init__(
        self,
        recording,
        stream_info: VideoStreamInfo,
        start_epoch_ns: int,
        end_epoch_ns: int,
    ):
        self.recording = recording
        self.__start_epoch_ns = start_epoch_ns
        self.__end_epoch_ns = end_epoch_ns
        self.times = list(
            range(
                self.start_epoch_ns,
                self.end_epoch_ns,
                int(1 / VideoGapReader.GAP_FPS * 1e9),
            )
        )
        self.frame_factory = VideoFrameFactory(
            stream_info, VideoGapReader.GAP_FRAME_COLOR
        )
        self.__current_timestamp = self.start_epoch_ns

    @property
    def start_epoch_ns(self) -> int:
        return self.__start_epoch_ns

    @property
    def offset_ns(self) -> int:
        return self.start_epoch_ns - self.recording.start_epoch_ns

    @property
    def end_epoch_ns(self) -> int:
        return self.__end_epoch_ns

    @property
    def duration_ns(self) -> int:
        return self.end_epoch_ns - self.start_epoch_ns

    @property
    def part(self) -> Part:
        return None

    def __len__(self):
        return len(self.times)

    def decode(self) -> T.Sequence[T.Tuple[int, int, av.VideoFrame]]:
        """Decode video gap data

        Yields:
            Iterator[T.Sequence[T.Tuple[int, int, av.VideoFrame]]]: yields (timestamp
                in epoch_ns, duration in ns, av.VideoFrame) for every frame
        """
        for time, next_time in iter_with_next(self.times, self.end_epoch_ns):
            if next_time < self.__current_timestamp:
                continue
            duration = next_time - time
            video_frame = self.frame_factory.padding_frame()
            self.__current_timestamp = time + duration
            yield time, duration, video_frame

    def seek(self, timestamp_ns: int):
        self.__current_timestamp = timestamp_ns

    @property
    def current_timestamp(self) -> int:
        return self.__current_timestamp


class AudioPartReader(PartReader):
    def __init__(self, video_part: VideoPart, strict_decoding=False):
        """
        AudioPartReader wraps a PI video sensor (audio and timestamps)

        Args:
            video_part: The VideoPart containing the audio
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        self._video_part = video_part
        self.recording = video_part.recording
        self.times = video_part.times
        self.video = video_part.video
        self.strict_decoding = strict_decoding
        self.__current_timestamp = self.start_epoch_ns

    @property
    def start_epoch_ns(self) -> int:
        return self.times[0]

    @property
    def end_epoch_ns(self) -> int:
        return self.start_epoch_ns + self.duration_ns

    @property
    def offset_ns(self) -> int:
        return self._video_part.offset_ns

    @property
    def duration_ns(self) -> int:
        return self.video.duration_audio_ns

    @property
    def part(self):
        return self._video_part

    def __len__(self):
        return self.video.n_frames_audio

    def decode(self) -> T.Sequence[T.Tuple[int, int, av.AudioFrame]]:
        """Decode mp4 audio stream

        Yields:
            Iterator[T.Sequence[T.Tuple[int, int, av.AudioFrame]]]: yields (timestamp
                in epoch_ns, duration in ns, av.AudioFrame) for every frame
        """
        for packet in self.video.container.demux(audio=0):
            try:
                for frame in packet.decode():
                    timestamp = (
                        int(frame.pts * frame.time_base * 1e9) + self.start_epoch_ns
                    )
                    duration = int(packet.duration * packet.time_base * 1e9)
                    self.__current_timestamp = timestamp + duration
                    yield timestamp, duration, frame
            except av.error.InvalidDataError as e:
                if self.strict_decoding:
                    raise
                logger.warning(f"failed to decode audio frame {e}")
        self.video.container.seek(0)

    def seek(self, timestamp_ns: int):
        self.video.container.seek(
            int((timestamp_ns - self.start_epoch_ns) / 1e9 * av.time_base)
        )
        # exact current timestamp only after first decode
        self.__current_timestamp = timestamp_ns

    @property
    def current_timestamp(self) -> int:
        return self.__current_timestamp


class AudioGapReader(PartReader):
    def __init__(self, recording, stream_info, start_epoch_ns, end_epoch_ns):
        self.recording = recording
        self.__start_epoch_ns = start_epoch_ns
        self.__end_epoch_ns = end_epoch_ns
        self.stream_info = stream_info

        self.__frame_durations = self.__compute_frame_durations()

        self.__current_timestamp = self.start_epoch_ns

    @property
    def start_epoch_ns(self) -> int:
        return self.__start_epoch_ns

    @property
    def end_epoch_ns(self) -> int:
        return self.__end_epoch_ns

    @property
    def offset_ns(self) -> int:
        return self.start_epoch_ns - self.recording.start_epoch_ns

    @property
    def duration_ns(self) -> int:
        return self.end_epoch_ns - self.start_epoch_ns

    @property
    def part(self) -> Part:
        return None

    def __len__(self):
        return len(self.__frame_durations)

    def __compute_frame_durations(self):
        sample_count = int(
            round(
                self.stream_info.sample_rate
                * max(0, self.end_epoch_ns - self.start_epoch_ns)
                / 1e9
            )
        )
        num_full_samples = sample_count // self.stream_info.frame_size

        full_gap_frame_duration = int(
            self.stream_info.frame_size * 1e9 / self.stream_info.sample_rate
        )
        last_duration = int(
            self.duration_ns - num_full_samples * full_gap_frame_duration
        )
        frame_durations = num_full_samples * [full_gap_frame_duration] + [last_duration]
        return frame_durations

    def decode(self) -> T.Sequence[T.Tuple[int, int, av.AudioFrame]]:
        """Decode audio gap data

        Yields:
            Iterator[T.Sequence[T.Tuple[int, int, av.AudioFrame]]]: yields (timestamp
                in epoch_ns, duration in ns, av.AudioFrame) for every frame
        """
        current_time = self.start_epoch_ns
        for frame_duration in self.__frame_durations:
            start_time = current_time
            end_time = start_time + frame_duration

            if end_time > self.__current_timestamp:
                # use start_time, as we need the first overlapping audio sample as well
                audio_frame = AudioFrame.padding_frame(self.stream_info)
                self.__current_timestamp = start_time + frame_duration
                yield start_time, frame_duration, audio_frame
            current_time = end_time

    def seek(self, timestamp_ns: int):
        self.__current_timestamp = timestamp_ns

    @property
    def current_timestamp(self) -> int:
        return self.__current_timestamp


class ArrayPartReader(PartReader):
    def __init__(self, array_part: ArrayPart, max_duration_ns=50 * 1e6):
        self._array_part = array_part
        self.recording = array_part.recording
        self.values = array_part.values
        self.times = array_part.times
        self.max_duration_ns = int(max_duration_ns)
        self.__current = 0
        self.__current_timestamp = self.start_epoch_ns

    @property
    def start_epoch_ns(self) -> int:
        return self._array_part.start_epoch_ns

    @property
    def end_epoch_ns(self) -> int:
        return self.times[len(self) - 1] + self.max_duration_ns

    @property
    def offset_ns(self) -> int:
        return self._array_part.offset_ns

    @property
    def duration_ns(self) -> int:
        return self.end_epoch_ns - self.start_epoch_ns

    @property
    def part(self) -> Part:
        return self._array_part

    def __len__(self):
        return min(self._array_part.n_samples, self._array_part.n_timestamps)

    def decode(self) -> T.Sequence[T.Tuple[int, int, dict]]:
        """Decode raw data stream

        Yields:
            Iterator[T.Sequence[T.Tuple[int, int, T.Dict]]]: yields (timestamp
                in epoch_ns, duration in ns, raw data row) for every frame
        """
        start = self.__current
        for (timestamp, value), (next_timestamp, _) in iter_with_next(
            zip(self.times.iter_slice(start), self.values.iter_slice(start)),
            (None, None),
        ):
            duration = self.max_duration_ns
            if next_timestamp:
                duration = min(self.max_duration_ns, next_timestamp - timestamp)
            self.__current += 1
            self.__current_timestamp = timestamp + duration
            yield timestamp, duration, value

    def seek(self, timestamp_ns: int):
        # seek somewhere close before requested timestamp
        self.times.seek(0)
        self.values.seek(0)
        average_time_diff = (self.end_epoch_ns - self.start_epoch_ns) / len(self.times)
        approximate_position = max(
            0, int((timestamp_ns - self.start_epoch_ns) / average_time_diff)
        )

        t = self.times.seek(approximate_position)
        self.__current = approximate_position
        while t > timestamp_ns:
            num_steps = max(1, int((t - timestamp_ns) / average_time_diff))
            t = self.times.seek(self.__current - num_steps)
            self.__current -= num_steps
            if self.__current < 0:
                self.__current = 0
                self.__current_timestamp = self.start_epoch_ns
                break
        # exact current timestamp only known after first decode
        self.__current_timestamp = t

    @property
    def current_timestamp(self) -> int:
        return self.__current_timestamp


class MultiPartReader(ABC):
    def __init__(
        self, recording, part_readers: T.Sequence[PartReader], sensor_name: str
    ):
        """
        Wraps a sequence of PartReaders and takes care of multi part reading

        Args:
            recording (Recording): recording, this multi part reader reads a sensor
                stream from
            part_readers (T.Sequence[PartReader]): Sequence of PartReaders, one for
                every sensor part
        """
        self.recording = recording
        self.part_readers = part_readers
        self.sensor_name = sensor_name

        self._decoders = [s.decode() for s in self.part_readers]
        self.__current_timestamp = recording.start_epoch_ns

    def __iter__(self):
        for decoder in self._decoders:
            for sample in decoder:
                timestamp, duration, data = sample
                self.__current_timestamp = timestamp + duration
                yield sample

    def seek(self, timestamp_ns: int):
        """Seek to timestamp

        Args:
            timestamp_ns (int): timestamp in epoch_ns
        """
        # find sensor data from seeking position onward and seek inside first
        # sensor_part to starting position
        self.__current_timestamp = timestamp_ns
        self._decoders = []
        for part_reader in self.part_readers:
            if part_reader.end_epoch_ns <= timestamp_ns:
                continue
            if part_reader.start_epoch_ns <= timestamp_ns < part_reader.end_epoch_ns:
                part_reader.seek(timestamp_ns)
            else:
                part_reader.seek(part_reader.start_epoch_ns)
            self._decoders.append(part_reader.decode())

    @property
    def current_timestamp(self) -> int:
        """approximate current timestamp after seek, exact current timestamp after first decode

        Returns:
            int: timestamp in epoch_ns
        """
        return self.__current_timestamp

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in ["sensor_name", "part_readers"]
                ]
            )
            + ">"
        )


class BaseSensor(ABC):
    @abstractproperty
    def sensor_part_readers(self) -> T.List[PartReader]:
        """
        Sensor part readers for all valid sensor parts

        Returns:
            T.List[PartReader]: List of PartReader
        """
        pass

    @abstractproperty
    def _multi_part_reader(self) -> MultiPartReader:
        """
        Wrap all valid sensor parts to allow seeking and reading without having to
        handle multi part files manually
        """
        pass

    @abstractmethod
    def _data_to_sample(self, timestmap, data, source=None):
        pass

    def seek(self, timestamp: int):
        """Seek to timestamp

        Args:
            timestamp_ns (int): timestamp in epoch_ns
        """
        self._multi_part_reader.seek(timestamp)

    @property
    def current_timestamp(self) -> int:
        """approximate current timestamp

        Returns:
            int: timestamp in epoch_ns
        """
        return self._multi_part_reader.current_timestamp

    def __iter__(self) -> T.Iterator[Sample]:
        """Iter sensor samples

        Returns:
            T.Iterator[Sample]: Sensor samples
        """
        for sample in self._multi_part_reader:
            timestamp, duration, data = sample
            source = getattr(sample, "source", None)
            yield self._data_to_sample(timestamp, duration, data, source=source)

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[Sample]:
        """Read sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[Sample]: Data samples
        """
        previous_position = self.current_timestamp
        self.seek(min_timestamp)
        for sample in self._multi_part_reader:
            source = getattr(sample, "source", None)
            timestamp, duration, data = sample
            if timestamp > max_timestamp:
                break
            if timestamp + duration < min_timestamp:
                continue

            yield self._data_to_sample(timestamp, duration, data, source=source)
        self.seek(previous_position)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> Sample:
        """Get closest data samples to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            Sample: Data sample
        """
        previous_position = self.current_timestamp
        self.seek(max(0, timestamp - max_time_difference_ns))
        min_distance = MAX_TIMESTAMP
        data_sample = None, None, None
        for t, duration, data in self._multi_part_reader:
            time_distance = abs(timestamp - t)
            if time_distance < min_distance:
                min_distance = time_distance
                data_sample = t, duration, data
            else:
                self.seek(previous_position)
                if min_distance <= max_time_difference_ns:
                    return self._data_to_sample(*data_sample)
                return None

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in ["recording", "sensor_part_readers"]
                ]
            )
            + ">"
        )


class WorldSensor(BaseSensor):
    def __init__(
        self,
        recording,
        fill_gaps=True,
        times_from_time_files: bool = False,
        strict_decoding: bool = False,
    ):
        """
        WorldSensor is a sensor that wraps the world video parts for a recording

        Args:
            recording: Recording this sensor belongs to
            fill_gaps: Fill gaps with artificial frames
            times_from_time_files: Read timestamps from .time files instead of using
                timestmaps from mp4 frames
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        super().__init__()
        self.recording = recording
        self.strict_decoding = strict_decoding
        self.times_from_time_files = times_from_time_files
        self.parts = self.recording.recording_parts.world
        self.__data_parts = self.__init_data_parts()
        self.padded_sensor_part_readers = None
        if fill_gaps:
            self.padded_sensor_part_readers = self.__fill_gaps(self.__data_parts)
            self.__multi_part_reader = MultiPartReader(
                self.recording, self.padded_sensor_part_readers, sensor_name="world"
            )
        else:
            self.__multi_part_reader = MultiPartReader(
                self.recording, self.__data_parts, sensor_name="world"
            )

    def __init_data_parts(self) -> T.List[VideoPartReader]:
        video_sensor_parts = []
        for world_part in self.parts:
            if not world_part.is_valid_part:
                continue
            video_sensor_part = VideoPartReader(
                world_part,
                times_from_time_files=self.times_from_time_files,
                strict_decoding=self.strict_decoding,
            )
            video_sensor_parts.append(video_sensor_part)
        return video_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[VideoPartReader]:
        """
        Video part readers for all valid world sensor parts

        Returns:
            T.List[VideoPartReader]: One VideoPartReader for every valid world part
        """
        return self.__data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        """
        Wrap world part readers to allow seeking and reading without having to
        handle multi part files manually. Gaps between sensor parts are padded with
        VideoGapReader [Gray frames at fixed fps]

        Returns:
            MultiPartReader: Multi part world sensor data
        """
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> VideoFrame:
        return VideoFrame(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            av_frame=data,
            source=source,
        )

    @cached_property
    def video_info(self) -> VideoStreamInfo:
        for world_part in self.sensor_part_readers:
            if world_part.video and world_part.video.is_mp4:
                # use the first available video stream to retrieve video stream info
                return world_part.video.video_info

        logger.warning("no world video mp4 stream, use default stream info")
        if self.recording.family == "neon":
            return stream_info.DEFAULT_NEON_VIDEO_STREAM_INFO
        return stream_info.DEFAULT_PI_VIDEO_STREAM_INFO

    def __fill_gaps(
        self, video_sensor_parts: T.List[VideoPartReader]
    ) -> T.List[PartReader]:
        padded_sensor_parts = []
        current_timestamp = self.recording.start_epoch_ns
        for sensor_part in video_sensor_parts:
            if current_timestamp < sensor_part.start_epoch_ns:
                gap_data = VideoGapReader(
                    self.recording,
                    self.video_info,
                    current_timestamp,
                    sensor_part.start_epoch_ns,
                )
                padded_sensor_parts.append(gap_data)
            padded_sensor_parts.append(sensor_part)
            current_timestamp = sensor_part.end_epoch_ns

        if current_timestamp < self.recording.end_epoch_ns:
            gap_data = VideoGapReader(
                self.recording,
                self.video_info,
                current_timestamp,
                self.recording.end_epoch_ns,
            )
            padded_sensor_parts.append(gap_data)

        return padded_sensor_parts

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[VideoFrame]:
        """Read world sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[VideoFrame]: Data samples
        """
        return super().read(min_timestamp=min_timestamp, max_timestamp=max_timestamp)

    def __iter__(self) -> T.Iterator[VideoFrame]:
        """Iter world sensor

        Yields:
            T.Iterator[VideoFrame]: Video frames of this sensor
        """
        return super().__iter__()

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> VideoFrame:
        """Get closest world frame to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            VideoFrame: video frame sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in [
                        "recording",
                        "sensor_part_readers",
                        "padded_sensor_part_readers",
                    ]
                ]
            )
            + ">"
        )


class WorldSensorProcessor(WorldSensor):
    def __init__(
        self,
        recording,
        processors,
        fill_gaps=True,
        times_from_time_files: bool = False,
        strict_decoding: bool = False,
    ):
        """
        (Experimental)
        WorldSensorProcessor is a sensor that wraps the world video parts for a
        recording and applies additional processing to the frames.

        Args:
            recording: Recording this sensor belongs to
            fill_gaps: Fill gaps with artificial frames
            times_from_time_files: Read timestamps from .time files instead of using
                timestmaps from mp4 frames
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        super().__init__(
            recording,
            fill_gaps=fill_gaps,
            times_from_time_files=times_from_time_files,
            strict_decoding=strict_decoding,
        )
        self.processors = processors

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> AlteringVideoFrame:
        from .tools.video.frame_processors import FrameType

        video_frame = AlteringVideoFrame(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            av_frame=data,
            properties={FrameType.DISTORTED},
            source=source,
        )
        processed_frame = self.process_frame(video_frame)
        return processed_frame

    def process_frame(self, video_frame: AlteringVideoFrame) -> AlteringVideoFrame:
        for processor in self.processors:
            video_frame = processor(video_frame)
        return video_frame

    def add_processors(self, processors: T.List):
        self.processors.extend(processors)


class AudioSensor(BaseSensor):
    def __init__(self, recording, fill_gaps=True, strict_decoding=False):
        """
        AudioSensor is a sensor that wraps the world audio parts for a recording

        Args:
            recording: Recording this sensor belongs to
            fill_gaps: Fill gaps with silence
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        super().__init__()
        self.strict_decoding = strict_decoding
        self.recording = recording
        self.parts = self.recording.recording_parts.audio
        self.__data_parts = self.__init_data_parts()
        self.padded_sensor_part_readers = None
        if fill_gaps:
            self.padded_sensor_part_readers = self.__fill_gaps(self.__data_parts)
            self.__multi_part_reader = MultiPartReader(
                self.recording, self.padded_sensor_part_readers, sensor_name="audio"
            )
        else:
            self.__multi_part_reader = MultiPartReader(
                self.recording, self.__data_parts, sensor_name="audio"
            )

    def __init_data_parts(self) -> T.List[AudioPartReader]:
        video_sensor_parts = []
        for audio_part in self.parts:
            if not audio_part.is_valid_part:
                continue
            if not audio_part.has_audio:
                continue

            video_sensor_part = AudioPartReader(
                audio_part, strict_decoding=self.strict_decoding
            )
            video_sensor_parts.append(video_sensor_part)
        return video_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[AudioPartReader]:
        """
        Video part readers for all valid audio sensor parts

        Returns:
            T.List[AudioPartReader]: One AudioPartReader for every valid audio part
        """
        return self.__data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        """
        Wrap all valid audio sensor parts to allow seeking and reading without having to
        handle multi part files manually. Gaps between sensor parts are padded with
        AudioGapReader [silent frames]

        Returns:
            MultiPartReader: Multi part audio sensor data
        """
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> AudioFrame:
        return AudioFrame(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            av_frame=data,
        )

    @cached_property
    def audio_info(self) -> AudioStreamInfo:
        if self.recording.has_audio:
            for data_part in self.sensor_part_readers:
                if data_part.video.has_audio:
                    return data_part.video.audio_info

        if self.recording.family == "neon":
            return DEFAULT_NEON_AUDIO_STREAM_INFO
        return DEFAULT_PI_AUDIO_STREAM_INFO

    def __fill_gaps(
        self, audio_data_parts: T.List[AudioPartReader]
    ) -> T.List[PartReader]:
        padded_data_parts = []
        current_timestamp = self.recording.start_epoch_ns

        for sensor_part in audio_data_parts:
            if current_timestamp < sensor_part.start_epoch_ns:
                gap_data = AudioGapReader(
                    self.recording,
                    self.audio_info,
                    current_timestamp,
                    sensor_part.start_epoch_ns,
                )
                padded_data_parts.append(gap_data)
            padded_data_parts.append(sensor_part)
            current_timestamp = sensor_part.end_epoch_ns

        if current_timestamp < self.recording.end_epoch_ns:
            gap_data = AudioGapReader(
                self.recording,
                self.audio_info,
                current_timestamp,
                self.recording.end_epoch_ns,
            )
            padded_data_parts.append(gap_data)

        return padded_data_parts

    def __iter__(self) -> T.Iterator[AudioFrame]:
        """Iter audio sensor

        Yields:
            T.Iterator[AudioFrame]: Audio frames of this sensor
        """
        return super().__iter__()

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[AudioFrame]:
        """
        Read audio sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[AudioFrame]: Data samples
        """
        return super().read(min_timestamp=min_timestamp, max_timestamp=max_timestamp)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> AudioFrame:
        """Get closest audio frame to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            AudioFrame: audio frame sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in [
                        "recording",
                        "sensor_part_readers",
                        "padded_sensor_part_readers",
                    ]
                ]
            )
            + ">"
        )


class EyeSensor(BaseSensor):
    def __init__(
        self,
        recording,
        eye: str,
        times_from_time_files: bool = True,
        strict_decoding: bool = False,
        fill_gaps=False,
    ):
        """
        EyeSensor is a sensor that wraps the eye parts for a recording

        Args:
            recording: Recording this sensor belongs to
            eye: which eye this sensor is for (left/right)
            times_from_time_files: Read timestamps from .time files instead of using
                timestmaps from mp4 frames
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """

        super().__init__()
        self.recording = recording
        self.strict_decoding = strict_decoding
        self.times_from_time_files = times_from_time_files
        if eye == "left":
            self.parts = self.recording.recording_parts.eye_left
        elif eye == "right":
            self.parts = self.recording.recording_parts.eye_right
        else:
            raise ValueError(
                f'invalid value for eye {repr(eye)}, must be one "left" or "right"'
            )

        self.__data_parts = self.__init_data_parts()
        self.padded_sensor_part_readers = None
        if fill_gaps:
            self.padded_sensor_part_readers = self.__fill_gaps(self.sensor_part_readers)
            self.__multi_part_reader = MultiPartReader(
                self.recording,
                self.padded_sensor_part_readers,
                sensor_name=f"eye_{eye}",
            )
        else:
            self.__multi_part_reader = MultiPartReader(
                self.recording, self.sensor_part_readers, sensor_name=f"eye_{eye}"
            )

    def __init_data_parts(self) -> T.List[VideoPartReader]:
        video_sensor_parts = []
        for eye_part in self.parts:
            if not eye_part.is_valid_part:
                continue

            video_sensor_part = VideoPartReader(
                eye_part,
                times_from_time_files=self.times_from_time_files,
                strict_decoding=self.strict_decoding,
            )

            video_sensor_parts.append(video_sensor_part)
        return video_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[VideoPartReader]:
        """
        Video part readers for all valid eye sensor parts

        Returns:
            T.List[VideoPartReader]: One VideoPartReader for every valid eye part
        """
        return self.__data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> VideoFrame:
        return VideoFrame(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            av_frame=data,
            source=source,
        )

    @cached_property
    def video_info(self) -> VideoStreamInfo:
        for eye_part in self.sensor_part_readers:
            if eye_part.video and eye_part.video.is_mp4:
                # use the first available video stream to retrieve video stream info
                return eye_part.video.video_info

        logger.warning("no eye video mp4 stream, use default stream info")
        return stream_info.DEFAULT_EYE_VIDEO_STREAM_INFO

    def __fill_gaps(
        self, video_sensor_parts: T.List[VideoPartReader]
    ) -> T.List[PartReader]:
        padded_sensor_parts = []
        current_timestamp = self.recording.start_epoch_ns
        for sensor_part in video_sensor_parts:
            if current_timestamp < sensor_part.start_epoch_ns:
                gap_data = VideoGapReader(
                    self.recording,
                    self.video_info,
                    current_timestamp,
                    sensor_part.start_epoch_ns,
                )
                padded_sensor_parts.append(gap_data)
            padded_sensor_parts.append(sensor_part)
            current_timestamp = sensor_part.end_epoch_ns

        if current_timestamp < self.recording.end_epoch_ns:
            gap_data = VideoGapReader(
                self.recording,
                self.video_info,
                current_timestamp,
                self.recording.end_epoch_ns,
            )
            padded_sensor_parts.append(gap_data)

        return padded_sensor_parts

    def __iter__(self) -> T.Iterator[VideoFrame]:
        """Iter eye sensor

        Yields:
            T.Iterator[VideoFrame]: Video frames of this sensor
        """
        return super().__iter__()

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[VideoFrame]:
        """Read eye sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[VideoFrame]: Data samples
        """
        return super().read(min_timestamp=min_timestamp, max_timestamp=max_timestamp)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> VideoFrame:
        """Get closest eye frame to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            VideoFrame: video frame sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in [
                        "recording",
                        "sensor_part_readers",
                        "padded_sensor_part_readers",
                    ]
                ]
            )
            + ">"
        )


class GazeSensor(BaseSensor):
    def __init__(self, recording, max_duration_ns=50 * 1e6):
        """
        Gaze is a sensor that wraps the gaze parts for a recording

        Args:
            recording: Recording this sensor belongs to
            max_duration_ns: maximum duration between 2 data samples without
                classifying it as a gap/disconnect
        """
        super().__init__()
        self.recording = recording
        self.max_duration_ns = max_duration_ns
        self.parts = self.recording.recording_parts.gaze
        self._current_timestamp = recording.start_epoch_ns
        self._data_parts = self._init_data_parts()
        self.__multi_part_reader = MultiPartReader(
            self.recording, self.sensor_part_readers, sensor_name="gaze"
        )

    def _init_data_parts(self) -> T.List[ArrayPartReader]:
        array_sensor_parts = []
        for gaze_part in self.parts:
            if not gaze_part.is_valid_part:
                continue

            array_sensor_part = ArrayPartReader(
                gaze_part, max_duration_ns=self.max_duration_ns
            )
            array_sensor_parts.append(array_sensor_part)
        return array_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[ArrayPartReader]:
        """
        Array part readers for all valid gaze sensor parts

        Returns:
            T.List[ArrayPartReader]: One ArrayPartReader for every valid gaze part
        """
        return self._data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> GazeSample:
        normalized = self.recording.scene_camera.normalize_point((data["x"], data["y"]))
        rectified = self.recording.scene_camera.rectify_point(
            normalized_point=(normalized[0], normalized[1])
        )
        sample = GazeSample(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            position=GazePosition(
                distorted=Point2D(data["x"], data["y"]),
                normalized=Point2D(normalized[0], normalized[1]),
                rectified=Point2D(rectified[0], rectified[1]),
            ),
        )
        return sample

    @property
    def current_timestamp(self) -> int:
        return self._current_timestamp

    def __iter__(self) -> T.Iterator[GazeSample]:
        """Iter gaze sensor

        Yields:
            T.Iterator[GazeSample]: Gaze samples of this sensor
        """
        # # timing of 540445 gaze points = 1 hour recording, no densified gaze
        #
        # # with bulk normalization, batchsize=100000
        # >>> %timeit -n1  a = list(recording.gaze); recording.gaze.seek(0)
        # 3.07 s ± 411 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)
        #
        # # without bulk normalization:
        # >>> %timeit -n1  a = list(recording.gaze); recording.gaze.seek(0)
        # 37.5 s ± 1.02 s per loop (mean ± std. dev. of 7 runs, 1 loop each)

        batchsize = 100_000
        for batch in more_itertools.chunked(self._multi_part_reader, n=batchsize):
            distorted_points = [(sample["x"], sample["y"]) for _, _, sample in batch]
            normalized_points = self.recording.scene_camera.normalize_points(
                distorted_points
            )
            rectified_points = self.recording.scene_camera.rectify_points(
                normalized_points=normalized_points
            )
            for sensor_part_datum, d_point, n_point, r_point in zip(
                batch, distorted_points, normalized_points, rectified_points
            ):
                timestamp, duration, _ = sensor_part_datum
                self._current_timestamp = timestamp + duration
                yield GazeSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                    position=GazePosition(
                        distorted=Point2D(*d_point),
                        normalized=Point2D(*n_point),
                        rectified=Point2D(*r_point),
                    ),
                )

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[GazeSample]:
        """Read gaze data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            Iterator[T.Iterator[GazeSample]]: Data samples
        """
        previous_position = self.current_timestamp
        self.seek(min_timestamp)
        batchsize = 100_000
        for batch in more_itertools.chunked(self._multi_part_reader, n=batchsize):
            distorted_points = [(sample["x"], sample["y"]) for _, _, sample in batch]
            normalized_points = self.recording.scene_camera.normalize_points(
                distorted_points
            )
            rectified_points = self.recording.scene_camera.rectify_points(
                normalized_points=normalized_points
            )
            for sensor_part_datum, d_point, n_point, r_point in zip(
                batch, distorted_points, normalized_points, rectified_points
            ):
                timestamp, duration, _ = sensor_part_datum
                if timestamp > max_timestamp:
                    break
                if timestamp + duration < min_timestamp:
                    continue
                self._current_timestamp = timestamp + duration
                yield GazeSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                    position=GazePosition(
                        distorted=Point2D(*d_point),
                        normalized=Point2D(*n_point),
                        rectified=Point2D(*r_point),
                    ),
                )

        self.seek(previous_position)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> GazeSample:
        """Get closest gaze sample to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            GazeSample: gaze sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)


class Gaze200Sensor(GazeSensor):
    def __init__(self, recording, max_duration_ns=50 * 1e6):
        self.recording = recording
        self.max_duration_ns = max_duration_ns
        self.parts = self.recording.recording_parts.gaze200
        self._current_timestamp = recording.start_epoch_ns
        self._data_parts = self._init_data_parts()
        self.__multi_part_reader = MultiPartReader(
            self.recording, self.sensor_part_readers, sensor_name="gaze200"
        )

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        return self.__multi_part_reader


class Gaze200DBSensor(GazeSensor):
    def __init__(self, recording, max_duration_ns=50 * 1e6):
        self.recording = recording
        self.max_duration_ns = max_duration_ns
        self._current_timestamp = recording.start_epoch_ns

        if not get_clickhouse_client():
            raise NoDBConnectionException("No connection to database")
        self.__seek = self.recording.start_epoch_ns

    @property
    def sensor_part_readers(self):
        """Gaze from DB does not have any parts

        Returns:
            None
        """
        return None  # TODO ?

    def seek(self, timestamp_ns: int):
        self._current_timestamp = timestamp_ns
        self.__seek = timestamp_ns

    @property
    def _multi_part_reader(self):
        return get_gaze_data(self.recording, start_epoch_ns=self.__seek)

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[Sample]:
        gaze_data = get_gaze_data(
            self.recording, start_epoch_ns=min_timestamp, end_epoch_ns=max_timestamp
        )

        batchsize = 100_000
        for batch in more_itertools.chunked(gaze_data, n=batchsize):
            normalized_points = [
                (undist_x, undist_y) for _, undist_x, undist_y in batch
            ]
            distorted_points = self.recording.scene_camera.distort_points(
                normalized_points
            )
            rectified_points = self.recording.scene_camera.rectify_points(
                normalized_points=normalized_points
            )
            for (
                (sensor_part_datum, d_point, n_point, r_point),
                next_data,
            ) in iter_with_next(
                zip(batch, distorted_points, normalized_points, rectified_points)
            ):
                timestamp, _, _ = sensor_part_datum
                duration = self.max_duration_ns
                if next_data:
                    next_db_sample, _, _, _ = next_data
                    next_timestamp = next_db_sample[0]
                    duration = min(next_timestamp - timestamp, self.max_duration_ns)
                self._current_timestamp = timestamp + duration

                yield GazeSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                    position=GazePosition(
                        distorted=Point2D(*d_point),
                        normalized=Point2D(*n_point),
                        rectified=Point2D(*r_point),
                    ),
                )

    def __iter__(self) -> T.Iterator[GazeSample]:
        """Iter world sensor

        Yields:
            T.Iterator[GazeSample]: Gaze samples of this sensor
        """
        return super().__iter__()
        # Timing of 1081080 (1 hour recording with 200hz gaze) from
        # Clickhouse db on hetzner:
        # >>> %timeit -n1  a = list(recording.gaze200); recording.gaze200.seek(0)
        # 6.91 s ± 321 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)

        batchsize = 500_000
        for batch in more_itertools.chunked(self._multi_part_reader, n=batchsize):
            normalized_points = [
                (undist_x, undist_y) for _, undist_x, undist_y in batch
            ]
            distorted_points = self.recording.scene_camera.distort_points(
                normalized_points
            )
            rectified_points = self.recording.scene_camera.rectify_points(
                normalized_points=normalized_points
            )
            for (
                (sensor_part_datum, d_point, n_point, r_point),
                next_data,
            ) in iter_with_next(
                zip(batch, distorted_points, normalized_points, rectified_points)
            ):
                timestamp, _, _ = sensor_part_datum
                duration = self.max_duration_ns
                if next_data:
                    next_db_sample, _, _, _ = next_data
                    next_timestamp = next_db_sample[0]
                    duration = min(next_timestamp - timestamp, self.max_duration_ns)

                self.__current_timestamp = timestamp + duration
                self.__seek = self.__current_timestamp
                yield GazeSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                    position=GazePosition(
                        distorted=Point2D(*d_point),
                        normalized=Point2D(*n_point),
                        rectified=Point2D(*r_point),
                    ),
                )


class IMUSensor(BaseSensor):
    def __init__(self, recording, max_duration_ns=50 * 1e6):
        """
        IMUSensor is a sensor that wraps the imu parts for a recording

        Args:
            recording: Recording this sensor belongs to
            max_duration_ns: maximum duration between 2 data samples without
                classifying it as a gap/disconnect
        """
        super().__init__()
        self.recording = recording
        self.max_duration_ns = max_duration_ns
        self.parts = self.recording.recording_parts.imu
        self.__data_parts = self.__init_data_parts()
        self.__multi_part_reader = MultiPartReader(
            self.recording, self.sensor_part_readers, sensor_name="imu"
        )

    def __init_data_parts(self) -> T.List[ArrayPartReader]:
        array_sensor_parts = []
        for imu_part in self.parts:
            if not imu_part.is_valid_part:
                continue

            array_sensor_part = ArrayPartReader(
                imu_part, max_duration_ns=self.max_duration_ns
            )
            array_sensor_parts.append(array_sensor_part)
        return array_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[ArrayPartReader]:
        """
        Array part readers for all valid imu sensor parts

        Returns:
            T.List[ArrayPartReader]: One ArrayPartReader for every valid imu part
        """
        return self.__data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> IMUSample:
        sample = IMUSample(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            gyroscope=Gyroscope(x=data["gyro_x"], y=data["gyro_y"], z=data["gyro_z"]),
            acceleration=Acceleration(
                x=data["accel_x"], y=data["accel_y"], z=data["accel_z"]
            ),
        )
        return sample

    def __iter__(self) -> T.Iterator[IMUSample]:
        """Iter imu sensor

        Yields:
            T.Iterator[IMUSample]: IMU samples of this sensor
        """
        return super().__iter__()

    # def __iter__(self) -> T.Sequence[IMUSample]:
    #     sensor_part_data = self.data
    #     # TODO(dan): using IMUSample objects here is ~5x slower than dicts
    #     # takes 5s to process 500,000 imu points (45 mins of data)

    #     return (
    #         self._data_to_sample(timestamp, duration, data)
    #         for timestamp, duration, data in sensor_part_data
    #     )

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[IMUSample]:
        """Read imu sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[IMUSample]: Data samples
        """
        return super().read(min_timestamp=min_timestamp, max_timestamp=max_timestamp)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> IMUSample:
        """Get closest imu sample to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            IMUSample: imu sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)


class WornSensor(BaseSensor):
    def __init__(self, recording):
        """
        WornSensor is a sensor that wraps the worn parts for a recording

        Args:
            recording: Recording this sensor belongs to
            max_duration_ns: maximum duration between 2 data samples without
                classifying it as a gap/disconnect
        """
        super().__init__()
        self.recording = recording
        self.parts = self.recording.recording_parts.worn
        self.__data_parts = self.__init_data_parts()
        self.__multi_part_reader = MultiPartReader(
            self.recording, self.sensor_part_readers, sensor_name="worn"
        )

    def __init_data_parts(self) -> T.List[ArrayPartReader]:
        array_sensor_parts = []
        for worn_part in self.parts:
            if not worn_part.is_valid_part:
                continue

            array_sensor_part = ArrayPartReader(worn_part)
            array_sensor_parts.append(array_sensor_part)
        return array_sensor_parts

    @property
    def sensor_part_readers(self) -> T.List[ArrayPartReader]:
        """
        Array part readers for all valid worn sensor parts

        Returns:
            T.List[ArrayPartReader]: One ArrayPartReader for every valid worn part
        """
        return self.__data_parts

    @property
    def _multi_part_reader(self) -> MultiPartReader:
        return self.__multi_part_reader

    def _data_to_sample(
        self,
        timestamp: RecordingTimestamp,
        duration: int,
        data,
        source=None,
    ) -> WornSample:
        sample = WornSample(
            recording=self.recording,
            timestamp=RecordingTimestamp(recording=self.recording, timestamp=timestamp),
            duration=duration,
            worn=data,
        )
        return sample

    def __iter__(self) -> T.Iterator[WornSample]:
        """Iter worn sensor

        Yields:
            T.Iterator[Worn]: Worn samples of this sensor
        """
        return super().__iter__()

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[WornSample]:
        """Read worn sensor data between timestamps

        Args:
            min_timestamp (int, optional): Start timestamp in epoch ns. Defaults to 0.
            max_timestamp (int, optional): End timestamp in epoch ns. Defaults to
                MAX_TIMESTAMP.

        Yields:
            T.Iterator[WornSample]: Data samples
        """
        if not self._multi_part_reader.part_readers:
            for gaze in self.recording.gaze.read():
                yield WornSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=gaze.timestamp
                    ),
                    duration=int(gaze.duration),
                    worn=255,
                )
            return

        previous_position = self.current_timestamp
        self.seek(min_timestamp)
        batchsize = 100_000
        for batch in more_itertools.chunked(self._multi_part_reader, n=batchsize):
            for timestamp, duration, worn in batch:
                if timestamp > max_timestamp:
                    break
                if timestamp + duration < min_timestamp:
                    continue
                self._current_timestamp = timestamp + duration
                yield WornSample(
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                    worn=worn,
                )

        self.seek(previous_position)

    def get_closest(
        self, timestamp: int = 0, max_time_difference_ns: int = 100 * 1e6
    ) -> WornSample:
        """Get closest worn sample to timestamp, return None if timestamp difference
        larger than `max_time_difference_ns`

        Args:
            timestamp (int, optional): Requested timestamp in epoch_ns. Defaults to 0.
            max_time_difference_ns (int, optional): Maximum allowed timestamp difference
                in ns. Defaults to 100*1e6.

        Returns:
            WornSample: worn sample
        """
        return super().get_closest(timestamp, max_time_difference_ns)


class WornDBSensor(WornSensor):
    def __init__(self, recording, max_duration_ns=50 * 1e6):
        self.recording = recording
        self.max_duration_ns = max_duration_ns
        self._current_timestamp = recording.start_epoch_ns

        if not get_clickhouse_client():
            raise NoDBConnectionException("No connection to database")
        self.__seek = self.recording.start_epoch_ns

    @property
    def sensor_part_readers(self):
        """Worn from DB does not have any parts

        Returns:
            None
        """
        return None  # TODO ?

    def seek(self, timestamp_ns: int):
        self._current_timestamp = timestamp_ns
        self.__seek = timestamp_ns

    @property
    def _multi_part_reader(self):
        return get_worn_data(self.recording, start_epoch_ns=self.__seek)

    def read(
        self, min_timestamp: int = 0, max_timestamp: int = MAX_TIMESTAMP
    ) -> T.Iterator[Sample]:
        worn_data = get_worn_data(
            self.recording, start_epoch_ns=min_timestamp, end_epoch_ns=max_timestamp
        )

        batchsize = 100_000
        for batch in more_itertools.chunked(worn_data, n=batchsize):
            worn_points = [worn for _, worn in batch]
            for (
                (sensor_part_datum, w_point),
                next_data,
            ) in iter_with_next(zip(batch, worn_points)):
                timestamp, _ = sensor_part_datum
                duration = self.max_duration_ns
                if next_data:
                    next_db_sample, _ = next_data
                    next_timestamp = next_db_sample[0]
                    duration = min(next_timestamp - timestamp, self.max_duration_ns)
                self._current_timestamp = timestamp + duration
                yield WornSample(
                    worn=w_point,
                    recording=self.recording,
                    timestamp=RecordingTimestamp(
                        recording=self.recording, timestamp=timestamp
                    ),
                    duration=duration,
                )
