import logging
import re
import typing as T
from abc import ABC
from abc import abstractproperty
from collections import OrderedDict

from natsort import natsorted

from .readers import GazeReader
from .readers import IMUReader
from .readers import TimeReader
from .readers import VideoReader
from .readers import WornReader

logger = logging.getLogger(__name__)


class RecordingParts:
    def __init__(self, recording):
        self.recording = recording

    @property
    def parted_files(self):
        """
        Returns parted sensor files aggregated via the ps<N> convention

        Examples:
            >>> recording.recording_parts.parted_files
            {
                'PI left v1': OrderedDict([
                    (
                        1,
                        {
                            'mjpeg': <File name='PI left v1 ps1.mjpeg', size=37295399>,
                            'time': <File name='PI left v1 ps1.time', size=7072>,
                            'time_aux': <File name='PI left v1 ps1.time_aux', size=7072>
                        }
                    ),
                    (
                        2,
                        {
                            'mjpeg': <File name='PI left v1 ps2.mjpeg', size=15992316>,
                            'time': <File name='PI left v1 ps2.time', size=7072>,
                            'time_aux': <File name='PI left v1 ps2.time_aux', size=7072>
                        }
                    ),
                ]),
                'gaze': OrderedDict([
                    (
                        1,
                        {
                            'raw': <File name='gaze ps1.raw', size=10296>,
                            'time': <File name='gaze ps1.time', size=10296>
                        }
                    )
                ]),
                ...
            }
        """

        regex = re.compile(r"(?P<prefix>.+) ps(?P<part_number>\d+)\.(?P<extension>.*)")
        result = {}
        for filename, file in natsorted(self.recording.files.items()):
            regex_match = regex.search(filename)
            if regex_match:
                prefix, part_number, extension = regex_match.groups()
                part_number = int(part_number)
                if prefix not in result:
                    result[prefix] = OrderedDict()
                if part_number not in result[prefix]:
                    result[prefix][part_number] = {}
                result[prefix][part_number][extension] = file
        return result

    @property
    def stand_alone_files(self):
        """Files without part number (ps<X>), grouped by name

        Examples:
         >>> recording.recording_parts.stand_alone_files
         {
            'gaze_200hz': {
                'raw': <File name='gaze_200hz.raw', size=7072>,
                'time': <File name='gaze_200hz.time', size=7072>,
            },

            'info': {
                'json': <File name='info.json', size=1026>,

            },
             ...
         }
        """

        parted_regex = re.compile(
            r"(?P<prefix>.+) ps(?P<part_number>\d+)\.(?P<extension>.*)"
        )
        stand_alone_regex = re.compile(r"(?P<name>.+)\.(?P<extension>.*)")
        result = {}
        for filename, file in natsorted(self.recording.files.items()):
            parted_regex_match = parted_regex.search(filename)
            if not parted_regex_match:
                regex_match = stand_alone_regex.search(filename)
                if regex_match:
                    name, extension = regex_match.groups()
                    if name not in result:
                        result[name] = {}
                    result[name][extension] = file
        return result

    @property
    def wearer_json(self) -> T.Dict:
        wearer_file = self.stand_alone_files.get("wearer")
        if wearer_file:
            return wearer_file.get("json")

    @property
    def template_json(self) -> T.Dict:
        template_file = self.stand_alone_files.get("template")
        if template_file:
            return template_file.get("json")

    @property
    def gaze(self) -> T.Sequence["GazePart"]:
        """Wraps gaze raw and time file of every part (ps<X>) in a GazePart object

        Returns:
            T.Sequence["GazePart"]: List of gaze parts
        """
        result = []
        parted_files = self.parted_files.get("gaze") or {}
        for part_number, files_by_suffix in parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            gaze_file = files_by_suffix.get("raw")
            gaze = None
            if gaze_file is not None:
                gaze = GazeReader(gaze_file)

            gaze_part = GazePart(
                recording=self.recording, number=part_number, times=times, gaze=gaze
            )
            result.append(gaze_part)
        return result

    @property
    def gaze200(self) -> T.Sequence["GazePart"]:
        result = []
        gaze_200_files = self.stand_alone_files.get("gaze_200hz")
        if gaze_200_files:
            time_file = gaze_200_files.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            gaze_200_file = gaze_200_files.get("raw")
            gaze_200 = None
            if gaze_200_file is not None:
                gaze_200 = GazeReader(gaze_200_file)

            gaze_part = GazePart(
                recording=self.recording, number=None, times=times, gaze=gaze_200
            )
            result.append(gaze_part)
        return result

    @property
    def imu(self) -> T.Sequence["IMUPart"]:
        """Wraps imu raw and time file of every part (ps<X>) in a IMUPart object

        Returns:
            T.Sequence["IMUPart"]: List of imu parts
        """
        result = []
        parted_files = self.parted_files.get("extimu") or {}
        for part_number, files_by_suffix in parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            imu_file = files_by_suffix.get("raw")
            imu = None
            if imu_file is not None:
                imu = IMUReader(imu_file)

            imu_part = IMUPart(
                recording=self.recording, number=part_number, times=times, imu=imu
            )
            result.append(imu_part)
        return result

    @property
    def world(self):
        """Wraps world mp4 and time file of every part (ps<X>) in a WorldPart object

        Returns:
            T.Sequence["WorldPart"]: List of world parts
        """
        result = []
        parted_files = (
            self.parted_files.get("PI world v1")
            or self.parted_files.get("Neon Scene Camera v1")
            or {}
        )
        for video_number, files_by_suffix in parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            # this should be mp4, but we have some recordings that have mjpeg.
            # VideoReader can read both
            video_file = files_by_suffix.get("mp4") or files_by_suffix.get("mjpeg")
            video = None
            if video_file is not None:
                try:
                    video = VideoReader(video_file)
                except Exception as e:
                    logger.warning(f"Can not initialize VideoReader: {e}")

            result.append(
                WorldPart(
                    recording=self.recording,
                    number=video_number,
                    video=video,
                    times=times,
                )
            )
        return result

    @property
    def audio(self):
        """Wraps world mp4 and time file of every part (ps<X>) in a AudioPart object

        Returns:
            T.Sequence["AudioPart"]: List of audio parts
        """
        result = []
        parted_files = (
            self.parted_files.get("PI world v1")
            or self.parted_files.get("Neon Scene Camera v1")
            or {}
        )
        for video_number, files_by_suffix in parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            video_file = files_by_suffix.get("mp4")
            video = None
            if video_file is not None:
                try:
                    video = VideoReader(video_file)
                except Exception as e:
                    logger.warning(f"Can not initialize VideoReader: {e}")

            result.append(
                AudioPart(
                    recording=self.recording,
                    number=video_number,
                    video=video,
                    times=times,
                )
            )
        return result

    def eye(self, eye: str):
        """Wraps eye mp4/mjpeg and time file of every part (ps<X>) in a EyePart object

        Returns:
            T.Sequence["EyePart"]: List of eye parts
        """
        result = []
        parted_files = self.parted_files.get(f"PI {eye} v1") or {}
        for video_number, files_by_suffix in parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)

            # use mp4 if available
            video_file = files_by_suffix.get("mp4") or files_by_suffix.get("mjpeg")
            video = None
            if video_file is not None:
                try:
                    video = VideoReader(video_file)
                except Exception as e:
                    logger.warning(f"Can not initialize VideoReader: {e}")

            result.append(
                EyePart(
                    recording=self.recording,
                    number=video_number,
                    video=video,
                    times=times,
                )
            )
        return result

    @property
    def eye_left(self):
        """Wraps left eye mp4/mjpeg and time file of every part (ps<X>) in a EyePart object

        Returns:
            T.Sequence["EyePart"]: List of eye parts
        """
        return self.eye("left")

    @property
    def eye_right(self):
        """Wraps right eye mp4/mjpeg and time file of every part (ps<X>) in a EyePart object

        Returns:
            T.Sequence["EyePart"]: List of eye parts
        """
        return self.eye("right")

    @property
    def worn(self):
        """Wraps world raw and gaze time file of every part (ps<X>) in a WornPart object

        Returns:
            T.Sequence["WornPart"]: List of worn parts
        """
        result = []

        # worn classifier outputs one value for every gaze predictions, so use
        # gaze timestamps
        gaze_parted_files = self.parted_files.get("gaze") or {}
        time_readers = {}
        for part_number, files_by_suffix in gaze_parted_files.items():
            time_file = files_by_suffix.get("time")
            times = None
            if time_file is not None:
                times = TimeReader(time_file)
                time_readers[part_number] = times

        parted_files = self.parted_files.get("worn") or {}

        for part_number, files_by_suffix in parted_files.items():

            times = time_readers.get(part_number)

            worn_file = files_by_suffix.get("raw")

            worn = None
            if worn_file is not None:
                worn = WornReader(worn_file)
            worn_part = WornPart(
                recording=self.recording, number=part_number, times=times, worn=worn
            )
            result.append(worn_part)
        return result

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}"
                for attr in ["recording", "parted_files"]
            )
            + ">"
        )


class Part(ABC):
    @property
    def start_epoch_ns(self):
        if not self.times:
            return None
        return self.times[0]

    @property
    def last_timestamp(self):
        if not self.times:
            return None
        return self.times[-1]

    @property
    def offset_ns(self):
        if not self.start_epoch_ns:
            return None
        return self.start_epoch_ns - self.recording.start_epoch_ns

    @property
    def n_timestamps(self):
        if not self.times:
            return 0
        return len(self.times)

    @abstractproperty
    def n_samples(self):
        pass

    @abstractproperty
    def is_valid_part(self):
        pass

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}"
                for attr in [
                    "number",
                    "start_epoch_ns",
                    "offset_ns",
                    "n_timestamps",
                    "n_samples",
                    "is_valid_part",
                ]
            )
            + ">"
        )


class ArrayPart(Part):
    @property
    def n_samples(self):
        if not self.values:
            return 0
        return len(self.values)


class IMUPart(ArrayPart):
    def __init__(self, recording, number: int, imu: IMUReader, times: T.Sequence[int]):
        self.recording = recording
        self.number = number
        self.times = times
        self.values = imu

    @property
    def is_valid_part(self):
        MAX_TIMESTAMP_DIFFERENCE = 5
        valid = True
        if not self.times:
            valid = False
        if not self.values:
            valid = False
        if abs(self.n_samples - self.n_timestamps) > MAX_TIMESTAMP_DIFFERENCE:
            valid = False
        return valid


class GazePart(ArrayPart):
    def __init__(
        self, recording, number: int, gaze: GazeReader, times: T.Sequence[int]
    ):
        self.recording = recording
        self.number = number
        self.times = times
        self.values = gaze

    @property
    def is_valid_part(self):
        MAX_TIMESTAMP_DIFFERENCE = 0
        valid = True
        if not self.times:
            valid = False
        if not self.values:
            valid = False
        if abs(self.n_samples - self.n_timestamps) > MAX_TIMESTAMP_DIFFERENCE:
            valid = False
        return valid


class WornPart(ArrayPart):
    def __init__(
        self, recording, number: int, worn: WornReader, times: T.Sequence[int]
    ):
        self.recording = recording
        self.number = number
        self.times = times
        self.values = worn

    @property
    def is_valid_part(self):
        MAX_TIMESTAMP_DIFFERENCE = 0
        valid = True
        if not self.times:
            valid = False
        if not self.values:
            valid = False
        if abs(self.n_samples - self.n_timestamps) > MAX_TIMESTAMP_DIFFERENCE:
            valid = False
        return valid


class VideoPart(Part):
    def __init__(self, recording, number: int, video: VideoReader, times: TimeReader):
        self.recording = recording
        self.number = number
        self.video = video
        self.times = times

    @property
    def n_samples(self):
        if not self.video:
            return None
        return self.video.n_frames_video

    @property
    def is_mp4(self):
        if not self.video:
            return None
        return self.video.is_mp4

    @property
    def has_audio(self):
        if not self.video:
            return None
        return self.video.has_audio

    @property
    def is_valid_part(self):
        MAX_TIMESTAMP_DIFFERENCE = 10
        if not self.times:
            return False
        if not self.video:
            return False

        # mp4 video files use pts as timestamps -> only check for mjpeg
        if (
            not self.is_mp4
            and abs(self.n_samples - self.n_timestamps) > MAX_TIMESTAMP_DIFFERENCE
        ):
            return False
        return True


class WorldPart(VideoPart):
    pass


class EyePart(VideoPart):
    pass


class AudioPart(VideoPart):
    pass
