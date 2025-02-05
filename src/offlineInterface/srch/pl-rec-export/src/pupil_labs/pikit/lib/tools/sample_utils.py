import typing as T

from ... import recording
from ..sensors import GazePosition
from ..sensors import GazeSample
from ..sensors import WornSample
from ..sensors import IMUSample


class GazeUtils:
    """Operations on list of gaze samples"""

    @staticmethod
    def average_gaze_sample(
        gaze_samples: T.List[GazeSample],
    ) -> T.List[GazeSample]:
        """Average gaze sample of a list of gaze samples.
        Returned sample duration is the sum of all duration of all input gaze_samples
        Gaze position is the mean of all input gaze_samples

        Args:
            gaze_samples (T.List[GazeSample]): List of gaze samples

        Returns:
            T.List[GazeSample]: List containing the average gaze sample,
                emtpy list if gaze_samples is an empty list
        """
        num_samples = len(gaze_samples)
        if num_samples == 0:
            return []

        rec = gaze_samples[0].recording

        average_gaze_position = GazePosition(0, 0, 0)
        for position in ["distorted", "normalized", "rectified"]:
            average_gaze_point = (
                1
                / num_samples
                * (sum(getattr(gm.position, position) for gm in gaze_samples))
            )
            setattr(average_gaze_position, position, average_gaze_point)
        total_duration = sum([gm.duration for gm in gaze_samples])
        # print(gaze_samples[0])
        return [
            GazeSample(
                recording=rec,
                timestamp=recording.RecordingTimestamp(
                    recording=rec, timestamp=gaze_samples[0].timestamp.epoch_ns
                ),
                duration=total_duration,
                position=average_gaze_position,
            )
        ]

    @staticmethod
    def weighted_average_gaze_sample(
        gaze_samples: T.List[GazeSample],
    ) -> T.List[GazeSample]:
        """Weighted average gaze sample of a list of gaze samples by their durations.
        Returned sample duration is the sum of all duration of all input gaze_samples
        Gaze position is the weighted average of all input gaze_samples by their
        durations

        Args:
            gaze_samples (T.List[GazeSample]): List of gaze samples

        Returns:
            T.List[GazeSample]: List containing the weighted average gaze sample,
                emtpy list if gaze_samples is an empty list
        """
        raise NotImplementedError()

    @staticmethod
    def all_gaze_sample(gaze_samples: T.List[GazeSample]) -> T.List[GazeSample]:
        """Return all input gaze samples

        Args:
            gaze_samples (T.List[GazeSample]): List of gaze samples

        Returns:
            T.List[GazeSample]: List of gaze samples
        """
        return gaze_samples

    @staticmethod
    def first_gaze_sample(gaze_samples: T.List[GazeSample]) -> T.List[GazeSample]:
        """Return the first gaze sample in the input

        Args:
            gaze_samples (T.List[GazeSample]): List of gaze samples

        Returns:
            T.List[GazeSample]: List containing first element of gaze_samples, emtpy
                list if gaze_samples is an empty list
        """
        if not gaze_samples:
            return []
        return [gaze_samples[0]]


class IMUUtils:
    """Operations on list of imu samples"""

    @staticmethod
    def average_imu_sample(
        imu_samples: T.List[IMUSample],
    ) -> T.List[IMUSample]:
        """Average imu sample of a list of imu samples.
        Returned sample duration is the sum of all duration of all input imu_samples
        IMU position is the mean of all input imu_samples

        Args:
            imu_samples (T.List[IMUSample]): List of imu samples

        Returns:
            T.List[IMUSample]: List containing the average imu sample,
                emtpy list if imu_samples is an empty list
        """
        num_samples = len(imu_samples)
        if num_samples == 0:
            return []

        rec = imu_samples[0].recording

        average_acceleration = (
            1 / num_samples * (sum(imu.acceleration for imu in imu_samples))
        )
        average_gyroscope = (
            1 / num_samples * (sum(imu.gyroscope for imu in imu_samples))
        )

        total_duration = sum([imu.duration for imu in imu_samples])

        return [
            IMUSample(
                recording=rec,
                timestamp=recording.RecordingTimestamp(
                    recording=rec, timestamp=imu_samples[0].timestamp.epoch_ns
                ),
                duration=total_duration,
                acceleration=average_acceleration,
                gyroscope=average_gyroscope,
            )
        ]

    @staticmethod
    def weighted_average_imu_sample(
        imu_samples: T.List[IMUSample],
    ) -> T.List[IMUSample]:
        """Weighted average imu sample of a list of imu samples by their durations.
        Returned sample duration is the sum of all duration of all input imu_samples.
        IMU data is the weighted average of all input imu_samples by their
        durations

        Args:
            imu_samples (T.List[IMUSample]): List of imu samples

        Returns:
            T.List[IMUSample]: List containing the weighted average imu sample,
                emtpy list if imu_samples is an empty list
        """
        raise NotImplementedError()

    @staticmethod
    def all_imu_sample(imu_samples: T.List[IMUSample]) -> T.List[IMUSample]:
        """Return all input imu samples

        Args:
            imu_samples (T.List[IMUSample]): List of imu samples

        Returns:
            T.List[IMUSample]: List of imu_samples
        """
        return imu_samples

    @staticmethod
    def first_imu_sample(imu_samples: T.List[IMUSample]) -> T.List[IMUSample]:
        """Return the first imu sample in the input

        Args:
            imu_samples (T.List[IMUSample]): List of imu samples

        Returns:
            T.List[IMUSample]: List containing first element of imu_samples,
                emtpy list if imu_samples is an empty list
        """
        if not imu_samples:
            return []
        return [imu_samples[0]]


class WornUtils:
    """Operations on list of worn samples"""

    @staticmethod
    def average_worn_sample(
        worn_samples: T.List[WornSample],
    ) -> T.List[WornSample]:
        """Average worn sample of a list of worn samples.
        Returned sample duration is the sum of all duration of all input worn_samples

        Args:
            worn_samples (T.List[WornSample]): List of worn samples

        Returns:
            T.List[WornSample]: List containing the average worn sample,
                emtpy list if worn_samples is an empty list
        """
        num_samples = len(worn_samples)
        if num_samples == 0:
            return []
        rec = worn_samples[0].recording
        total_duration = sum([gm.duration for gm in worn_samples])

        # print(f"worn {worn_samples[0]}")
        return [
            WornSample(
                recording=rec,
                timestamp=recording.RecordingTimestamp(
                    recording=rec, timestamp=worn_samples[0].timestamp.epoch_ns
                ),
                duration=total_duration,
                worn=worn_samples[0].worn
            )
        ]

    @staticmethod
    def weighted_average_worn_sample(
        worn_samples: T.List[WornSample],
    ) -> T.List[WornSample]:
        """Weighted average worn sample of a list of worn samples by their durations.
        Returned sample duration is the sum of all duration of all input worn_samples

        Args:
            worn_samples (T.List[WornSample]): List of worn samples

        Returns:
            T.List[WornSample]: List containing the weighted average worn sample,
                emtpy list if worn_samples is an empty list
        """
        raise NotImplementedError()

    @staticmethod
    def all_worn_sample(worn_samples: T.List[WornSample]) -> T.List[WornSample]:
        """Return all input worn samples

        Args:
            worn_samples (T.List[WornSample]): List of worn samples

        Returns:
            T.List[WornSample]: List of worn samples
        """
        return worn_samples

    @staticmethod
    def first_worn_sample(worn_samples: T.List[WornSample]) -> T.List[WornSample]:
        """Return the first worn sample in the input
        Args:
            worn_samples (T.List[WornSample]): List of worn samples

        Returns:
            T.List[WornSample]: List containing first element of worn_samples, emtpy
                list if worn_samples is an empty list
        """
        if not worn_samples:
            return []
        return [worn_samples[0]]
