import logging
import typing as T
from itertools import groupby, tee
from pathlib import Path

import cv2
import numpy as np
from more_itertools import convolve, windowed
from xgboost import XGBClassifier

from .helper import BlinkEvent, OfParams, PPParams, create_grid, pad_beginning, pairwise


def blink_detection_pipeline(
    eye_left_images, eye_right_images, timestamps: T.List, clf_path: Path
) -> T.List:
    """Pipeline for blink detection.

    Args:
    -------
    eye_left_images : list
        List of left eye images.
    eye_right_images : list
        List of right eye images.
    timestamps : list
        List of timestamps.
    clf_path : str
        Path to the classifier object.

    Returns:
    -------
    list
        List of blink events.
    """

    # get default optical flow parameters
    of_params = OfParams()

    # get default post processing parameters
    pp_params = PPParams()

    grid = create_grid(of_params.img_shape, of_params.grid_size)

    # load classifier
    clf = XGBClassifier()
    clf.load_model(clf_path)

    images_timestamps = zip(zip(eye_left_images, eye_right_images), timestamps)

    x = calculate_optical_flow(images_timestamps, of_params, grid)
    x = predict_class_probas(x, clf, of_params)
    x = smooth_probas(x, pp_params)
    x = threshold_probas(x, pp_params)
    x = compile_into_events(x)
    x = filter_events(x)
    blink_events = extract_blink_events(x, pp_params)
    return list(blink_events)


def cv2_calcOpticalFlowPyrLK(
    img_prev: np.ndarray,
    img_curr: np.ndarray,
    pts_prev: np.ndarray,
    window_size: int,
    stop_steps: int,
) -> np.ndarray:
    """Calculates optical flow using the Lucas-Kanade method.

    Args:
    -------
    img_prev : np.ndarray
        Previous frame.
    img_curr : np.ndarray
        Current frame.
    pts_prev : np.ndarray
        Grid points.
    window_size : int
        Size of the search window at each pyramid level.
    stop_steps : int
        Criteria to stop the search.

    Returns:
    -------
    np.ndarray
        Optical flow vectors.
    """

    lk_params = dict(
        winSize=(window_size, window_size),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, stop_steps, 0.03),
    )
    img_prev = img_prev.astype(np.uint8)
    img_curr = img_curr.astype(np.uint8)
    pts_next, _, _ = cv2.calcOpticalFlowPyrLK(
        img_prev, img_curr, pts_prev, None, **lk_params
    )
    return pts_next - pts_prev


def calculate_optical_flow(
    eye_pair_frames: T.Generator,
    of_params: OfParams = OfParams(),
    grid: np.ndarray = None,
) -> T.Generator:
    """Calculates optical flow for pairs of video frames using optical flow parameters defined in of_params.

    Args:
    -------
    eye_pair_frames : generator
        Yields a tuple of left and right frames, as well as the corresponding timestamps.
    of_params : OfParams
        Optical flow parameters.
    grid : np.ndarray
        Grid coordinates for which to calculate optical flow.

    Yields:
    -------
    Yields a tuple of optical flow vectors and corresponding timestamps.
    """

    eye_pair_frames = pad_beginning(eye_pair_frames, of_params.step_size)

    for consecutive_frames in windowed(eye_pair_frames, n=of_params.step_size + 1):
        previous, current = consecutive_frames[0][0], consecutive_frames[-1][0]
        timestamp = consecutive_frames[-1][1]

        left_prev_image, right_prev_image = previous
        left_curr_image, right_curr_image = current

        args = grid, of_params.window_size, of_params.stop_steps

        optic_flow_left = cv2_calcOpticalFlowPyrLK(
            left_prev_image, left_curr_image, *args
        )
        optic_flow_right = cv2_calcOpticalFlowPyrLK(
            right_prev_image, right_curr_image, *args
        )

        # only return the y-component of the optical flow
        yield np.concatenate((optic_flow_left[:, 1], optic_flow_right[:, 1])), timestamp


def predict_class_probas(
    optical_flow: T.Generator, clf: XGBClassifier, of_params: OfParams = OfParams()
) -> T.Generator:
    """Predicts class probabilities from optical flow vectors concatenated across several points in time ("layers").

    Args
    -------
    optical_flow : generator
        Generator that yields a tuple of optical flow vectors and timestamps.
    clf : Classifier
        Trained classifier for classifying optical flow vectors.
    of_params : OfParams
        Optical flow parameters.

    Yields
    -------
    Yields a tuple of class probabilities and timestamps.
    """

    window_length = (of_params.n_layers - 1) * of_params.layer_interval + 1
    window_center = (window_length - 1) // 2

    optical_flow = pad_beginning(optical_flow, window_center)

    indices = np.arange(0, window_length, of_params.layer_interval)

    for window in windowed(optical_flow, n=window_length):
        flows = [window[i][0] for i in indices if window[i] is not None]
        if len(flows) != len(indices):
            logging.warning(f"missing flows {len(flows)} != {len(indices)}")
            continue
        features = np.hstack(flows)[None, :]
        timestamp = window[window_center][1]
        probas = clf.predict_proba(features)[0]

        yield probas, timestamp


def threshold_probas(
    probas_timestamps: T.Generator, pp_params: PPParams = PPParams()
) -> T.Generator:
    """Apply thresholding to class probabilities.

    Args:
    -------
    probas_timestamps : generator
        Generator that yields a tuple of class probabilities and a corresponding timestamp.

    Yields:
    -------
    Yields a tuple of event type string and the corresponding timestamp.
    """

    return map(lambda p_ts: thresholding(p_ts, pp_params), probas_timestamps)


def thresholding(
    p_ts: T.Tuple[np.ndarray, int], pp_params: PPParams = PPParams()
) -> T.Tuple[str, int]:
    """Thresholds class probabilities.

    Args:
    -------
    p_ts : tuple
        Tuple of class probabilities and timestamp.
    pp_params : PPParams
        Post-processing parameters.

    Returns:
    -------
    Returns a tuple of event type string and the corresponding timestamp.
    """

    p, ts = p_ts
    if p[1] > pp_params.proba_onset_threshold:
        return "onset", ts
    if p[2] > pp_params.proba_offset_threshold:
        return "offset", ts
    else:
        return "background", ts


def smooth_probas(
    probas_timestamps: T.Generator, pp_params: PPParams = PPParams()
) -> T.Generator:
    """Smooths class probabilities using a moving average filter.

    Args:
    -------
    probas_timestamps : generator
        Generator that yields a tuple of class probabilities and timestamps.
    pp_params : PPParams
        Post-processing parameters.

    Yields:
    -------
    Yields a tuple of smoothed class probabilities and timestamps.
    """

    kernel_size = pp_params.smooth_window

    probas_timestamps1, probas_timestamps2 = tee(probas_timestamps, 2)
    probas = (p for p, ts in probas_timestamps1)
    smoothed_probas = convolve(probas, np.ones(kernel_size) / kernel_size)
    timestamps = (ts for p, ts in probas_timestamps2)
    return zip(smoothed_probas, timestamps)


def compile_into_events(samples: T.Generator) -> T.Generator:
    """Compiles samples into events.

    Args:
    -------
    samples : generator
        Generator that yields a tuple of event type and timestamp.

    Yields:
    -------
    Yields an event, defined by its type, start and end time.
    """

    for event_type, samples in groupby(samples, key=lambda sample: sample[0]):
        first_sample = next(samples)
        start = first_sample[1]
        end = first_sample[1]
        for sample in samples:
            end = sample[1]
        yield BlinkEvent(start, end, event_type)


def filter_events(events: T.Generator) -> T.Generator:
    """Filters events by their type.

    Args:
    -------
    events : generator
        Generator that yields single events (onset, offset or background).

    Yields:
    -------
    Filter object that yields only onset and offset events.
    """

    return filter(lambda event: (event.label in ["onset", "offset"]), events)


def extract_blink_events(
    onsets_offset_events: T.Generator, pp_params: PPParams = PPParams()
) -> T.Generator:
    """Extracts blinks from onset and offset events.

    Args:
    -------
    onsets_offset_events : generator
        Generator that yields onset and offset events.
    pp_params : PPParams
        Post-processing parameters.

    Yields:
    -------
    Yields a blink event, defined by its start and end time and type (always "Blink")
    """

    for event1, event2 in pairwise(onsets_offset_events):
        if (
            (event1.label == "onset")
            and (event2.label == "offset")
            and (
                (event2.start_time / 1e9 - event1.end_time / 1e9)
                < pp_params.max_gap_duration_s
            )
            and (
                (event2.end_time / 1e9 - event1.start_time / 1e9)
                > pp_params.short_event_min_len_s
            )
        ):
            yield BlinkEvent(event1.start_time, event2.end_time, "blink")
