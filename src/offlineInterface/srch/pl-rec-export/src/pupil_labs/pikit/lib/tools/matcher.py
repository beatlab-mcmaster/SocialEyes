import typing as T
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum

from ..sensors import RecordingTimestamp
from ..sensors import Sample
from .iterfuncs import iter_with_next


@dataclass
class MatchingData(Sample):
    __slots__ = ["base_sample", "matches"]
    base_sample: Sample
    matches: T.List[T.List[Sample]]


class ChronologicalOrder(Enum):
    BEFORE = -2
    PARTIAL_BEFORE = -1
    DURING = 0
    PARTIAL_AFTER = 1
    AFTER = 2


def get_sample_timeinterval(
    sample: Sample, duration: int
) -> T.Tuple[RecordingTimestamp, RecordingTimestamp]:
    """Return a tuple of RecordingTimestamps marking beginning and end of data sample,
    with end = sample.timestamp.epoch_ns + duration

    Args:
        sample (Sample): data sample
        duration (int): duration of sample in ns

    Returns:
         T.Tuple[RecordingTimestamp, RecordingTimestamp]: Sample time interval
    """
    return (
        sample.timestamp,
        RecordingTimestamp(
            recording=sample.recording,
            timestamp=sample.timestamp.epoch_ns + round(duration),
        ),
    )


class MatchingMethod(Enum):
    INTERVAL = 0
    CLOSEST = 1
    ALL_CLOSE = 2

    def get_base_timeintervals(
        self, base_data: T.Iterable[Sample]
    ) -> T.Tuple[RecordingTimestamp, int]:
        """Timeinterval used to find matching data

        Args:
            base_data ([T.Iterable[Sample]]): Sensor data used for matching

        Returns:
            Iterator[T.Tuple[RecordingTimestamp, int]]:
                (RecordingTimestamp, duration: int) for every base datum
        """
        if self.name == "INTERVAL":
            return self.get_range_timeintervals(base_data)
        elif self.name == "ALL_CLOSE":
            return self.get_closest_timeintervals(base_data)
        elif self.name == "CLOSEST":
            return self.get_point_timeintervals(base_data)

    def get_matching_timeintervals(
        self, matching_data: T.Iterable[Sample]
    ) -> T.Tuple[RecordingTimestamp, int]:
        """Timeinterval used to find matching data

        Args:
            matching_data ([T.Iterable[Sample]]): Sensor data used for matching

        Returns:
            Iterator[T.Tuple[RecordingTimestamp, int]]:
                (RecordingTimestamp, duration: int) for every base datum
        """
        if self.name == "INTERVAL":
            return self.get_range_timeintervals(matching_data)
        elif self.name == "ALL_CLOSE":
            return self.get_point_timeintervals(matching_data)
        elif self.name == "CLOSEST":
            return self.get_closest_timeintervals(matching_data)

    def get_point_timeintervals(
        self, base_data: T.Iterable[Sample]
    ) -> T.Tuple[RecordingTimestamp, int]:
        """Timeintervals with start at beginning of every base sample and duration 0

        Example:
            base_data:     |--------|-----|------------|----------|

            return:        |        |     |            |          |

        Args:
            base_data ([T.Iterable[Sample]]): Sensor data used for matching

        Yields:
            Iterator[T.Tuple[RecordingTimestamp, int]]: Timestamp and duration
        """
        for sample in base_data:
            yield sample, get_sample_timeinterval(sample, 0)

    def get_range_timeintervals(
        self, base_data: T.Iterable[Sample]
    ) -> T.Tuple[RecordingTimestamp, int]:
        """Timeinterval equal to base data time ranges

        Example:
            base_data:     |--------|-----|------------|----------|

            return:        |--------|-----|------------|----------|

        Args:
            base_data ([T.Iterable[Sample]]): Sensor data used for matching

        Yields:
            Iterator[T.Tuple[RecordingTimestamp, int]]: Timestamp and duration
        """
        for sample in base_data:
            yield sample, get_sample_timeinterval(sample, sample.duration)

    def get_closest_timeintervals(
        self, base_data: T.Iterable[Sample]
    ) -> T.Tuple[RecordingTimestamp, int]:
        """Intervals that contain for every base datum all timestamps that are closest
        to it's (starting) timestamp

        Note: the first base sample only contains a "half"-interval as the previous
            timestamp is not known

        Example:
            base_data:     |--------|-----|------------|----------|

            return:        |----|------|---------|-----------|
                                x      x         x           x
                        (x are center points between two samples)

        Args:
            base_data (T.Iterable[Sample]): Sensor data used for matching

        Returns:
            T.Tuple[RecordingTimestamp, int]: Timestamp and duration

        Yields:
            Iterator[T.Tuple[RecordingTimestamp, RecordingTimestamp]]: start and end
                RecordingTimestamp for every base_data
        """

        first = True
        for sample, next_sample in iter_with_next(base_data):
            if first:
                yield sample, get_sample_timeinterval(sample, sample.duration / 2)
                first = False
            # last
            if next_sample is None:
                break
            start_timestamp = next_sample.timestamp.epoch_ns
            if next_sample.timestamp - sample.timestamp == sample.duration:
                # no gap
                start_timestamp = sample.timestamp.epoch_ns + round(sample.duration / 2)
            yield next_sample, (
                RecordingTimestamp(
                    recording=sample.recording, timestamp=start_timestamp
                ),
                RecordingTimestamp(
                    recording=sample.recording,
                    timestamp=(
                        next_sample.timestamp.epoch_ns + round(next_sample.duration / 2)
                    ),
                ),
            )

    def chronology(
        self,
        base_timeinterval: T.Tuple[RecordingTimestamp, RecordingTimestamp],
        timeinterval: T.Tuple[RecordingTimestamp, RecordingTimestamp],
    ) -> ChronologicalOrder:
        """Chronological Order of timeinterval to a base_timeinterval

        Example:

            base interval:                        |---------------|
                                                .               .
            interval BEFORE:            |----|    .               .
            interval PARTIAL_BEFORE:            |------|          .
            interval DURING:                      .     |----|    .
            interval DURING:                      |               . (duration 0)
            interval PARTIAL_AFTER:               .             |--------|
            interval PARTIAL_AFTER:            |----------------------|
            interval AFTER:                       .               .   |------|
            interval AFTER:                       .               | (duration 0)
                                                  .               .

            Args:
                base_timeinterval (T.Tuple[RecordingTimestamp, RecordingTimestamp]):
                    Time interval to compare to
                timeinterval (T.Tuple[RecordingTimestamp, RecordingTimestamp]):
                    Time interval

            Returns:
                ChronologicalOrder: chronological order of timeinterval to
                    base_timeinterval
        """
        if (
            timeinterval[0] < base_timeinterval[0]
            and timeinterval[1] <= base_timeinterval[0]
        ):
            return ChronologicalOrder.BEFORE
        if (
            timeinterval[0] < base_timeinterval[0]
            and timeinterval[1] <= base_timeinterval[1]
        ):
            return ChronologicalOrder.PARTIAL_BEFORE
        if timeinterval[0] >= base_timeinterval[1]:
            return ChronologicalOrder.AFTER
        if (
            timeinterval[0] < base_timeinterval[1]
            and timeinterval[1] > base_timeinterval[1]
        ):
            return ChronologicalOrder.PARTIAL_AFTER
        return ChronologicalOrder.DURING


class Sampler(ABC):
    @abstractmethod
    def __call__(
        self, stream_samples: T.List[T.List[Sample]], base_sample: Sample
    ) -> T.List[T.List[Sample]]:
        pass


class SampleAll(Sampler):
    def __call__(
        self, stream_samples: T.List[T.List[Sample]], base_sample: Sample
    ) -> T.List[T.List[Sample]]:
        """Return all matches for each stream

        Args:
            stream_samples (T.List[T.List[Sample]]): List of matches for each stream
                that match with base_sample
            base_sample (Sample): base sample that was used for matching

        Returns:
            T.List[T.List[Sample]]: all samples for each stream
        """
        return stream_samples


class SampleOne(Sampler):
    def __call__(
        self, stream_samples: T.List[T.List[Sample]], base_sample: Sample
    ) -> T.List[T.List[Sample]]:
        """Find closest sample for each stream to base_sample.timestamp

        Args:
            stream_samples (T.List[T.List[Sample]]): List of matches for each stream
                that match with base_sample
            base_sample (Sample): base sample that was used for matching

        Returns:
            T.List[T.List[Sample]]: one or none sample for each stream
        """
        closest_matches = []
        for samples in stream_samples:
            min_diff = None
            closest_stream_match = []
            for sample in samples:
                diff = abs(sample.timestamp - base_sample.timestamp)
                if min_diff is None or diff < min_diff:
                    min_diff = diff
                    closest_stream_match = [sample]
            closest_matches.append(closest_stream_match)
        return closest_matches


class Matcher:
    def __init__(
        self,
        base_stream: T.Iterator[Sample],
        data_streams: T.List[T.Iterator[Sample]],
        method: MatchingMethod = MatchingMethod.INTERVAL,
        sampler: Sampler = None,
    ):
        """Find matching data to every sample in `base_stream` in all `data_stream`
        based on their timestamps.

        Args:
            base_stream (T.Iterator[Sample]): Stream of samples to align `data_streams`
                to
            data_streams (T.List[T.Iterator[Sample]]): List of streams of samples that
                are aligned with `base_stream`
            method (MatchingMethod, optional): Matching Method, one of INTERVAL,
                CLOSEST, ALL_CLOSE. Defaults to MatchingMethod.INTERVAL.
            sampler (Sampler, optional): Sample output, one of (`None/SampleAll`,
                `SampleOne`). Defaults to None.
        """
        self.base_stream = base_stream
        self.method = method
        self.matching_streams = [
            self.method.get_matching_timeintervals(s) for s in data_streams
        ]
        self.sampler = sampler or SampleAll()

    def __call__(self):
        """Yield MatchingData

        Yields:
            MatchingData: Matches
        """
        brink_stream_samples = [(None, None)] * len(self.matching_streams)
        for base_sample, base_timeinterval in self.method.get_base_timeintervals(
            self.base_stream
        ):
            stream_matches = []
            for stream_index, stream in enumerate(self.matching_streams):
                matching_stream_samples = []
                read_more_samples = True
                brink_stream_sample, brink_timeinterval = brink_stream_samples[
                    stream_index
                ]
                if brink_stream_sample is not None:
                    # For time interval maching, one stream sample can overlap with
                    # several base stream samples, so check the sample that
                    # was on the brink with the last base sample if it also matches
                    # with the current base sample
                    chronology = self.method.chronology(
                        base_timeinterval, brink_timeinterval
                    )
                    if chronology in {
                        ChronologicalOrder.PARTIAL_BEFORE,
                        ChronologicalOrder.DURING,
                    }:
                        matching_stream_samples.append(brink_stream_sample)
                    elif chronology == ChronologicalOrder.PARTIAL_AFTER:
                        matching_stream_samples.append(brink_stream_sample)
                        read_more_samples = False
                    elif chronology == ChronologicalOrder.AFTER:
                        read_more_samples = False
                if read_more_samples:
                    # read as long as timeinterval is PARTIAL_AFTER/AFTER than
                    # base_timeinterval
                    for sample, timeinterval in stream:
                        chronology = self.method.chronology(
                            base_timeinterval, timeinterval
                        )
                        if chronology in {
                            ChronologicalOrder.PARTIAL_BEFORE,
                            ChronologicalOrder.DURING,
                        }:
                            matching_stream_samples.append(sample)
                        elif chronology == ChronologicalOrder.PARTIAL_AFTER:
                            matching_stream_samples.append(sample)
                            brink_stream_samples[stream_index] = (sample, timeinterval)
                            break
                        elif chronology == ChronologicalOrder.AFTER:
                            brink_stream_samples[stream_index] = (sample, timeinterval)
                            break
                stream_matches.append(matching_stream_samples)
            yield MatchingData(
                recording=base_sample.recording,
                timestamp=base_timeinterval[0],
                duration=base_timeinterval[1] - base_timeinterval[0],
                base_sample=base_sample,
                matches=self.sampler(stream_matches, base_sample),
            )
