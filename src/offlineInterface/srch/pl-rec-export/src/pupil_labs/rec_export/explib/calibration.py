import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Union, cast

import numpy as np
import numpy.typing as npt
import requests
from appdirs import user_cache_dir
from diskcache import Cache

cache_dir = Path(user_cache_dir("pupil-labs"))
calibrations_cache = Cache(cache_dir / "calibrations")


logger = logging.getLogger(__name__)


class Calibration:
    """
    Base class for hardware calibration data
    """

    dtype: np.dtype

    @classmethod
    def from_file(cls, file_path: Union[Path, str]):
        file = Path(file_path)
        return cls.from_binary(file.open("rb").read())

    @classmethod
    def from_binary(cls, bytes: bytes):
        data = np.frombuffer(bytes, dtype=cls.dtype)
        if len(data) != 1:
            raise ValueError("invalid calibration data")
        return cls(*data[0])

    @classmethod
    def to_json(cls, bytes_object):
        calibration_data = np.frombuffer(
            bytes_object,
            cls.dtype,
        )[0]
        result = {
            name: calibration_data[name].tolist()
            for name in calibration_data.dtype.names
        }
        result["serial"] = calibration_data["serial"].decode("utf8")
        return result


@dataclass
class InvisibleCalibration(Calibration):
    serial: str
    scene_camera_matrix: npt.NDArray[np.float32]
    scene_distortion_coefficients: npt.NDArray[np.float32]
    rotation_matrix: npt.NDArray[np.float32]

    dtype = np.dtype(
        [
            ("serial", "5a"),
            ("scene_camera_matrix", "(3,3)d"),
            ("scene_distortion_coefficients", "8d"),
            ("rotation_matrix", "(3,3)d"),
        ]
    )

    def __post_init__(self):
        if isinstance(self.serial, bytes):
            self.serial = self.serial.decode("utf8")

    @classmethod
    def from_cloud(cls, serial: str):
        if serial == "default":
            serial = "00000"

        calibration_binary = fetch_pi_calibration_binary_from_cloud(serial)
        calibration = cls.from_binary(calibration_binary)
        if calibration.serial != serial:
            raise ValueError("invalid calibration data")
        return calibration


def fetch_pi_calibration_binary_from_cloud(serial: str) -> bytes:
    if serial == "default":
        serial = "00000"

    if serial not in calibrations_cache:
        logger.debug(f"using cached calibration data: {serial}")

        base_url = (
            "https://pupil-invisible-hardware-calibrations"
            ".s3.eu-central-1.amazonaws.com"
        )
        version = "v1"
        response = requests.get(base_url + "/" + version + "/" + serial)
        response.raise_for_status()

        calibration_binary = response.content
        logger.debug(
            f"fetched calibration data for {serial} ({len(calibration_binary)} bytes)"
        )
        calibrations_cache[serial] = calibration_binary
    return cast(bytes, calibrations_cache[serial])


@dataclass
class NeonCalibration(Calibration):
    version: int
    serial: str
    scene_camera_matrix: npt.NDArray[np.float32]
    scene_distortion_coefficients: npt.NDArray[np.float32]
    scene_extrinsics_affine_matrix: npt.NDArray[np.float32]
    right_camera_matrix: npt.NDArray[np.float32]
    right_distortion_coefficients: npt.NDArray[np.float32]
    right_extrinsics_affine_matrix: npt.NDArray[np.float32]
    left_camera_matrix: npt.NDArray[np.float32]
    left_distortion_coefficients: npt.NDArray[np.float32]
    left_extrinsics_affine_matrix: npt.NDArray[np.float32]
    crc: int

    dtype = np.dtype(
        [
            ("version", "u1"),
            ("serial", "6a"),
            ("scene_camera_matrix", "(3,3)d"),
            ("scene_distortion_coefficients", "8d"),
            ("scene_extrinsics_affine_matrix", "(4,4)d"),
            ("right_camera_matrix", "(3,3)d"),
            ("right_distortion_coefficients", "8d"),
            ("right_extrinsics_affine_matrix", "(4,4)d"),
            ("left_camera_matrix", "(3,3)d"),
            ("left_distortion_coefficients", "8d"),
            ("left_extrinsics_affine_matrix", "(4,4)d"),
            ("crc", "u4"),
        ]
    )

    def __post_init__(self):
        if isinstance(self.serial, bytes):
            self.serial = self.serial.decode("utf8")
