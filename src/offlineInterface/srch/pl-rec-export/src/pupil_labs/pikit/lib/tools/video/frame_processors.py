import logging
import math
import typing as T
from abc import ABC
from abc import abstractmethod
from enum import Enum

import av
import cv2
import intervaltree

from pikit.lib.sensors import AlteringVideoFrame
from pikit.lib.sensors import GazeSample
from pikit.lib.sensors import WornSample

from ..sample_utils import GazeUtils
from ..sample_utils import WornUtils

logger = logging.getLogger(__name__)


class FrameType(Enum):
    DISTORTED = 0
    RECTIFIED = 1


class FrameContent(Enum):
    GAZE = 0
    TIMESTAMPS = 1
    SCANPATH = 2


class FrameProcessor(ABC):
    @abstractmethod
    def __call__(self, frame: AlteringVideoFrame) -> AlteringVideoFrame:
        pass


class GazeCircleBurner(FrameProcessor):
    def __init__(
        self,
        radius: int,
        width: int,
        color: T.Tuple,
        gaze_data: T.Iterator,
        worn_data: T.Iterator,
        gaze_selection=GazeUtils.average_gaze_sample,
        worn_selection=WornUtils.average_worn_sample,
    ):
        self.radius = radius
        self.width = width
        self.color = color
        self.gaze_data = list(gaze_data)
        self.worn_data = list(worn_data)
        self.gaze_selection = gaze_selection
        self.worn_selection = worn_selection

    @staticmethod
    def request_gaze_data(
        gaze_data: T.List[GazeSample], start: int, end: int
    ) -> T.Tuple[T.List[GazeSample], T.List[GazeSample]]:
        # assumes sorted gaze data!
        requested_data = []
        for index, row in enumerate(gaze_data):
            gaze_end = row.end_timestamp.epoch_ns
            gaze_start = row.timestamp.epoch_ns
            if gaze_end > start and gaze_start < end:
                requested_data.append(row)
            if gaze_start >= end:
                return gaze_data[max(0, index - 1) :], requested_data
        return [], requested_data

    @staticmethod
    def request_worn_data(
        worn_data: T.List[WornSample], start: int, end: int
    ) -> T.Tuple[T.List[WornSample], T.List[WornSample]]:
        # assumes sorted worn data!
        requested_data = []
        for index, row in enumerate(worn_data):
            worn_end = row.end_timestamp.epoch_ns
            worn_start = row.timestamp.epoch_ns
            if worn_end > start and worn_start < end:
                requested_data.append(row)
            if worn_start >= end:
                return worn_data[max(0, index - 1) :], requested_data
        return [], requested_data

    def __call__(self, frame: AlteringVideoFrame) -> AlteringVideoFrame:
        remaining_gaze_data, frame_gaze_data = self.request_gaze_data(
            self.gaze_data, frame.timestamp.epoch_ns, frame.end_timestamp.epoch_ns
        )
        remaining_worn_data, frame_worn_data = self.request_worn_data(
            self.worn_data, frame.timestamp.epoch_ns, frame.end_timestamp.epoch_ns
        )
        self.gaze_data = remaining_gaze_data
        self.worn_data = remaining_worn_data

        frame = self.burn_in_gaze(frame, frame_gaze_data, frame_worn_data)
        return frame

    def burn_in_gaze(
        self,
        video_frame: AlteringVideoFrame,
        frame_gaze_data: T.Iterable,
        frame_worn_data: T.Iterable,
    ):
        image_array = video_frame.av_frame.to_ndarray(format="bgr24")

        if len(frame_gaze_data) != len(frame_worn_data):
            logger.warning(f"gaze and worn data are not the same length")

        gaze_selection = self.gaze_selection(frame_gaze_data)
        worn_selection = self.worn_selection(frame_worn_data)

        selection = zip(gaze_selection, worn_selection)

        for gaze_sample, worn_sample in selection:
            # NOTE (bil): skip burning gaze if worn is False
            if worn_sample.worn != 255:
                continue
            if FrameType.RECTIFIED in video_frame.properties:
                center = (
                    int(gaze_sample.position.rectified.x),
                    int(gaze_sample.position.rectified.y),
                )
            else:
                center = (
                    int(gaze_sample.position.distorted.x),
                    int(gaze_sample.position.distorted.y),
                )
            bgr = [self.color[2], self.color[1], self.color[0]]
            alpha = 1
            if len(self.color) == 4:
                alpha = self.color[-1] / 255
            pad = self.radius + 2 + self.width

            roi = (
                slice(int(center[1] - pad), int(center[1] + pad)),
                slice(int(center[0] - pad), int(center[0] + pad)),
            )
            try:
                overlay = image_array[roi].copy()
                cv2.circle(
                    image_array,
                    center,
                    self.radius,
                    bgr,
                    thickness=self.width,
                    lineType=cv2.LINE_AA,
                )
                opacity = alpha
                cv2.addWeighted(
                    src1=image_array[roi],
                    alpha=opacity,
                    src2=overlay,
                    beta=1.0 - opacity,
                    gamma=0,
                    dst=image_array[roi],
                )
            except Exception:
                logger.info("circle outside of image -> not drawing it")

        frame = av.VideoFrame.from_ndarray(image_array, format="bgr24")
        video_frame.av_frame = frame
        self.update_frame_properties(video_frame)
        return video_frame

    def update_frame_properties(self, frame: AlteringVideoFrame):
        frame.properties.add(FrameContent.GAZE)


class FixationScanpathBurner(FrameProcessor):
    def __init__(
        self,
        radius: int,
        width: int,
        color: T.Tuple,
        scanpath_data: T.List[T.Dict],
        worn_data: T.Iterator,
    ):
        self.radius = radius
        self.width = width
        self.color = color

        self.scanpath_lookup = intervaltree.IntervalTree()
        for frame in scanpath_data:
            self.scanpath_lookup[
                range(frame["start_offset_ns"], frame["stop_offset_ns"])
            ] = frame

        self.worn_data = list(worn_data)

    def __call__(self, frame: AlteringVideoFrame) -> AlteringVideoFrame:
        frame_offset_ns = frame.timestamp - frame.recording.start_epoch_ns
        for interval in self.scanpath_lookup[frame_offset_ns]:
            frame_scanpath_data = interval.data
            frame = self.render_scanpath(frame, frame_scanpath_data)
            break  # ignore dups

        return frame

    def render_scanpath(
        self,
        video_frame: AlteringVideoFrame,
        frame_scanpath_data: T.Dict,
    ):
        image_array = video_frame.av_frame.to_ndarray(format="bgr24")

        black = (0, 0, 0)
        white = (255, 255, 255)
        scan_color = white
        bg_color = black
        fixation_text_color = white
        prev_plot_point = None
        for scanpoint in frame_scanpath_data["path"]:
            dist_x = scanpoint["x"]
            dist_y = scanpoint["y"]
            if FrameType.RECTIFIED in video_frame.properties:
                center = dist_x, dist_y

            plot_point = dist_x, dist_y
            if prev_plot_point:
                cv2.line(image_array, prev_plot_point, plot_point, bg_color, 3)
                cv2.line(image_array, prev_plot_point, plot_point, scan_color, 2)
            fixation_id = scanpoint["id"]
            duration_ms = scanpoint["ms"]

            fixation_color = [self.color[2], self.color[1], self.color[0]]

            size = int(1.3 * math.sqrt(float(duration_ms)))

            # cv2.circle(
            #     image_array, plot_point, size, bg_color, thickness=self.width + 1
            # )
            cv2.circle(
                image_array,
                plot_point,
                size,
                fixation_color,
                thickness=self.width,
                lineType=cv2.LINE_AA,
            )

            for color, thickness in [(bg_color, 4), (fixation_text_color, 2)]:
                cv2.putText(
                    image_array,
                    f"{fixation_id}",
                    (plot_point[0] + 20, plot_point[1] + size),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=0.5,
                    thickness=thickness,
                    color=color,
                )
                cv2.putText(
                    image_array,
                    # f'{scanpoint["ms"]}ms',
                    str(fixation_id),
                    (plot_point[0] + 20, plot_point[1] + size),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=0.5,
                    thickness=thickness,
                    color=color,
                )

            prev_plot_point = plot_point

        frame = av.VideoFrame.from_ndarray(image_array, format="bgr24")
        video_frame.av_frame = frame
        self.update_frame_properties(video_frame)
        return video_frame

    def update_frame_properties(self, frame: AlteringVideoFrame):
        frame.properties.add(FrameContent.SCANPATH)


class FrameTimeBurner(FrameProcessor):
    def __init__(self, lines: T.Iterable[str] = None):
        self.frame_counter = 0
        if lines is None:
            lines = []
        self.additional_lines = lines

        self.font = cv2.FONT_HERSHEY_SIMPLEX

    def __call__(self, frame: AlteringVideoFrame) -> AlteringVideoFrame:
        np_frame = frame.av_frame.to_ndarray(format="bgr24")
        lines = [
            f"frame.start [offset ms]: {frame.timestamp.offset_ms}",
            f"frame.end [offset ms]  : {frame.end_timestamp.offset_ms}",
            f"frame.duration [ns]  : {frame.duration}",
            f"frame index   : {self.frame_counter}",
        ]
        lines.extend(self.additional_lines)

        offset_x, offset_y = 20, 40

        for line in lines:
            # dark background text first then light text
            # on top to make dark outline text
            for color, thickness in [((0, 0, 0), 4), ((255, 255, 255), 2)]:
                cv2.putText(
                    np_frame,
                    line,
                    (offset_x, offset_y),
                    fontFace=self.font,
                    fontScale=1,
                    thickness=thickness,
                    color=color,
                )
            offset_y += 35

        self.frame_counter += 1
        burned_av_frame = av.VideoFrame.from_ndarray(np_frame, format="bgr24")
        frame.av_frame = burned_av_frame
        self.update_frame_properties(frame)
        return frame

    def update_frame_properties(self, frame: AlteringVideoFrame):
        frame.properties.add(FrameContent.TIMESTAMPS)


class FrameUndistorter(FrameProcessor):
    def __init__(self, camera):
        self.camera = camera

    def __call__(self, frame: AlteringVideoFrame) -> AlteringVideoFrame:
        if {FrameContent.GAZE, FrameContent.TIMESTAMPS}.intersection(
            frame.properties
        ) != set():
            logger.warning(
                "undistorting frame after rendering content, result will look wrong"
            )
        frame.av_frame = self.camera.rectifyFrame(frame.av_frame)
        self.update_frame_properties(frame)
        return frame

    def update_frame_properties(self, frame: AlteringVideoFrame):
        frame.properties.discard(FrameType.DISTORTED)
        frame.properties.add(FrameType.RECTIFIED)
