import enum
import logging
import typing as T
from pathlib import Path

import av
import cv2
import numpy as np
import turbojpeg

log = logging.getLogger(__name__)
VideoPath = T.Union[str, Path]


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


def mjpeg_video_frame_generator(video_path: VideoPath, format="gray"):
    pixel_format = turbojpeg.TJPF_GRAY if format == "gray" else turbojpeg.TJPF_RGB
    jpeg_decoder = turbojpeg.TurboJPEG()
    packet_errors = 0
    last_packet_err = None
    with av.open(str(video_path), format="mjpeg") as container:
        for index, packet in enumerate(container.demux(video=0)):
            # Skip flushing packets that are caused by demux.
            # All videos have dts, if they are not in the file,
            # then pyav creates synthetic ones.
            frame_np = None
            if packet.dts is None:
                continue
            try:
                frame_np = jpeg_decoder.decode(
                    packet, pixel_format=pixel_format, flags=turbojpeg.TJFLAG_FASTDCT
                )
            except Exception as exc:
                log.debug(f"error processing packet {index} in {video_path}: {exc}")
                packet_errors += 1
                last_packet_err = exc

            yield frame_np

    if packet_errors:
        log.warning(
            f"skipped {packet_errors} packets with error in {video_path}: "
            f"{last_packet_err}"
        )


def av_h264_frame_to_gray(av_frame):
    """
    Returns the gray frame data from the planes of a YUV av frame
    """
    plane = av_frame.planes[0]
    gray = np.frombuffer(plane, np.uint8)
    try:
        gray.shape = av_frame.height, av_frame.width
    except ValueError:
        gray = gray.reshape(-1, plane.line_size)
        gray = np.ascontiguousarray(gray[:, : av_frame.width])
    return gray


def mp4_video_frame_generator(filepath: VideoPath, format="gray"):
    with av.open(str(filepath), format="mp4") as container:
        # container.streams.video[0].thread_type = "AUTO"
        for packet in container.demux(video=0):
            try:
                frames = packet.decode()
            except Exception as e:
                log.warning(f"error decoding packet: {e}")
                continue
            for frame in frames:
                if format == "gray":
                    frame_np = av_h264_frame_to_gray(frame)
                else:
                    frame_np = frame.to_ndarray(format=format)
                yield frame_np
