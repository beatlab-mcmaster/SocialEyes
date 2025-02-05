""" Main function for fixation detection.
"""

import logging
import time
import typing as T

import numpy as np
from rich.progress import Progress
from scipy.signal import savgol_filter

from . import event_handling, helpers, optic_flow_correction

logger = logging.getLogger(__name__)


class Params(T.NamedTuple):
    """Algorithm parameters with standard values."""

    use_pixels: bool = True  # using pixel velocities or angular velocities
    correct_optic_flow: bool = True  # turn on/off optic flow
    microsaccade_filter: bool = True  # turn on/off micro-saccade filter
    short_fixations_filter: bool = True  # turn on/off short-fixations filter
    vel_thr: int = 900  # velocity threshold
    ang_thr: float = 1.5  # angle threshold
    time_thr: float = 0.06  # time threshold to filter microsaccades (s)
    min_len: float = 0.06  # time threshold to filter short fixations (s)


DEFAULT_PARAMS = Params()


def i_vt(time_axis, gaze_xy_normalized, gaze_xy_distorted, velocity, params=None):
    """Core algorithm for fixation detection.
    Takes preprocessed data and applies velocity threshold as well as post-processing.
    Returns predictions both in sample-based as well as event-based format.

    Args:
        time_axis: time axis in seconds
        gaze_xy_normalized: (N, 2) array, normalized coordinates for each sample
        gaze_xy_distorted: (N, 2) array, distorted coordinates for each sample
        velocity: (N,) array, angular velocities for each sample
        params: parameter of the algorithm

    Returns:
        pred_samples: predicted samples
        pred_events: predicted event sequence
    """
    # get parameters
    if params is None:
        params = Params()

    # apply velocity threshold (sample-wise)
    logger.info(f"Applying velocity threshold.")
    pred_samples = (velocity <= params.vel_thr).astype("int")
    mapping = {0: "gap", 1: "fixation"}
    pred_labels = list(map(lambda x: mapping[x], pred_samples))

    # convert to event-based representation
    pred_events = event_handling.parse_labels_to_event_sequence(time_axis, pred_labels)
    logger.info(f"Number of events after velocity threshold: %i", len(pred_events))

    # filter out microsaccades
    if params.microsaccade_filter:
        logger.info(f"Applying microsaccade-filter.")
        pred_events = event_handling.update_events_with_stats(
            pred_events, time_axis, gaze_xy_normalized, gaze_xy_distorted, velocity
        )
        pred_events = event_handling.filter_microsaccades(
            pred_events, ang_thr=params.ang_thr, time_thr=params.time_thr
        )
        logger.info(f"Number of events after microsaccade-filter: %i", len(pred_events))

    # filter out too short fixations
    if params.short_fixations_filter:
        logger.info(f"Applying short-fixations-filter.")
        pred_events = event_handling.update_events_with_stats(
            pred_events, time_axis, gaze_xy_normalized, gaze_xy_distorted, velocity
        )
        pred_events = event_handling.filter_short_fixations(
            pred_events, time_thr=params.min_len
        )
        logger.info(
            f"Number of events after short-fixations-filter: %i", len(pred_events)
        )

    # get final statistics for each event
    logger.info(f"Updating event statistics.")
    pred_events = event_handling.update_events_with_stats(
        pred_events, time_axis, gaze_xy_normalized, gaze_xy_distorted, velocity
    )

    # transform events to samples
    mapping = {"fixation": 1, "gap": 0}
    pred_samples = event_handling.transform_event_sequence_to_samples(
        pred_events, time_axis, mapping=mapping
    )

    return pred_samples, pred_events


def detect_fixations_invisible(
    rec_folder,
    output_timestamps=True,
    use_cached_optic_flow=False,
    params: Params = DEFAULT_PARAMS,
    gaze_data=None,
    progress: T.Optional[Progress] = None,
):
    """Main function for fixation prediction. Takes a recording folder and
    returns predictions for the given recording.

    Args:
        rec_folder: recording folder
        output_timestamps: whether to transform time axis back to original
            nanosecond timestamps
        **params: algorithm paramaters

    Returns:
        pred_samples: pandas-Series containing predicted class for each sample
        pred_events: list of dictionaries with key properties for each event
    """
    # load data
    if gaze_data is None:
        start = time.time()
        (
            time_axis,
            timestamps,
            gaze_distorted,
            _,
            gaze_normalized,
        ) = helpers.get_gaze_from_recording(rec_folder)
        duration_s = time.time() - start
        logger.info(
            f"Loaded gaze data (%i samples) from {rec_folder} in %s seconds.",
            len(timestamps),
            duration_s,
        )
    else:
        time_axis, timestamps, gaze_distorted, gaze_normalized = gaze_data

    # resample gaze data to 200 Hz (equally spaced samples)
    fs = 200.0

    gaze_distorted_x, resampled_time_axis = helpers.resample_linearly(
        gaze_distorted[:, 0], time_axis, fs=fs
    )
    gaze_distorted_y, _ = helpers.resample_linearly(
        gaze_distorted[:, 1], time_axis, fs=fs
    )

    gaze_normalized_x, _ = helpers.resample_linearly(
        gaze_normalized[:, 0], time_axis, fs=fs
    )
    gaze_normalized_y, _ = helpers.resample_linearly(
        gaze_normalized[:, 1], time_axis, fs=fs
    )
    logger.info(f"Resampled gaze data to 200 Hz (%i samples).", len(gaze_distorted_x))

    # smooth gaze coordinates
    window_len = 11
    poly_order = 3
    smoothed_gaze_normalized_x = savgol_filter(
        gaze_normalized_x, window_len, poly_order
    )
    smoothed_gaze_normalized_y = savgol_filter(
        gaze_normalized_y, window_len, poly_order
    )
    smoothed_gaze_normalized = np.vstack(
        (smoothed_gaze_normalized_x, smoothed_gaze_normalized_y)
    ).T

    smoothed_gaze_distorted_x = savgol_filter(gaze_distorted_x, window_len, poly_order)
    smoothed_gaze_distorted_y = savgol_filter(gaze_distorted_y, window_len, poly_order)
    smoothed_gaze_distorted = np.vstack(
        (smoothed_gaze_distorted_x, smoothed_gaze_distorted_y)
    ).T
    logger.info(f"Applied smoothing filter to gaze data.")

    velocity = None
    optic_flow_vectors_available = False
    optic_flow_vectors = optic_flow_correction.load_optic_flow_vectors(
        rec_folder, use_existing=use_cached_optic_flow, progress=progress
    )

    # upsample optic flow to the same time axis as the gaze data
    resampled_optic_x = np.interp(
        resampled_time_axis, optic_flow_vectors.ts, optic_flow_vectors.x
    ).astype(np.float32)
    resampled_optic_y = np.interp(
        resampled_time_axis, optic_flow_vectors.ts, optic_flow_vectors.y
    ).astype(np.float32)
    optic_flow_vectors = optic_flow_correction.OpticFlow(
        ts=resampled_time_axis, x=resampled_optic_x, y=resampled_optic_y
    )

    corrected_pixel_velocity = None
    if not len(optic_flow_vectors.ts):
        logger.warning("No optic flow vectors were available")
    else:
        optic_flow_vectors_available = True
        corrected_pixel_velocity = helpers.get_pixel_velocity(
            resampled_time_axis, smoothed_gaze_distorted
        )

    if not optic_flow_vectors_available:
        logger.info(f"Calculated un-corrected gaze velocity in pixels/sec.")

        corrected_pixel_velocity = optic_flow_correction.get_corrected_pixel_velocity(
            optic_flow_vectors,
            resampled_time_axis,
            smoothed_gaze_distorted,
        )

    if corrected_pixel_velocity is None:
        raise Exception("could not get optic flow velocity")

    # apply I-VT algorithm
    pred_samples, pred_events = i_vt(
        resampled_time_axis,
        smoothed_gaze_normalized,
        smoothed_gaze_distorted,
        corrected_pixel_velocity,
        params,
    )
    logger.info(f"Done predicting fixations.")

    label_counts = {}
    for event in pred_events:
        label = event["label"]
        label_counts[label] = label_counts.get(label, 0) + 1
        event["instance"] = label_counts[label]

    # match start and end times of events to the original nanosecond timestamps
    if output_timestamps:
        pred_events = helpers.transform_to_original_timestamps(
            pred_events, time_axis, timestamps
        )
        mapping = {"fixation": 1, "gap": 0}
        pred_samples = event_handling.transform_event_sequence_to_samples(
            pred_events, timestamps, mapping=mapping
        )
        logger.info(f"Transforming to original timestamps.")

    # finally, convert event sequence to list of dictionaries
    pred_events = pred_events.to_list()

    return pred_samples, pred_events


if __name__ == "__main__":
    detect_fixations_invisible("/recs/longrec", use_cached_optic_flow=True)
