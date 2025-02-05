import datetime
import functools
import itertools
import json
import logging
import pathlib
import typing as T
import urllib
from collections import OrderedDict
from dataclasses import dataclass

import fs.zipfs
import numpy as np
from natsort import natsorted

from .event import Event
from .lib.binary import File, URLFileReader
from .lib.camera import NeonSceneCamera, PISceneCamera
from .lib.clickhouse_db import NoDBConnectionException
from .lib.readers import TimeReader
from .lib.recording_parts import RecordingParts
from .lib.sensors import (
    AudioSensor,
    EyeSensor,
    Gaze200DBSensor,
    Gaze200Sensor,
    GazeSensor,
    IMUSensor,
    RecordingTimestamp,
    WorldSensor,
    WornDBSensor,
    WornSensor,
)

logger = logging.getLogger(__name__)


class InvalidRecording(Exception):
    """Exception for an invalid recording"""


class Files(list):
    @classmethod
    def from_fs(cls, fs_uri: T.Union[str, pathlib.Path]):
        if isinstance(fs_uri, pathlib.Path):
            fs_uri = str(fs_uri.resolve())

        if "://" not in fs_uri:
            fs_uri = urllib.parse.quote(fs_uri)
            if fs_uri.endswith(".zip"):
                fs_uri = f"zip://{fs_uri}"
            else:
                fs_uri = f"file://{fs_uri}"

        if fs_uri.endswith(".zip") and not fs_uri.startswith("zip://"):
            fs_uri = f"zip://{fs_uri}"

        if fs_uri.startswith("zip://http://") or fs_uri.startswith("zip://https://"):
            filesystem = fs.zipfs.ZipFS(URLFileReader(fs_uri[6:]), write=False)
        else:
            filesystem = fs.open_fs(fs_uri, writeable=False)

        folders = filesystem.listdir(".")
        if len(folders) == 1 and folders[0] != "info.json":
            filesystem = filesystem.opendir(folders[0])

        result = Files()
        for item in filesystem.scandir(".", namespaces=["details"]):
            if not item.is_file:
                continue

            result.append(
                File(
                    name=item.name,
                    size=item.size,
                    open=functools.partial(filesystem.open, item.name),
                )
            )
        return result


@dataclass
class GazeOffset:
    __slots__ = ["x", "y"]
    x: float
    y: float


class Recording(object):
    InvalidRecording = InvalidRecording

    def __init__(
        self,
        files: T.Union[Files, str, pathlib.Path],
        info=None,
        strict_decoding=False,
        use_world_time_files=False,
    ):
        """
        Recording wraps a PI recording

        Args:
            files: List of files for the recording
            info: PI recording info.json dict (otherwise will try to read from files)
            strict_decoding: Raise exception on decoding errors, otherwise warn
        """
        self.strict_decoding = strict_decoding
        self.use_world_time_files = use_world_time_files

        if not isinstance(files, Files):
            files = Files.from_fs(files)

        self.files: T.Dict[str, File] = OrderedDict()
        for file in natsorted(files, key=lambda f: f.name):
            self.files[file.name] = file

        self._info = info

        if not self.info:
            raise InvalidRecording("missing info.json")

        self._wearer_json = None
        self._template_json = None

        self.recording_parts = RecordingParts(recording=self)

    @property
    def events(self):
        event_name_file = self.files.get("event.txt")
        event_time_file = self.files.get("event.time")
        event_times = []
        event_names = []
        if event_name_file:
            event_names = []
            event_names = [
                x.strip().decode("utf8") for x in event_name_file.open("rb").readlines()
            ]
        if event_time_file:
            event_times = TimeReader(event_time_file).values

        result = []
        for epoch_ns, name in itertools.zip_longest(event_times, event_names):
            offset_ns = None
            if epoch_ns is not None:
                offset_ns = epoch_ns - self.start_epoch_ns
            event = Event(name=name, epoch_ns=epoch_ns, offset_ns=offset_ns)
            result.append(event)

        return result

    @property
    def info(self):
        if self._info is None:
            info_json_file = self.files.get("info.json")
            if info_json_file:
                self._info = json.loads(info_json_file.open("rb").read())
        return self._info

    @property
    def wearer_json(self):
        if self._wearer_json is None:
            wearer_json_file = self.recording_parts.wearer_json
            if wearer_json_file:
                self._wearer_json = json.loads(wearer_json_file.open("rb").read())
        return self._wearer_json

    @property
    def template_json(self):
        if self._template_json is None:
            template_json_file = self.recording_parts.template_json
            if template_json_file:
                self._template_json = json.loads(template_json_file.open("rb").read())
        return self._template_json

    @property
    def has_audio(self):
        has_audio = False
        for world_part in self.recording_parts.world:
            video = world_part.video
            if video and video.has_audio:
                has_audio = True
                break
        return has_audio

    def is_silent(self, threshold=0.01):
        """
        Naive way of checking if recording is silent
        """
        for world_part in self.recording_parts.world:
            video = world_part.video
            if video and video.has_audio:
                for frame in video.container.decode(audio=0):
                    if (abs(frame.to_ndarray()[0]) > threshold).any():
                        return False
        return True

    @property
    def family(self) -> T.Literal["neon", "pi", None]:
        info = self.info or {}
        if (info.get("data_format_version") or "").startswith("1."):
            return "pi"
        if (info.get("data_format_version") or "").startswith("2."):
            return "neon"
        return None

    @property
    def scene_camera(self):
        if self.files.get("calibration.bin"):
            calibration_data = self.files["calibration.bin"].open("rb").read()
            if self.family == "neon":
                return NeonSceneCamera.from_binary(calibration_data)
            elif self.family == "pi":
                return PISceneCamera.from_binary(calibration_data)

        return PISceneCamera.load(self.scene_camera_serial_number)

    @property
    def start_timestamp(self) -> RecordingTimestamp:
        return RecordingTimestamp(recording=self, timestamp=self.start_epoch_ns)

    @property
    def end_timestamp(self) -> RecordingTimestamp:
        return RecordingTimestamp(
            recording=self, timestamp=self.start_timestamp.epoch_ns + self.duration_ns
        )

    @property
    def start_epoch_ns(self):
        return self.info["start_time"]

    @property
    def duration_ns(self):
        return self.info["duration"]

    @property
    def duration_s(self):
        return self.duration_ns / 1e9

    @property
    def end_epoch_ns(self):
        return self.start_epoch_ns + self.duration_ns

    @property
    def pipeline_version(self):
        return self.info.get("pipeline_version")

    @property
    def calibration_version(self):
        return self.info.get("calib_version")

    @property
    def android_device_name(self):
        return self.info.get("android_device_name")

    @property
    def glasses_serial_number(self):
        return self.info.get("glasses_serial_number")

    @property
    def scene_camera_serial_number(self):
        return self.info.get("scene_camera_serial_number")

    @property
    def android_device_model(self):
        return self.info.get("android_device_model")

    @property
    def data_format_version(self):
        return self.info.get("data_format_version")

    @property
    def id(self):
        return self.info.get("recording_id")

    @property
    def start_datetime(self):
        if self.start_epoch_ns:
            return datetime.datetime.fromtimestamp(
                self.start_epoch_ns / 1e9, tz=datetime.timezone.utc
            )

    @property
    def start_datetime_str(self):
        return str(self.start_datetime)

    @property
    def template_data(self):
        return self.info.get("template_data") or {}

    @property
    def name(self):
        return self.template_data.get("recording_name")

    @property
    def wearer_id(self):
        return self.info.get("wearer_id")

    @property
    def gaze_offset(self):
        gaze_offset = self.info.get("gaze_offset")
        x, y = gaze_offset
        return GazeOffset(x, y)

    @property
    def filenames(self):
        return list(self.files.keys())

    @property
    def world(self) -> WorldSensor:
        """World sensor to access world frames of multi-part files

        Returns:
            WorldSensor: world sensor instance
        """
        if not getattr(self, "_world_sensor", None):
            self._world_sensor = WorldSensor(
                self,
                strict_decoding=self.strict_decoding,
                times_from_time_files=self.use_world_time_files,
            )
        return self._world_sensor

    @property
    def audio(self) -> AudioSensor:
        """Audio sensor to access audio data of multi-part files

        Returns:
            AudioSensor: audio sensor instance
        """
        if self.has_audio:
            if not getattr(self, "_audio_sensor", None):
                self._audio_sensor = AudioSensor(
                    self, strict_decoding=self.strict_decoding
                )
            return self._audio_sensor

    @property
    def eye_right(self) -> EyeSensor:
        """Eye sensor to access right eye frames of multi-part files

        Returns:
            EyeSensor: Eye sensor instance
        """
        if not getattr(self, "_eye_right_sensor", None):
            self._eye_right_sensor = EyeSensor(
                recording=self, eye="right", strict_decoding=self.strict_decoding
            )
        return self._eye_right_sensor

    @property
    def eye_left(self) -> EyeSensor:
        """Eye sensor to access left eye frames of multi-part files

        Returns:
            EyeSensor: eye sensor instance
        """
        if not getattr(self, "_eye_left_sensor", None):
            self._eye_left_sensor = EyeSensor(
                recording=self, eye="left", strict_decoding=self.strict_decoding
            )
        return self._eye_left_sensor

    @property
    def gaze(self) -> GazeSensor:
        """Gaze sensor to access gaze data of multi-part files

        Returns:
            GazeSensor: gaze sensor instance
        """
        if not getattr(self, "_gaze_sensor", None):
            self._gaze_sensor = GazeSensor(self)
        return self._gaze_sensor

    @property
    def scanpath_data(self):
        """Fixations sensor to access fixation data

        Returns:
            FixationsSensor: fixation sensor instance
        """
        #   {
        #     "start_offset_ns": 11849183692,
        #     "stop_offset_ns": 11899183692,
        #     "path": [
        #       {
        #         "x": 592,
        #         "y": 810,
        #         "id": 23,
        #         "ms": 260
        #       },
        #     ]
        #   }
        if not getattr(self, "_scanpath_data", None):
            self._scanpath_data = None
            scanpath_json_file = self.files.get("scanpath.json")
            if scanpath_json_file:
                try:
                    self._scanpath_data = json.loads(
                        scanpath_json_file.open("rb").read()
                    )
                except Exception as e:
                    logger.warning("failed to load scanpath data: {e}")
            else:
                logger.warning("no scanpath data available")
        return self._scanpath_data or []

    @property
    def gaze200_db(self):
        if not getattr(self, "_gaze200_db_sensor", None):
            self._gaze200_db_sensor = Gaze200DBSensor(self)
        return self._gaze200_db_sensor

    @property
    def worn_db(self):
        if not getattr(self, "_worn_db_sensor", None):
            self._worn_db_sensor = WornDBSensor(self)
        return self._worn_db_sensor

    @property
    def gaze200(self) -> Gaze200Sensor:
        """gaze200 sensor to access gaze data from Clickhouse db

        Returns:
            Gaze200Sensor: gaze200 sensor instance
        """
        if not getattr(self, "_gaze200_sensor", None):
            self._gaze200_sensor = Gaze200Sensor(self)
        return self._gaze200_sensor

    @property
    def imu(self) -> IMUSensor:
        """IMU sensor to access IMU data of multi-part files

        Returns:
            IMUSensor: imu sensor instance
        """
        if not getattr(self, "_imu_sensor", None):
            self._imu_sensor = IMUSensor(self)
        return self._imu_sensor

    @property
    def worn(self) -> WornSensor:
        """Worn sensor to access worn data of multi-part files

        Returns:
            WornSensor: worn sensor instance
        """
        if not getattr(self, "_worn_sensor", None):
            self._worn_sensor = WornSensor(self)
        return self._worn_sensor

    def timestamp_at_offset(self, seconds=0, nanoseconds=0):
        """
        Returns the epoch timestamp at offset

        Args:
            seconds (int): offset in seconds
            nanoseconds (int): offset in seconds

        Examples:
            >>> recording.timestamp_at_offset(seconds=3)
            1582082047876907580

            >>> recording.timestamp_at_offset(seconds=2, nanoseconds=1000000000)
            1582082047876907580

        """

        return self.start_epoch_ns + int(seconds * 1e9) + int(nanoseconds)

    def seek(self, timestamp_ns):
        """Seek all sensors to timestamp_ns

        Args:
            timestamp_ns (int): timestamp in epoch_ns
        """
        self.imu.seek(timestamp_ns)
        self.gaze.seek(timestamp_ns)
        self.world.seek(timestamp_ns)
        self.eye_left.seek(timestamp_ns)
        self.eye_right.seek(timestamp_ns)
        self.gaze200.seek(timestamp_ns)
        try:
            self.gaze200_db.seek(timestamp_ns)
        except NoDBConnectionException:
            pass

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}"
                for attr in ["id", "name", "start_datetime_str", "duration_s"]
            )
            + ">"
        )
