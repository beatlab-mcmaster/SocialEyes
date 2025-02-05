from collections import namedtuple
from fractions import Fraction

import av
import numpy as np

from .constants import (
    NEON_SCENE_HEIGHT,
    NEON_SCENE_WIDTH,
    PI_SCENE_HEIGHT,
    PI_SCENE_WIDTH,
)
from .util import cached_property

Resolution = namedtuple("Resolution", ["width", "height"])


class StreamInfo:
    # https://github.com/mikeboers/PyAV/blob/develop/av/audio/frame.pyx
    _format_dtypes = {
        "dbl": "<f8",
        "dblp": "<f8",
        "flt": "<f4",
        "fltp": "<f4",
        "s16": "<i2",
        "s16p": "<i2",
        "s32": "<i4",
        "s32p": "<i4",
        "u8": "u1",
        "u8p": "u1",
    }

    @cached_property
    def format(self):
        return self.stream.codec_context.format

    @cached_property
    def time_base(self):
        return self.stream.time_base

    @cached_property
    def gop_size(self):
        return self.stream.gop_size

    @cached_property
    def bit_rate(self):
        return self.stream.bit_rate

    @cached_property
    def sample_rate(self):
        return None

    @cached_property
    def frame_size(self):
        return None

    @cached_property
    def av_layout(self):
        return None

    @cached_property
    def av_format(self):
        return self.stream.codec_context.format.name

    @cached_property
    def dtype(self):
        return None

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [
                    f"{attr}={getattr(self, attr, '?')!r}"
                    for attr in [
                        "format",
                        "bit_rate",
                        "sample_rate",
                        "time_base",
                        "frame_size",
                        "av_format",
                        "av_layout",
                        "gop_size",
                        "dtype",
                    ]
                ]
            )
            + ">"
        )


class AudioStreamInfo(StreamInfo):
    """Audio stream info for mp4 files"""

    def __init__(self, stream):
        assert (
            stream.type == "audio"
        ), f"Cannot initialize AudioStreamInfo from {stream.type} stream"
        self.stream = stream

    @property
    def time_base(self):
        return self.stream.time_base

    @cached_property
    def sample_rate(self):
        return self.stream.sample_rate

    @cached_property
    def frame_size(self):
        return self.stream.frame_size

    @cached_property
    def av_layout(self):
        return self.stream.layout.name

    @cached_property
    def dtype(self):
        return np.dtype(StreamInfo._format_dtypes[self.av_format])


class VideoStreamInfo(StreamInfo):
    """Video stream info for mp4 files"""

    def __init__(self, stream):
        assert (
            stream.type == "video"
        ), f"Cannot initialize VideoStreamInfo from {stream.type} stream"
        self.stream = stream


class DefaultVideoStreamInfo(VideoStreamInfo):
    """
    Default video stream info, used if no world video is available to
    read the properties.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height

    @cached_property
    def sample_rate(self):
        return None

    @cached_property
    def format(self):
        return Resolution(self.width, self.height)

    @cached_property
    def frame_size(self):
        return None

    @cached_property
    def time_base(self):
        return Fraction(1, 90000)

    @cached_property
    def av_layout(self):
        None

    @cached_property
    def av_format(self):
        return "yuv420p"

    @cached_property
    def dtype(self):
        return None

    @cached_property
    def gop_size(self):
        return 12

    @cached_property
    def bit_rate(self):
        return 5_000_000


DEFAULT_PI_VIDEO_STREAM_INFO = DefaultVideoStreamInfo(PI_SCENE_WIDTH, PI_SCENE_HEIGHT)
DEFAULT_NEON_VIDEO_STREAM_INFO = DefaultVideoStreamInfo(
    NEON_SCENE_WIDTH, NEON_SCENE_HEIGHT
)


class DefaultEyeVideoStreamInfo(VideoStreamInfo):
    """
    Default video stream info, used if no mp4 eye video is available to
    read the properties.
    """

    def __init__(self):
        pass

    @cached_property
    def sample_rate(self):
        return None

    @cached_property
    def format(self):
        return Resolution(192, 192)

    @cached_property
    def frame_size(self):
        return None

    @cached_property
    def time_base(self):
        return Fraction(1, 90000)

    @cached_property
    def av_layout(self):
        None

    @cached_property
    def av_format(self):
        return "yuvj420p"

    @cached_property
    def dtype(self):
        return None

    @cached_property
    def gop_size(self):
        return 12

    @cached_property
    def bit_rate(self):
        return 1_000_000


DEFAULT_EYE_VIDEO_STREAM_INFO = DefaultEyeVideoStreamInfo()


class DefaultAudioStreamInfo(AudioStreamInfo):
    """
    Default audio stream info, used if no audio is available to read the properties.
    """

    def __init__(self, family):
        if family == "neon":
            self._time_base = Fraction(1, 90000)
        else:
            self._time_base = Fraction(1, 44100)
            self._sample_rate = 48000

    @cached_property
    def sample_rate(self):
        return self._sample_rate

    @cached_property
    def format(self):
        return av.AudioFormat("fltp")

    @cached_property
    def frame_size(self):
        return 1024

    @cached_property
    def time_base(self):
        return self._time_base

    @cached_property
    def av_layout(self):
        return av.AudioLayout("mono").name

    @cached_property
    def av_format(self):
        return av.AudioFormat("fltp").name

    @cached_property
    def dtype(self):
        return None

    @cached_property
    def bit_rate(self):
        return 64_000


DEFAULT_NEON_AUDIO_STREAM_INFO = DefaultAudioStreamInfo("neon")
DEFAULT_PI_AUDIO_STREAM_INFO = DefaultAudioStreamInfo("pi")
