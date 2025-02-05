from dataclasses import dataclass
import typing as T
import numpy as np
from itertools import chain
from itertools import tee


@dataclass
class BlinkEvent:
    start_time: int = None
    end_time: int = None
    label: str = None


@dataclass(unsafe_hash=True, order=True)
class OfParams:
    """Parameters for feature vector calculation.

    Attributes:
    -------
    n_layers : int
        Number of optical flow layers for the feature vector concatenation.
    layer_interval : int
        Interval between the optical flow layers (in frames)
    average : bool
        If True, the optical flow layers are averaged.
    img_shape : tuple
        Size of the optical flow images (height, width).
    grid_size : int
        Number of grid points in each dimension (x and y).
    step_size : int
        Step size for the opitcal flow calculation.
    window_size : int
        Size of the search window at each pyramid level.
    stop_steps : int
        Criteria to stop the search.
    """

    n_layers: int = 5
    layer_interval: int = 7
    average: bool = False
    img_shape: tuple = (64, 64)
    grid_size: int = 4
    step_size: int = 7
    window_size: int = 15
    stop_steps: int = 3


@dataclass(unsafe_hash=True, order=True)
class PPParams:
    """Parameters for post processing

    Attributes:
    -------
    max_gap_duration_s : float
        Maximum duration of a gap between blink onset and offset events.
    short_event_min_len_s : float
        Minimum duration of a blink.
    smooth_window : int
        Size of the smoothing window.
    proba_onset_threshold : float
        Threshold for the onset probability.
    proba_offset_threshold : float
        Threshold for the offset probability.
    """

    max_gap_duration_s: float = 0.03
    short_event_min_len_s: float = 0.1
    smooth_window: int = 11
    proba_onset_threshold: float = 0.25
    proba_offset_threshold: float = 0.25


def create_grid(img_shape: T.Tuple[int, int], grid_size: int) -> np.ndarray:
    """Creates a regular grid and returns grid coordinates.

    Args:
    -------
    img_shape : tuple
        Grid size in px (e.g. (64, 64)).
    grid_size : int
        Number of grid points in each dimension (x and y).

    Returns:
    -------
    np.ndarray
        Grid coordinates.
    """

    x = np.linspace(0, img_shape[1], grid_size + 2, dtype=np.float32)[1:-1]
    y = np.linspace(0, img_shape[0], grid_size + 2, dtype=np.float32)[1:-1]
    xx, yy = np.meshgrid(x, y)
    p_grid = np.concatenate((xx.reshape(-1, 1), yy.reshape(-1, 1)), axis=1)
    return p_grid


def pad_beginning(generator, n) -> T.Generator:
    """Pads the beginning of a generator with the first element.

    Args:
    -------
    generator : generator
        Generator to pad.
    n : int
        Number of elements to pad.

    Returns:
    -------
    Returns the padded generator object.
    """

    first = next(generator)
    stream = chain((n + 1) * [first], generator)
    return stream


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)
