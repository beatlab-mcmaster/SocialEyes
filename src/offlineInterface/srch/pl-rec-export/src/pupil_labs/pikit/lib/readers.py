import logging

import av
import numpy as np

from . import stream_info
from .binary import BinaryArrayReader
from .binary import FileReader
from .binary import URLFileReader
from .util import cached_property

logger = logging.getLogger(__name__)


class TimeReader(BinaryArrayReader):
    dtype = np.dtype(np.int64)


class GazeReader(BinaryArrayReader):
    dtype = np.dtype([("x", "<f"), ("y", "<f")])


class WornReader(BinaryArrayReader):
    # dtype = np.dtype([("worn", np.uint8)])
    dtype = np.dtype(np.uint8)


class IMUReader(BinaryArrayReader):
    dtype = np.dtype(
        [
            ("gyro_x", "<f"),
            ("gyro_y", "<f"),
            ("gyro_z", "<f"),
            ("accel_x", "<f"),
            ("accel_y", "<f"),
            ("accel_z", "<f"),
        ]
    )


class VideoReader(FileReader):
    def __init__(self, file):
        super().__init__(file)
        if isinstance(self.reader, URLFileReader):
            logger.debug(f"open video container {self.reader.url}")
            # av.open(<URLFileReader>) takes 12s
            # av.open(<URLFileReader>.url) takes 2s for a 2 min rec
            self.container = av.open(self.reader.url)
        else:
            logger.debug(f"open video container {self.reader}")
            self.container = av.open(self.reader)

    @cached_property
    def has_audio(self):
        if self.is_mp4:
            return bool(self.container.streams.audio)
        return False

    @property
    def format(self):
        return self.container.format.name

    @property
    def is_mp4(self):
        return "mp4" in self.format

    @cached_property
    def demux_analysis_video(self):
        self.container.seek(0)
        n_frames = 0
        last_packet = None
        for packet in self.container.demux(video=0):
            if packet.dts is not None:
                n_frames += 1
                last_packet = packet

        self.container.seek(0)
        return {
            "n_frames": n_frames,
            "last_dts": last_packet.dts,
            "last_pts": last_packet.pts,
            "last_timestamp": last_packet.pts * last_packet.time_base,
            "last_packet_duration": last_packet.duration * last_packet.time_base,
        }

    @cached_property
    def demux_analysis_audio(self):
        self.container.seek(0)
        n_frames = 0
        last_packet = None
        for packet in self.container.demux(audio=0):
            if packet.dts is not None:
                n_frames += 1
                last_packet = packet

        self.container.seek(0)
        return {
            "n_frames": n_frames,
            "last_dts": last_packet.dts,
            "last_pts": last_packet.pts,
            "last_timestamp": last_packet.pts * last_packet.time_base,
            "last_packet_duration": last_packet.duration * last_packet.time_base,
        }

    @property
    def n_frames_video(self):
        if self.is_mp4:
            return self.container.streams.video[0].frames
        return self.demux_analysis_video["n_frames"]

    @property
    def last_pts_video(self):
        return self.demux_analysis_video["last_pts"]

    @property
    def last_timestamp_video(self):
        return self.demux_analysis_video["last_timestamp"]

    @property
    def last_frame_duration_video(self):
        return self.demux_analysis_video["last_packet_duration"]

    @property
    def n_frames_audio(self):
        if self.has_audio:
            return self.container.streams.audio[0].frames

    @property
    def last_pts_audio(self):
        return self.demux_analysis_audio["last_pts"]

    @property
    def last_timestamp_audio(self):
        return self.demux_analysis_audio["last_timestamp"]

    @property
    def last_frame_duration_audio(self):
        return self.demux_analysis_audio["last_packet_duration"]

    @property
    def duration_ns(self):
        video_stream = self.container.streams.video[0]
        if video_stream.duration is not None:  # mp4
            return int((video_stream.duration * video_stream.time_base) * 1e9)

    @property
    def duration_audio_ns(self):
        if self.has_audio:
            audio_stream = self.container.streams.audio[0]
            if audio_stream.duration is not None:
                return int((audio_stream.duration * audio_stream.time_base) * 1e9)

    @cached_property
    def video_info(self):
        return stream_info.VideoStreamInfo(self.container.streams.video[0])

    @cached_property
    def audio_info(self):
        if self.has_audio:
            return stream_info.AudioStreamInfo(self.container.streams.audio[0])

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}"
                for attr in ["container", "video_info", "audio_info"]
            )
            + ">"
        )
