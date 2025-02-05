import logging
import typing as T
from itertools import chain
from pathlib import Path

import cv2
import more_itertools
import numpy as np
import numpy.typing as npt
from rich.progress import Progress, track

from ....pikit import Recording
from ....pikit.lib.sensors import WorldSensor
from ..video import av_h264_frame_to_gray


def iter_with_next(iterable):
    yield from more_itertools.pairwise(chain(iterable, [None]))


from . import helpers

OPTIC_FLOW_FILE_NAME = "optic_flow_vectors.npz"

log = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


class OpticFlow(T.NamedTuple):
    ts: npt.NDArray[np.int64]
    x: npt.NDArray[np.float32]
    y: npt.NDArray[np.float32]


def calculate_optic_flow_vectors(
    rec_folder, progress: T.Optional[Progress] = None
) -> OpticFlow:
    """Gets the optic flow vectors for this recording."""
    log.info("Calculating optic flow vectors.")
    (
        time_axis,
        timestamps,
        optic_flow_x,
        optic_flow_y,
    ) = get_global_grid_based_optic_flow_LK(rec_folder, progress)

    return OpticFlow(ts=time_axis, x=optic_flow_x, y=optic_flow_y)


def save_optic_flow_vectors(rec_folder, optic_flow_vectors: OpticFlow):
    """
    Saves the optic flow vectors to a binary file in the recording folder
    """
    save_file = Path(rec_folder) / OPTIC_FLOW_FILE_NAME
    log.info(f"Saving optic flow vectors to {save_file}")
    file_handle = open(save_file, "wb")
    np.savez(
        file_handle,
        timestamps=optic_flow_vectors.ts,
        optic_flow_x=optic_flow_vectors.x,
        optic_flow_y=optic_flow_vectors.y,
    )


def load_optic_flow_vectors(
    rec_folder: Path,
    use_existing=True,
    save=True,
    progress: T.Optional[Progress] = None,
) -> OpticFlow:
    """
    Loads the optic flow vectors for a recording

    Args:
        rec_folder: recording folder
        use_existing: use existing vectors if they exist, otherwise recalculates
        save: save calculated vectors to file for reuse next time
    """
    load_file = Path(rec_folder) / OPTIC_FLOW_FILE_NAME
    data = None
    if use_existing and load_file.exists():
        try:
            data = np.load(load_file)
        except Exception as e:
            log.error(f"Could not load existing vectors: {e}")

    if data is not None:
        log.info(f"Using existing optic flow vectors: {load_file}")
        optic_flow_vectors = OpticFlow(
            ts=data["timestamps"],
            x=data["optic_flow_x"],
            y=data["optic_flow_y"],
        )
    else:
        log.info(f"Calculating optic flow vectors for {rec_folder}")
        optic_flow_vectors = calculate_optic_flow_vectors(rec_folder, progress)
        if save:
            try:
                save_optic_flow_vectors(rec_folder, optic_flow_vectors)
            except Exception as e:
                log.exception(f"Could not save vectors to {rec_folder}: {e}")

    return optic_flow_vectors


def get_global_grid_based_optic_flow_LK(
    rec_folder, progress: T.Optional[Progress] = None, **lk_params
):
    """Calculates the optic flow velocity (in [px/s]) for each frame in a recording.
    For each pair of frames (previous and current) the function
    'calc_grid_optic_flow_LK' is called to calculate local optic flow vectors
    on an equally spaced grid.

    The global optic flow vector is then calculated as the average over all
    local optic flow vectors.
    This function is based on the 30 Hz world video data.

    Args:
        rec_folder: PI recording folder
        **lk_params: keyword arguments for the function calc_grid_optic_flow_LK

    Returns:
        list_delta_vec: array of optic flow vectors for each video frame
        list_q_points: number of points which could be tracked for each frame
    """
    # get recording
    rec = Recording(rec_folder)
    timestamp_at_0 = rec.timestamp_at_offset(seconds=0)

    # get world stream
    stream = WorldSensor(rec, fill_gaps=False, times_from_time_files=True).read()

    previous_scene = None
    previous_timestamp = None
    list_delta_vec = []
    timestamps = []
    delta_time = []

    tot_frames = sum([p.video and p.video.n_frames_video or 0 for p in rec.world.parts])
    track_fn = progress.track if progress else track
    for previous_sample, sample in track_fn(
        iter_with_next(stream),
        description="Detecting optic flow for fixations...",
        total=tot_frames,
    ):
        if sample is None:
            break

        if previous_scene is None:
            previous_scene = av_h264_frame_to_gray(previous_sample.av_frame)
            previous_timestamp = previous_sample.timestamp.epoch_ns
            continue

        current_scene = av_h264_frame_to_gray(sample.av_frame)
        current_timestamp = sample.timestamp.epoch_ns

        # get optic flow vectors on a grid
        delta_vec, _, _ = calc_grid_optic_flow_LK(
            previous_scene, current_scene, **lk_params
        )

        # average optic flow vectors over the whole image
        delta_vec = np.nanmean(delta_vec, axis=(0, 1))

        # keep results
        list_delta_vec.append(delta_vec)
        timestamps.append(current_timestamp)
        delta_time.append((current_timestamp - previous_timestamp) / 1e9)

        # reset previous frame
        previous_scene = current_scene
        previous_timestamp = current_timestamp

    # reshape data so that first axis is time axis
    if not len(list_delta_vec):
        return [], [], [], []

    optic_flow_LK = np.stack(list_delta_vec, 0)
    optic_flow_LK_x = optic_flow_LK[:, 0]
    optic_flow_LK_y = optic_flow_LK[:, 1]
    timestamps = np.array(timestamps).reshape(-1)
    delta_time = np.array(delta_time).reshape(-1)

    # convert to pixels/sec
    optic_flow_LK_x = optic_flow_LK_x / delta_time
    optic_flow_LK_y = optic_flow_LK_y / delta_time

    # get time axis
    timestamps = np.array(timestamps, dtype=np.uint64)
    time_axis = (timestamps - timestamp_at_0) / 1e9  # recording start is t=0

    return time_axis, timestamps, optic_flow_LK_x, optic_flow_LK_y


def get_corrected_pixel_velocity(
    optic_flow_vectors: OpticFlow,
    gaze_time_axis,
    smoothed_gaze_distorted,
    fs_gaze=200.0,
):
    """
    Get pixel velocity of the gaze point, corrected for optic flow
    by vector subtraction.

    Args:
        optic_flow_vectors: optic flow vectors for recording
        smoothed_gaze_distorted: (N,2) array with preprocessed gaze coordinates
                                 (distorted coordinates)

    Returns:
        corrected_velocity: corrected pixel velocity (absolute value)
    """
    estimated_next_points = _get_estimated_next_points(
        optic_flow_vectors, smoothed_gaze_distorted
    )
    diff = np.sqrt(
        np.sum((estimated_next_points - smoothed_gaze_distorted) ** 2, axis=1)
    )
    corrected_velocity = diff * fs_gaze  # convert to pixels/sec
    return corrected_velocity


def _get_estimated_next_points(optic_flow_vectors: OpticFlow, smoothed_gaze_distorted):
    # For each frame, take the gaze coordinates of the next point and
    # subtract the optic flow vector between the frames.
    # This yields an estimate where the next point would be, if there was no
    # optic flow. Then, use the difference between this estimated next point and
    # the current point, to compute the pixel velocity.
    optic_flow_x = optic_flow_vectors.x
    optic_flow_y = optic_flow_vectors.y
    estimated_next_points_x = (
        helpers.roll_array(smoothed_gaze_distorted[:, 0], -1) - optic_flow_x
    )
    estimated_next_points_y = (
        helpers.roll_array(smoothed_gaze_distorted[:, 1], -1) - optic_flow_y
    )
    estimated_next_points = np.hstack(
        (estimated_next_points_x[:, np.newaxis], estimated_next_points_y[:, np.newaxis])
    )
    return estimated_next_points


def get_corrected_angular_velocity(
    optic_flow_vectors: OpticFlow,
    gaze_time_axis,
    smoothed_gaze_distorted,
    smoothed_gaze_normalized,
    camera_matrix,
    distortion_coefficients,
    fs_gaze=200,
):
    """
    Get angular velocity of the gaze point, corrected for optic flow by
    vector subtratction.

    Args:
        optic_flow_vectors: optic flow vectors of recording
        gaze_time_axis: equally spaced time ais
        smoothed_gaze_distorted: (N,2) array with preprocessed
                                 distorted gaze coordinates
        smoothed_gaze_normalized: (N,2) array with preprocessed
                                 normalized gaze coordinates
        fs_gaze: sample rate of the gaze signal

    Returns:
        corrected_velocity: corrected angular velocity (absolute value)
    """
    estimated_next_points = _get_estimated_next_points(
        optic_flow_vectors, gaze_time_axis, fs_gaze, smoothed_gaze_distorted
    )

    # convert estimated next points to homogeneous coordinates
    logging.info("Undistorting corrected points for calculation of angular velocity.")
    next_points_normalized = helpers.undistort_points(
        estimated_next_points,
        camera_matrix,
        distortion_coefficients,
    )

    # get corrected angular velocity for each sample
    delta_angles = helpers.get_delta_angles_between_two_arrays(
        smoothed_gaze_normalized, next_points_normalized
    )
    corrected_velocity = delta_angles * fs_gaze  # convert to degree/sec
    return corrected_velocity


def calc_grid_optic_flow_LK(
    previous_frame,
    current_frame,
    grid_spacing=100,
    lk_winSize=(50, 50),
    lk_maxLevel=4,
    lk_criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 0.01),
):
    """Calculates the optic flow vector between two frames by applying the Lucas-Kanade
    algorithm on a grid of points.

    Args:
        previous_frame: first frame (gray)
        current_frame: second frame (gray)

        grid_spacing: spacing of the grid to be used
        lk_winSize: window size for the Lucas-Kanade algorithm (should be large enough)
        lk_maxLevel: maximum level of pyramids for the Lucas-Kanade algorithm
        lk_criteria: openCV-recursive algorithm criteria

    Returns:
        delta_vec: optic flow vectors, arranged on a grid
        coords: coordinates of the grid points
        n_quality_points: number of points for successful optic flow estimations
    """
    # define parameters for Lucas-Kanade algorithm
    lk_params = dict(winSize=lk_winSize, maxLevel=lk_maxLevel, criteria=lk_criteria)

    # define a grid of points to track
    X, Y = np.meshgrid(
        np.arange(grid_spacing // 2, previous_frame.shape[0], grid_spacing),
        np.arange(grid_spacing // 2, previous_frame.shape[1], grid_spacing),
    )
    p_0 = (
        np.vstack((X.flatten(), Y.flatten())).T.reshape(-1, 1, 2).astype(np.float32)
    )  # format coordinates as required for openCV
    coords = np.dstack([X, Y])  # format coordinates as (NxMx2)-matrix

    # trace points using the Lucas-Kanade algorithm
    p_1, st, err = cv2.calcOpticalFlowPyrLK(
        previous_frame, current_frame, p_0, None, **lk_params
    )

    # set all points which could not be successfully traces to NaN
    p_1[st == 0] = np.nan  # these are the new locations of the points
    p_0[st == 0] = np.nan

    # rearrange back to 2D grid
    p_1 = np.dstack([p_1[:, 0, 0].reshape(X.shape), p_1[:, 0, 1].reshape(X.shape)])
    p_0 = np.dstack([p_0[:, 0, 0].reshape(X.shape), p_0[:, 0, 1].reshape(X.shape)])

    # get difference vectors for each position
    delta_vec = p_1 - p_0

    n_quality_points = st.sum()  # number of points that could be successfully traced
    if n_quality_points < 1:  # return only zeros if no points could be traced at all
        delta_vec = np.zeros(X.shape + (2,))

    return delta_vec, coords, n_quality_points


class LKParams(T.NamedTuple):
    """Params for cv2.calcOpticalFlowPyrLK"""

    grid_spacing: int = 100  # spacing of the grid to be used
    win_size: T.Tuple[int, int] = (50, 50)  # window size for the Lucas-Kanade algorithm
    max_level: int = 4  # maximum level of pyramids for the Lucas-Kanade algorithm
    criteria: T.Tuple[int, int, float] = (  # openCV-recursive algorithm criteria
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
        100,
        0.01,
    )
    # flags: int = cv2.OPTFLOW_USE_INITIAL_FLOW


DEFAULT_LK_PARAMS = LKParams()
