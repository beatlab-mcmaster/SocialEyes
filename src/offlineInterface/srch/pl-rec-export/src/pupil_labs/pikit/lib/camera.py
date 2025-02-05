import struct
import typing as T
import warnings

import av
import cv2
import numpy as np
import requests

from .constants import (
    NEON_SCENE_HEIGHT,
    NEON_SCENE_WIDTH,
    PI_SCENE_HEIGHT,
    PI_SCENE_WIDTH,
)
from .projection import (
    distort_points_accurate,
    distort_points_fast,
    normalize_points_accurate,
    normalize_points_fast,
    rectifyFrame,
)


class BaseSceneCamera(object):
    camera_matrix: np.ndarray
    distortion_coefficients: np.ndarray
    frame_width: int
    frame_height: int
    __undistorted_camera_matrix = None

    @property
    def dist_coefs(self):
        return self.distortion_coefficients

    @property
    def undistorted_camera_matrix(self):
        if self.__undistorted_camera_matrix is None:
            self.__undistorted_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
                cameraMatrix=np.asarray(self.camera_matrix),
                distCoeffs=np.asarray(self.distortion_coefficients),
                imageSize=(self.frame_width, self.frame_height),
                newImgSize=(self.frame_width, self.frame_height),
                alpha=0,
                centerPrincipalPoint=False,
            )
        return self.__undistorted_camera_matrix

    def normalize_point(self, point: T.List, fast: bool = True) -> T.List:
        """Convert point from distorted image coordinates to normalized coordinates

        Args:
            point (T.List): [x, y] coordinates of point in image
            fast (bool, optional): use cv2.undistortPoints if `fast` else run
                optimization manually (much slower, more accurate). Defaults to True.

        Returns:
            [T.List]: [x_norm, y_norm] normalized coordinates
        """
        if fast:
            return normalize_points_fast(
                [point], self.camera_matrix, self.distortion_coefficients
            )[0]
        return normalize_points_accurate(
            [point], self.camera_matrix, self.distortion_coefficients
        )[0]

    def normalize_points(
        self, points: T.List[T.List], fast: bool = True
    ) -> T.List[T.List]:
        """Convert points from distorted image coordinates to normalized coordinates

        Args:
            points (T.List[T.List]): [[x, y],...] coordinates of points in image
            fast (bool, optional): use cv2.undistortPoints if `fast` else run
                optimization manually (much slower, more accurate). Defaults to True.

        Returns:
            [T.List[T.List]]: [[x_norm, y_norm],...] normalized coordinates
        """

        if fast:
            return normalize_points_fast(
                points, self.camera_matrix, self.distortion_coefficients
            )
        return normalize_points_accurate(
            points, self.camera_matrix, self.distortion_coefficients
        )

    def distort_point(self, point: T.List, fast: bool = True) -> T.List:
        """Convert point from normalized coordinates to distorted image coordinates

        Args:
            point (T.List): [x, y] normalized coordinates
            fast (bool, optional): use cv2.projectPoints if `fast` else run
                projection manually (much slower). Defaults to True.

        Returns:
            [T.List]: [x_dist, y_dist] distorted image coordinates
        """
        if fast:
            return distort_points_fast(
                [point], self.camera_matrix, self.distortion_coefficients
            )[0]
        return distort_points_accurate(
            [point], self.camera_matrix, self.distortion_coefficients
        )[0]

    def distort_points(
        self, points: T.List[T.List], fast: bool = True
    ) -> T.List[T.List]:
        """Convert points from normalized coordinates to distorted image coordinates

        Args:
            points (T.List[T.List]): [[x, y], ...] normalized coordinates
            fast (bool, optional): use cv2.projectPoints if `fast` else run
                projection manually (much slower). Defaults to True.

        Returns:
            [T.List[T.List]]: [[x_dist, y_dist],...] distorted image coordinates
        """
        if fast:
            return distort_points_fast(
                points, self.camera_matrix, self.distortion_coefficients
            )
        return distort_points_accurate(
            points, self.camera_matrix, self.distortion_coefficients
        )

    def rectifyFrame(self, frame: av.VideoFrame) -> av.VideoFrame:
        """Undistort pyav VideoFrame

        Args:
            frame (av.VideoFrame): Distorted VideoFrame

        Returns:
            av.VideoFrame: Undistorted VideoFrame
        """
        np_frame = frame.to_ndarray(format="bgr24")
        undistorted_frame = rectifyFrame(
            np_frame,
            self.camera_matrix,
            self.distortion_coefficients,
            self.undistorted_camera_matrix,
        )
        output_frame = av.VideoFrame.from_ndarray(undistorted_frame, format="bgr24")
        return output_frame

    def rectify_points(
        self,
        distorted_points: T.List[T.List] = None,
        normalized_points: T.List[T.List] = None,
    ) -> T.List[T.List]:
        """Convert points to rectified image coordinates. Either provide
        `distorted_points` or `normalized_points`

        Args:
            distorted_points (T.List[T.List], optional): [[x, y], ...] Distorted point
                coordinates. Defaults to None.
            normalized_point (T.List[T.List], optional):  [[x, y], ...] Normalized
                point coordinates. Defaults to None.

        Raises:
            Exception: Either provide `distorted_points` or `normalized_points`, not
                both

        Returns:
            T.List[T.List]: [[x_rect, y_rect], ...] rectified coordinates
        """
        if distorted_points is not None and normalized_points is not None:
            raise Exception()
        points = normalized_points
        camera_matrix = np.eye(3)
        dist_coeffs = [0, 0, 0, 0, 0]
        if distorted_points is not None:
            points = distorted_points
            camera_matrix = self.camera_matrix
            dist_coeffs = self.distortion_coefficients
        return normalize_points_fast(
            points, camera_matrix, dist_coeffs, self.undistorted_camera_matrix
        )

    def rectify_point(
        self, distorted_point: T.List = None, normalized_point: T.List = None
    ) -> T.List:
        """Convert point to rectified image coordinates. Either provide
        `distorted_point` or `normalized_point`

        Args:
            distorted_point (T.List, optional): [x, y] Distorted point coordinates.
                Defaults to None.
            normalized_point (T.List, optional):  [x, y] Normalized point coordinates.
                Defaults to None.

        Raises:
            Exception: Either provide `distorted_point` or `normalized_point`, not both

        Returns:
            T.List: [x_rect, y_rect] rectified coordinates
        """

        if distorted_point is not None and normalized_point is not None:
            raise Exception()
        if distorted_point:
            return self.rectify_points(distorted_points=[distorted_point])[0]
        return self.rectify_points(normalized_points=[normalized_point])[0]

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                [f"{attr}={getattr(self, attr, '?')!r}" for attr in ["serial_number"]]
            )
            + ">"
        )


class PISceneCamera(BaseSceneCamera):
    """Pupil Invisible Scene Camera"""

    frame_width = PI_SCENE_WIDTH
    frame_height = PI_SCENE_HEIGHT

    def __init__(
        self, serial_number, camera_matrix, distortion_coefficients, rotation_matrix
    ):
        self.serial_number = serial_number
        self.camera_matrix = camera_matrix
        self.distortion_coefficients = distortion_coefficients
        self.rotation_matrix = rotation_matrix

    def as_v1_calibration_json(self):
        return {
            "serial_number": self.serial_number,
            "camera_matrix": self.camera_matrix,
            "distortion_coefficients": self.distortion_coefficients,
            "rotation_matrix": self.rotation_matrix,
        }

    def as_v1_calibration_binary(self):
        return CameraCalibrationV1.json_to_binary(self.as_v1_calibration_json())

    @classmethod
    def from_binary(cls, calibration_bytes: bytes):
        data = CameraCalibrationV1.binary_to_json(calibration_bytes)
        return PISceneCamera(
            serial_number=data["serial_number"],
            camera_matrix=data["camera_matrix"],
            distortion_coefficients=data["distortion_coefficients"],
            rotation_matrix=data["rotation_matrix"],
        )

    @classmethod
    def load(cls, serial_number: str):
        if not hasattr(cls, "_cache"):
            cls._cache = {}

        if serial_number == "default":
            serial_number = "00000"

        if serial_number in cls._cache:
            return cls._cache[serial_number]

        base_url = (
            "https://pupil-invisible-hardware-calibrations"
            ".s3.eu-central-1.amazonaws.com"
        )
        version = "v1"
        response = requests.get(base_url + "/" + version + "/" + serial_number)
        response.raise_for_status()

        binary_data = response.content
        data = CameraCalibrationV1.binary_to_json(binary_data)

        if not serial_number == data["serial_number"]:
            raise ValueError(
                "The serial number returned from the cloud does not"
                "match the queried serial number!"
            )

        camera = PISceneCamera(
            serial_number=data["serial_number"],
            camera_matrix=data["camera_matrix"],
            distortion_coefficients=data["distortion_coefficients"],
            rotation_matrix=data["rotation_matrix"],
        )
        cls._cache[serial_number] = camera
        return camera


class SceneCamera(PISceneCamera):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "`SceneCamera` is replaced with PISceneCamera`", DeprecationWarning
        )
        PISceneCamera.__init__(*args, **kwargs)


class NeonSceneCamera(BaseSceneCamera):
    """Pupil Neon Scene Camera"""

    frame_width = NEON_SCENE_WIDTH
    frame_height = NEON_SCENE_HEIGHT

    def __init__(self, serial_number, camera_matrix, distortion_coefficients):
        self.serial_number = serial_number
        self.camera_matrix = camera_matrix
        self.distortion_coefficients = distortion_coefficients

    def as_v2_calibration_json(self):
        return {
            "serial_number": self.serial_number,
            "camera_matrix": self.camera_matrix,
            "distortion_coefficients": self.distortion_coefficients,
            # "rotation_matrix": self.rotation_matrix,
        }

    def as_v1_calibration_binary(self):
        return CameraCalibrationV2.json_to_v1_binary(self.as_v2_calibration_json())

    @classmethod
    def from_binary(cls, calibration_bytes: bytes):
        data = CameraCalibrationV2.binary_to_json(calibration_bytes)
        camera = NeonSceneCamera(
            serial_number=data["serial"],
            camera_matrix=data["scene_camera_matrix"],
            distortion_coefficients=[data["scene_distortion_coefficients"]],
        )

        return camera


class CameraCalibrationV1(object):
    """Class for converting v1 camera intrinsics/extrinsics from binary/json format"""

    BYTE_FORMAT = "<5s 9d 8d 9d"

    @classmethod
    def binary_to_json(cls, bytes_object):
        data = struct.unpack(cls.BYTE_FORMAT, bytes_object)
        result = {
            "serial_number": data[0].decode("utf-8"),
            "camera_matrix": np.array(data[1:10], dtype=np.float64)
            .reshape(3, 3)
            .tolist(),
            "distortion_coefficients": np.array(data[10:18], dtype=np.float64)
            .reshape(1, 8)
            .tolist(),
            "rotation_matrix": np.array(data[18:27], dtype=np.float64)
            .reshape(3, 3)
            .tolist(),
        }
        return result

    @classmethod
    def json_to_binary(cls, json_data):
        json_data["serial_number"].encode("utf8")
        result = struct.pack(
            cls.BYTE_FORMAT,
            json_data["serial_number"].encode("utf8"),
            *np.array(json_data["camera_matrix"], dtype=np.float64).reshape(9),
            *np.array(json_data["distortion_coefficients"], dtype=np.float64).reshape(
                8
            ),
            *np.array(json_data["rotation_matrix"], dtype=np.float64).reshape(9),
        )
        return result


class CameraCalibrationV2(object):
    """Class for converting v2 neon camera intrinsics/extrinsics from binary/json format"""

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

    @classmethod
    def binary_to_json(cls, bytes_object):
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

    @classmethod
    def json_to_v1_binary(cls, json_data):
        result = struct.pack(
            CameraCalibrationV1.BYTE_FORMAT,
            json_data["serial_number"].encode("utf8"),
            *np.array(json_data["camera_matrix"], dtype=np.float64).reshape(9),
            *np.array(json_data["distortion_coefficients"], dtype=np.float64).reshape(
                8
            ),
        )
        return result
