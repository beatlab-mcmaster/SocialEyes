import atexit
import logging
import os
import shutil
import subprocess
import tempfile
import typing as T
from fractions import Fraction
from queue import Queue

import av
from tqdm import tqdm

from pikit.lib.sensors import AudioFrame
from pikit.lib.sensors import AudioSensor
from pikit.lib.sensors import VideoFrameFactory
from pikit.lib.sensors import WorldSensor

logger = logging.getLogger(__name__)

OUTPUT_TIME_BASE = Fraction(1, 90000)
MIN_DELTA_AUDIO_PTS = 5


def check_pyav_video_encoder_error(encoder):
    """
    Tries to run an encoding of a video using `encoder` and returns the
    exception if there is one otherwise None.

    Args:
        encoder (string): eg. 'h264_nvenc'

    Returns:
        error: the exception raised or None if it worked
    """
    error = None
    with tempfile.NamedTemporaryFile(suffix=".mp4") as fp:
        container = av.open(fp.name, "w")
        try:
            video_stream = container.add_stream(encoder)
            video_stream.encode(None)
        except Exception as exc:
            error = exc
    return error


class AudioStream:
    """
    av audio stream class to ensure no buffering of pts when encoding and striclty
    monotonic pts
    """

    def __init__(self, audio_stream):
        self.stream = audio_stream
        self.__last_pts = -10
        self._pts_q = Queue()

    def encode(self, audio_av_frame, pts=None):
        if pts is not None:
            self._pts_q.put(pts)

        audio_packets = self.stream.encode(audio_av_frame)

        for packet in audio_packets:
            if not self._pts_q.empty():
                audio_pts = self._pts_q.get()
                audio_pts = max(self.__last_pts + MIN_DELTA_AUDIO_PTS, audio_pts)
                packet.pts = audio_pts
                packet.dts = audio_pts

                self.__last_pts = audio_pts
                yield packet


class VideoSampler:
    def sample(self, pts: int):
        raise NotImplementedError()


class NoSampler(VideoSampler):
    def sample(self, pts: int):
        return True


class ThumbsVideoSampling(VideoSampler):
    def __init__(self, delta_pts):
        self.delta_pts = delta_pts
        self.__next_pts = 0

    def sample(self, pts: int):
        if pts:
            sample = pts >= self.__next_pts
            if sample:
                self.__next_pts += self.delta_pts
            return sample
        return False


class VideoStream:
    """
    av video stream class to keep track of last pts
    """

    def __init__(self, video_stream, video_sampler: VideoSampler = None):
        self.stream = video_stream
        self.video_sampler = video_sampler or NoSampler()
        self.__last_pts = -1

    @property
    def last_pts(self):
        return self.__last_pts

    def encode(self, video_av_frame, pts=None):
        if self.video_sampler.sample(pts):
            self.__last_pts = pts
            yield from self.stream.encode(video_av_frame)


class AV_Output:
    def __init__(self, output_path, container, video_stream, audio_stream):
        self.output_path = output_path
        self.__container = container
        self.__video_stream = video_stream
        self.__audio_stream = audio_stream

    @property
    def container(self) -> av.container:
        return self.__container

    @property
    def video_stream(self) -> VideoStream:
        return self.__video_stream

    @property
    def audio_stream(self) -> AudioStream:
        return self.__audio_stream

    @classmethod
    def create_output(
        cls,
        output_path,
        video_info,
        audio_info,
        gop_size=None,
        bit_rate=None,
        frame_size=None,
        encoder="h264_nvenc",
        audio=True,
        audio_codec="aac",
        video_sampler=None,
    ):
        logger.info(f"create output container {output_path}")

        # NOTE: h264_nvenc doesnt seem to work well with small bitrates so we
        # convert it to h264 encoder in this case
        if encoder == "h264_nvenc" and bit_rate and bit_rate < 200_000:
            encoder = "h264"
            print(
                f"{output_path} - bitrate requested {bit_rate} is too small "
                "for h264_nvenc encoder, using h264 instead"
            )

        container = av.open(output_path, "w")
        video_stream, audio_stream = None, None
        bit_rate = bit_rate or video_info.bit_rate

        if encoder == "h264_nvenc":
            h264_nvenc_error = check_pyav_video_encoder_error("h264_nvenc")
            if h264_nvenc_error:
                logger.warning(
                    f"could not add stream with encoder {encoder}, using "
                    "h264 instead. Error was: {h264_nvenc_error}"
                )
                encoder = "h264"

        video_stream = container.add_stream(encoder)

        logger.info(f"added video stream to output container with encoder {encoder}")

        video_stream.bit_rate = bit_rate
        frame_size = frame_size or (video_info.format.height, video_info.format.width)
        video_stream.time_base = OUTPUT_TIME_BASE

        if gop_size is not None:
            video_stream.gop_size = gop_size

        # h264_nvenc encoder seems to encode at a different bitrate to requested,
        # multiplying by 10 and dividing by 8 seems to fix it (maybe it's a bug
        # issue of bits vs bytes somewhere in the encoder...)
        if encoder == "h264_nvenc":
            video_stream.codec_context.bit_rate *= 1.25

        # b frames can cause certain frames in chrome to not be seeked to correctly
        # https://bugs.chromium.org/p/chromium/issues/detail?id=66631
        video_stream.options["bf"] = "0"

        # Move atom to start so less requests when loading video in web
        video_stream.options["movflags"] = "faststart"

        # bufsize at 2x bitrate seems to give better overall quality
        video_stream.options["bufsize"] = f"{2*bit_rate/1000}k"

        video_stream.codec_context.height = frame_size[0]
        video_stream.codec_context.width = frame_size[1]

        if audio:
            logger.info(
                f"add audio stream to output container with codec {audio_codec}"
            )
            if audio_codec == "aac":
                audio_stream = container.add_stream("aac")

            elif audio_codec == "flac":
                container.options["strict"] = "experimental"
                audio_stream = container.add_stream("flac")
                audio_stream.options["frame_size"] = f"{audio_info.frame_size}"
            audio_stream.time_base = audio_info.time_base
            audio_stream.sample_rate = audio_info.sample_rate
            audio_stream.codec_context.layout = audio_info.av_layout

        custom_audio_stream = None
        if audio_stream:
            custom_audio_stream = AudioStream(audio_stream)
            if audio_codec == "aac":
                # aac codec adds one packet at the beginning
                # https://www2.iis.fraunhofer.de/AAC/gapless.html
                custom_audio_stream._pts_q.put(0)

        return cls(
            output_path,
            container,
            VideoStream(video_stream, video_sampler),
            custom_audio_stream,
        )


def default_av_output(
    recording,
    video_filename,
    video_encoder,
    with_audio,
    frame_height=None,
    frame_width=None,
    audio_codec="aac",
    bit_rate=2_500_000,
):
    return AV_Output.create_output(
        output_path=video_filename,
        video_info=recording.world.video_info,
        audio_info=recording.audio.audio_info if recording.has_audio else None,
        encoder=video_encoder,
        bit_rate=bit_rate,
        gop_size=12,
        frame_size=(
            frame_height or recording.world.video_info.format.height,
            frame_width or recording.world.video_info.format.width,
        ),
        audio=recording.has_audio and with_audio,
        audio_codec=audio_codec,
    )


class MPEG_Audio_Writer:
    def __init__(
        self,
        video: WorldSensor,
        audio: T.Optional[AudioSensor],
        start_epoch_ns: float,
        end_epoch_ns: float,
        output: T.Iterable[AV_Output],
        show_progress: bool = False,
    ):
        self.show_progress = show_progress
        self.video = video
        self.output = output
        self.recording = video.recording
        self.start_epoch_ns = max(self.video.recording.start_epoch_ns, start_epoch_ns)
        self.end_epoch_ns = min(end_epoch_ns, self.video.recording.end_epoch_ns)
        self.section_duration = self.end_epoch_ns - self.start_epoch_ns

        self.video_info = self.video.recording.world.video_info

        self.audio_iterator = None
        if audio:
            self.audio_info = self.video.recording.audio.audio_info
            self.audio_iterator = audio.read(
                min_timestamp=start_epoch_ns, max_timestamp=end_epoch_ns
            )

    def video_pts_from_ns(self, offset_ns):
        return int(round(1 / OUTPUT_TIME_BASE * offset_ns / 1e9))

    def audio_pts_from_ns(self, offset_ns):
        return int(round(1 / self.audio_info.time_base * offset_ns / 1e9))

    def encode(self):
        """Encode audio and video frames into mp4 file

        requested section:     |------------------------------------------|
                             start_epoch_ns                         end_epoch_ns

        audio/video frames: |--------|------------|------|----------------------|
                             >>                           >>>>>>>>>>>>>>>>
        mp4 output:            |-----|------------|-----------------------|
                             0 [pts]                 (section_duration)/time_base [pts]

        """
        logger.info(
            f"encode video "
            f"(names={[o.output_path for o in self.output]},"
            f" video duration={self.section_duration/1e9}s)"
        )

        added_leading_video_frame = False
        added_leading_audio_frame = False

        def write_audio_frames(until_timestamp, add_leading_audio_frame=False):
            if not self.audio_iterator:
                return
            section_duration_in_audio_pts = self.audio_pts_from_ns(
                self.section_duration
            )

            previous_audio_frame = None
            for audio_frame in self.audio_iterator:
                audio_frame_offset_ns = (
                    audio_frame.timestamp.epoch_ns - self.start_epoch_ns
                )

                if audio_frame_offset_ns < 0:
                    # before section start -> skip
                    previous_audio_frame = audio_frame
                    continue

                if add_leading_audio_frame and audio_frame_offset_ns > 0:
                    # first audio frame inside section -> add previous frame at pts = 0
                    if not previous_audio_frame:
                        raise Exception("Leading audio frame is missing")

                    previous_audio_frame.av_frame.pts = None
                    self.encode_and_mux_audio_frame(
                        previous_audio_frame.av_frame, pts=0
                    )

                add_leading_audio_frame = False
                if audio_frame.end_timestamp.epoch_ns >= self.end_epoch_ns:
                    # last audio frame -> skip it, as it is added in next section

                    # add final dummy packets with start timestamp at the end of the
                    # section to set last packet duration correctly.
                    self.add_final_audio_frame()
                    break

                audio_frame.av_frame.pts = None
                # ensure audio pts (of last frame) have MIN_DELTA_AUDIO_PTS distance to
                # section end time to be able to add final audio packet and keep
                # requested section duration
                self.encode_and_mux_audio_frame(
                    audio_frame.av_frame,
                    min(
                        self.audio_pts_from_ns(audio_frame_offset_ns),
                        section_duration_in_audio_pts - MIN_DELTA_AUDIO_PTS,
                    ),
                )
                if audio_frame.timestamp.epoch_ns > until_timestamp:
                    # done for this frame, pause iteration
                    break

        previous_frame = None
        last_video_pts = -1
        if self.show_progress:
            progress = tqdm(
                total=self.section_duration / 1e9,
                desc="Render",
                unit="x",
                bar_format=(
                    "{l_bar}{bar}| {n:.3f}/{total_fmt}s "
                    "[{elapsed}<{remaining}, {rate_fmt}{postfix}]"
                ),
            )
            progress = tqdm()

        section_duration_in_pts = self.video_pts_from_ns(self.section_duration)
        for frame in self.video.read(
            min_timestamp=self.start_epoch_ns, max_timestamp=self.end_epoch_ns
        ):
            frame_offset_ns = frame.timestamp.epoch_ns - self.start_epoch_ns
            pts = self.video_pts_from_ns(frame_offset_ns)

            if frame_offset_ns < 0:
                # frame before section -> skip
                previous_frame = frame
                continue
            if pts >= section_duration_in_pts:
                # frame after section -> stop
                break

            if pts <= last_video_pts:
                # some videos have duplicated or negative pts frames, drop them
                # as they cause jittery video and are caused by source video
                continue

            if not added_leading_video_frame and pts > 0:
                if not previous_frame:
                    raise Exception("Leading video frame is missing")
                self.encode_and_mux_video_frame(previous_frame.av_frame, pts=0)
            added_leading_video_frame = True
            last_video_pts = pts
            self.encode_and_mux_video_frame(frame.av_frame, pts=pts)
            if self.show_progress:
                progress.update()
                # progress.update(frame_offset_ns / 1e9 - progress.n)

            write_audio_frames(
                until_timestamp=frame.timestamp.epoch_ns,
                add_leading_audio_frame=not added_leading_audio_frame,
            )
            added_leading_audio_frame = True

        write_audio_frames(until_timestamp=self.end_epoch_ns)

        # add final dummy packets with start timestamp at the end of the section to
        # set last packet duration correctly.
        self.add_final_video_frame()
        if self.show_progress:
            progress.update(self.section_duration / 1e9 - progress.n)

        # flush the buffers
        self.encode_and_mux_audio_frame(None)
        self.encode_and_mux_video_frame(None)

        for output in self.output:
            output.container.close()

            # remove last packet again as it is outside of section
            remove_last_packet(output, self.section_duration)

    def encode_and_mux_audio_frame(self, audio_frame, pts=None):
        for output in self.output:
            if output.audio_stream:
                for packet in output.audio_stream.encode(audio_frame, pts):
                    output.container.mux(packet)

    def encode_and_mux_video_frame(self, video_frame, pts=None):
        for output in self.output:
            if video_frame:
                video_frame.pts = pts
                video_frame.time_base = OUTPUT_TIME_BASE

            for packet in output.video_stream.encode(video_frame, pts):
                output.container.mux(packet)

    def add_final_video_frame(self):
        pts = self.video_pts_from_ns(self.section_duration)
        frame = VideoFrameFactory(self.video_info, (0, 0, 0)).padding_frame()
        self.encode_and_mux_video_frame(frame, pts)

    def add_final_audio_frame(self):
        pts = self.audio_pts_from_ns(self.section_duration)
        empty_frame = AudioFrame.padding_frame(self.audio_info)
        self.encode_and_mux_audio_frame(empty_frame, pts)


def remove_last_packet(av_file: AV_Output, duration: float):
    temp_dir = tempfile.mkdtemp(prefix="pikit-processing-dir-")
    atexit.register(shutil.rmtree, temp_dir)

    temp_output = os.path.join(temp_dir, "output.mp4")

    duration_s = duration / 1e9
    subprocess.run(
        [
            "ffmpeg",
            "-t",
            str(duration_s),
            "-i",
            av_file.output_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-strict",
            "experimental",
            temp_output,
        ]
    )
    subprocess.run(["mv", temp_output, av_file.output_path])
