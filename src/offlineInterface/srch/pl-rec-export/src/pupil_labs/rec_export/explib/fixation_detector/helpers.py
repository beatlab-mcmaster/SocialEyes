""" General helper functions.
"""

import math
import typing as T

import cv2
import numpy as np
from rich.progress import Progress
from scipy import optimize

from ....pikit import Recording
from ....pikit.lib import projection


def find_nearest(array, value):
    """
    Finds nearest index to a value in a sorted array.
    """
    idx = np.searchsorted(array, value, side="right")
    if idx > 0 and (
        idx == len(array)
        or math.fabs(value - array[idx - 1]) < math.fabs(value - array[idx])
    ):
        ind = idx - 1
        value = array[ind]
        if ind == -1:
            value = None
        return ind, value
    else:
        return idx, array[idx]


def find_previous(array, value):
    """
    Finds previous index to a value in a sorted array.
    """
    idx = np.searchsorted(array, value, side="right")
    ind = idx - 1
    value = array[ind]
    if ind == -1:
        value = None
    return ind, value


def find_next(array, value):
    """
    Finds next index to a value in a sorted array.
    """
    idx = np.searchsorted(array, value, side="right")
    return idx, array[idx]


def resample_linearly(data, time, min_time=None, max_time=None, fs=200.0):
    """
    Resample data linearly to a different sample rate.

    Args:
        data: data
        time: timestamps (in seconds)
        min_time: minimum of new time axis
        max_time: maximum of new time axis
        fs: desired sample rate

    Returns:
        interp_p: new data points
        x: new time axis
    """
    if min_time is None:
        min_time = time.min()
    if max_time is None:
        max_time = time.max()

    xp = time
    fp = data
    x = np.arange(min_time, max_time + 1e-9, 1 / fs)  # new time axis
    interp_p = np.interp(x, xp, fp)

    return interp_p, x


def get_gaze_from_recording(rec_folder, progress: T.Optional[Progress] = None):
    """
    Retrieves gaze coordinates from a pikit recording.

    Args:
        rec_folder: recording folder

    Returns:
        time_axis: time axis in seconds
        timestamps: nanosecond timestamps for each sample
        gaze_distorted: gaze coordinates (pixel space)
        gaze_rectified: gaze coordinates (rectified)
        gaze_normalized: gaze coordinates (normalized)
    """
    rec = Recording(rec_folder)
    timestamp_at_0 = rec.timestamp_at_offset(seconds=0)
    rec.seek(timestamp_at_0)

    gaze_stream = rec.gaze
    if rec.gaze200.parts:
        gaze_stream = rec.gaze200

    stream = gaze_stream.read(
        rec.timestamp_at_offset(seconds=0),
        rec.timestamp_at_offset(seconds=rec.duration_s),
    )
    timestamps = []
    gaze_distorted = []
    gaze_rectified = []
    gaze_normalized = []
    task = None
    if progress:
        task = progress.add_task("Loading gaze samples...", total=None)
    for sample in stream:
        epoch_ns = sample.timestamp.epoch_ns
        gaze_distorted_xy = [sample.position.distorted.x, sample.position.distorted.y]
        gaze_rectified_xy = [sample.position.rectified.x, sample.position.rectified.y]
        gaze_normalized_xy = [
            sample.position.normalized.x,
            sample.position.normalized.y,
        ]

        timestamps.append(epoch_ns)
        gaze_distorted.append(gaze_distorted_xy)
        gaze_rectified.append(gaze_rectified_xy)
        gaze_normalized.append(gaze_normalized_xy)
    if task:
        progress.update(task, total=len(timestamps), completed=len(timestamps))

    timestamps = np.array(timestamps, dtype=np.int64)
    time_axis = (timestamps - timestamp_at_0) / 1e9  # recording start is t=0
    gaze_distorted = np.array(gaze_distorted, dtype=np.float32)
    gaze_rectified = np.array(gaze_rectified, dtype=np.float32)
    gaze_normalized = np.array(gaze_normalized, dtype=np.float32)

    return time_axis, timestamps, gaze_distorted, gaze_rectified, gaze_normalized


def get_consecutive_delta_angles_from_xy(coords_xy, out_format="degrees"):
    """
    Calculates difference angles between consecutive points in visual space.
    Assumes that input points are given in normalized coordinates.

    Args:
        coords_xy: (N,2) array with normalized gaze coordinates

    Returns:
        Array with N-1 angles
    """
    assert coords_xy.ndim == 2

    # format as 3D homogeneous coordinates
    if coords_xy.shape[1] == 2:
        coords_xy = np.hstack([coords_xy, np.ones((len(coords_xy), 1))])

    # get dot product between consecutive vectors
    dot_product = np.sum(coords_xy[1:, :] * coords_xy[:-1, :], axis=1)

    # get absolute values of vectors
    abs_values = np.sqrt(np.sum(coords_xy**2, axis=1))

    # get cosine of the internal angle
    cos_angle = dot_product / (abs_values[1:] * abs_values[:-1])
    cos_angle = np.minimum(cos_angle, 1)

    if out_format == "radians":
        return np.arccos(cos_angle)
    elif out_format == "degrees":
        return np.degrees(np.arccos(cos_angle))


def get_angular_velocity(time_axis, norm_coords):
    """
    Calculates angular velocities from an array of normalized coordinates.
    Assumes that @time_axis is given in seconds.

    Args:
        time_axis: time axis in seconds
        norm_coords: (N,2) array with normalized gaze coordinates

    Returns:
        velocity: forwards velocities for each time step
    """
    diff_angle = get_consecutive_delta_angles_from_xy(norm_coords)
    diff_time = time_axis[1:] - time_axis[:-1]
    velocity = diff_angle / diff_time
    velocity = np.insert(velocity, 0, 0)
    return velocity


def get_pixel_velocity(time_axis, px_coords):
    """
    Calculates pixel velocities from an array of coordinates.
    Assumes that @time_axis is given in seconds.

    Args:
        time_axis: time axis in seconds
        px_coords: (N,2) array with distorted (pixel) gaze coordinates

    Returns:
        velocity: forwards velocities for each time step
    """
    assert px_coords.ndim == 2
    diff = px_coords[1:] - px_coords[:-1]
    diff = np.sqrt((diff**2).sum(axis=1))
    diff_time = time_axis[1:] - time_axis[:-1]
    velocity = diff / diff_time
    velocity = np.insert(velocity, 0, 0)
    return velocity


def get_delta_angles_between_two_arrays(coords_a, coords_b, out_format="degrees"):
    """
    Calculates difference angles between two array of points in visual space when
    points are given in homogeneous coordinates.
    """
    assert coords_a.ndim == 2
    assert coords_b.ndim == 2

    # format properly as homogeneous coordinates
    if coords_a.shape[1] == 2:
        coords_a = np.hstack([coords_a, np.ones((len(coords_a), 1))])
    if coords_b.shape[1] == 2:
        coords_b = np.hstack([coords_b, np.ones((len(coords_b), 1))])

    # get dot product between vectors
    dot_product = np.sum(coords_a * coords_b, axis=1)

    # get absolute values of vectors
    abs_values_a = np.sqrt(np.sum(coords_a**2, axis=1))
    abs_values_b = np.sqrt(np.sum(coords_b**2, axis=1))

    # get cosine of the internal angle
    cos_angle = dot_product / (abs_values_a * abs_values_b)
    cos_angle = np.minimum(cos_angle, 1)

    if out_format == "radians":
        return np.arccos(cos_angle)
    elif out_format == "degrees":
        return np.degrees(np.arccos(cos_angle))


def undistort_points(points_distorted, camera_matrix, distortion_coefficients):
    """
    Transform points from pixel coordinates to normalized coordinates.

    Args:
        points_distorted: (N,2) array of pixel coordinates
        camera_matrix: Intrinsic matrix of the camera
        distortion_coefficients: Distortion coefficients of the camera

    Returns:
        undistorted points: (N,2) array of normalized coordinates
    """

    assert points_distorted.ndim == 2
    assert points_distorted.shape[1] == 2

    points = np.asarray(points_distorted, dtype=np.float32)
    points_3d = np.squeeze(cv2.convertPointsToHomogeneous(points))

    # un-project points with intrinsic matrix
    inv_camera_matrix = np.linalg.inv(camera_matrix)
    points_3d_ = np.matmul(inv_camera_matrix, points_3d.T).T

    # un-distort points by finding the roots of the distortion model
    undistorted_points = []
    for _, point_ in enumerate(points_3d_):
        solution = optimize.root(
            lambda p: point_[0:2]
            - projection.apply_distortion_model(p, distortion_coefficients),
            point_[0:2],
            method="lm",
        )

        if not solution.success:
            print("Problem finding the root for the distortion model.")

        undistorted_points.append(solution.x)

    undistorted_points = np.vstack(undistorted_points)

    return undistorted_points


def roll_array(array, roll):
    """
    Same as np.roll, but instead re-introducing elements which are pushed beyond
    the last position, it fills in NaN's.
    """
    array = np.roll(array, roll)
    if roll >= 0:
        array[:roll] = np.nan
    else:
        array[len(array) - (-roll) :] = np.nan
    return array


def my_rolling_window(a, window):
    """Implements an effective rolling window.

    This implements the stride trick so that we can vectorize operations over
    a sliding window of an N-D array.

    This function assumes that the first (or 0-th) dimension of the input array is the
    time axis.

    Parameters:
        a       --  N-D numpy array
        window  --  window size
    Returns:
        (N+1)-D Numpy array, where the last dimension are the values for the sliding window
    """
    # first dimension will stay the main time axis
    # last dimension will be the second time axis (for the sliding window)
    shape = (a.shape[0] - window + 1,) + a.shape[1:] + (window,)
    strides = a.strides + (a.strides[0],)
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


Position = T.Literal["central", "left", "right"]
Mode = T.Literal["edge", "constant"]


def pad_for_window(
    a,
    window_size,
    position: Position = "central",
    mode: Mode = "edge",
    pad_value=np.nan,
):
    """Pads an array so that applying a sliding window will yields the same sized array.
    Padding values are the start or end values of the array, respectively, when mode is
    set to 'edge', or a custom value in mode 'constant'.
    Parameter position can be either 'central', 'left', 'right' to specify the relative
    position of the window with respect each sample.

    This function assumes that the time axis is the first (or 0-th) dimension of the input array.

    Args:
        a: input array
        position: window position with respect to the sample
        mode: pad mode
        pad_value: constant pad value (only for mode 'constant')

    Returns:
        padded array
    """
    if position == "central":
        pad_start = (window_size // 2,) + (0,) * len(a.shape[1:])
        pad_end = (window_size // 2,) + (0,) * len(a.shape[1:])
        pad_width = np.stack((pad_start, pad_end), axis=1)
        if mode == "constant":
            values_start = (pad_value,) + (0,) * len(a.shape[1:])
            values_end = (pad_value,) + (0,) * len(a.shape[1:])
            pad_values = np.stack((values_start, values_end), axis=1)
            return np.pad(a, mode=mode, pad_width=pad_width, constant_values=pad_values)
        elif mode == "edge":
            return np.pad(a, mode=mode, pad_width=pad_width)

    elif position == "left":
        pad_start = (window_size - 1,) + (0,) * len(a.shape[1:])
        pad_end = (0,) + (0,) * len(a.shape[1:])
        pad_width = np.stack((pad_start, pad_end), axis=1)
        if mode == "constant":
            values_start = (pad_value,) + (0,) * len(a.shape[1:])
            values_end = (pad_value,) + (0,) * len(a.shape[1:])
            pad_values = np.stack((values_start, values_end), axis=1)
            return np.pad(a, mode=mode, pad_width=pad_width, constant_values=pad_values)
        elif mode == "edge":
            return np.pad(a, mode=mode, pad_width=pad_width)

    elif position == "right":
        pad_start = (0,) + (0,) * len(a.shape[1:])
        pad_end = (window_size - 1,) + (0,) * len(a.shape[1:])
        pad_width = np.stack((pad_start, pad_end), axis=1)
        if mode == "constant":
            values_start = (pad_value,) + (0,) * len(a.shape[1:])
            values_end = (pad_value,) + (0,) * len(a.shape[1:])
            pad_values = np.stack((values_start, values_end), axis=1)
            return np.pad(a, mode=mode, pad_width=pad_width, constant_values=pad_values)

        elif mode == "edge":
            return np.pad(a, mode=mode, pad_width=pad_width)


def as_windowed(*features, window_size=21, padding=True, **padding_kwargs):
    """Returns all given features as strided arrays, applying a sliding window over
    the firstc dimension.

    Args:
        *features: Input features (N, ...) arrays of arbitrary dimensions. First axis is
            assumed to be the time axis.
        window_size: Length of the sliding window in samples
        padding (bool): Whether to features before windowing or not
        **padding_kwargs: Keyword arguments for the padding function.

    Returns:
        *windowed_features: Output features (N, ..., N_window) as strided,
            windowed features arrays.
    """
    window_size = int(window_size)
    for feat in features:
        if padding:
            feat_ = pad_for_window(feat, window_size)
        else:
            feat_ = feat
        windowed_feat = my_rolling_window(feat_, window_size)
        yield windowed_feat


def transform_to_original_timestamps(event_sequence, time_axis, timestamps):
    """Converts start and end times of events back to nanosecond timestamps (instead
    of time axis in seconds).
    Strategy is to search for the closest sample in the original array (before
    resampling) and take the time of this sample.

    Args:
        pred_events: DenseEventSequence object
        time_axis: original time axis in second (before resampling)
        timestamps: original timestamps in nanoseconds

    Returns:
        Modified event sequence with start and end time in nanosecond timestamps
    """
    for ev in event_sequence:
        ind, _ = find_nearest(time_axis, ev["end_t"])
        ev.set_end_time(timestamps[ind])
        ind, _ = find_nearest(time_axis, ev["start_t"])
        ev.set_start_time(timestamps[ind])
    return event_sequence
