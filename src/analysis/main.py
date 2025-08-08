"""
main.py

Author:  Shreshth Saxena
Purpose: Provides utility functions to analyse gaze and blink data recorded using SocialEyes
"""

import re
import cv2
import math, statistics
import pandas as pd
from matplotlib import cm 
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import distance, ConvexHull,QhullError
from st_dbscan import ST_DBSCAN 

def add_condition_cols(df, path, re_ip = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', re_cond = r'day(.)_(.*?)/'):
    """
    Extracts information from a path and adds columns to a DataFrame based on extracted values.

    Parameters:
    - df (DataFrame): The pandas DataFrame to which columns will be added.
    - path (str): A string containing the path from which information will be extracted.
    - re_ip (str, optional): Regular expression pattern to match and extract an IP address from `path`. Default is r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'.
    - re_cond (str, optional): Regular expression pattern to match and extract day and event information from `path`. Default is r'Innocents_day(.)_(.*?)/'.

    Returns:
    - DataFrame: A pandas DataFrame with additional columns 'device', 'day', 'event', and 'condition' based on extracted values from `path`.

    Raises:
    - Exception: If either `re.findall(re_ip, path)` or `re.findall(re_cond, path)` fails to find matches.
    """
    try:
        ip = re.findall(re_ip, path)[0]
        day, event = re.findall(re_cond, path)[0]
    except Exception as e:
        raise e

    df["device"] = ip
    df["day"] = day
    df["event"] = event
    df["condition"] = f"Day {day} {event}"
    return df

def eu_dist(pos1, pos2):
    """Calculate Euclidean distance between two positions of a table (row, column)."""
    return int(np.sqrt((pos2[0] - pos1[0])**2 + (pos2[1] - pos1[1])**2))

def reject_pts_outside_frame(df, x_lim = (0,640), y_lim = (0,480), x_col = "transformed_gaze_x", y_col = "transformed_gaze_y"):
    """
    Filter DataFrame points that fall outside specified x and y limits.

    Parameters:
    - df (DataFrame): The pandas DataFrame containing the points to filter.
    - x_lim (tuple, optional): Tuple specifying the inclusive range of x-values to keep. Default is (0, 640).
    - y_lim (tuple, optional): Tuple specifying the inclusive range of y-values to keep. Default is (0, 480).
    - x_col (str, optional): Name of the column in `df` containing x-coordinates. Default is "transformed_gaze_x".
    - y_col (str, optional): Name of the column in `df` containing y-coordinates. Default is "transformed_gaze_y".

    Returns:
    - DataFrame: A pandas DataFrame with points outside the specified ranges replaced with NaN values.
    """
    
    df[x_col] = df[x_col].where((x_lim[0] <= df[x_col]) & (df[x_col] < x_lim[1]))
    df[y_col] = df[y_col].where((y_lim[0] <= df[y_col]) & (df[y_col] < y_lim[1]))
    return df

def generate_heatmap(x_pts, y_pts, res=(640, 480), sigma=15):
    """
    Generates a heatmap based on the given points and parameters.
    
    Args:
        x_pts (list or array-like of type Int): X-coordinates of the points.
        y_pts (list or array-like of type Int): Y-coordinates of the points.
        res (tuple): Resolution of the heatmap in the form (width, height).
        sigma (int or float): Standard deviation for Gaussian kernel. Could be related to the visual degrees of eye movements.
        
    Returns:
        np.ndarray: Generated heatmap as a 2D array.
    """
    
    indices = np.zeros(res[::-1]) #heatmap resolution
    indices[y_pts, x_pts] = 1
    heatmap = gaussian_filter(indices,sigma=sigma)*255  
    return heatmap

def plot_heatmap(heatmap, alpha=0, beta=255, colormap = cv2.COLORMAP_VIRIDIS):
    """
    Plots a heatmap by normalizing and applying a colormap.
    
    Args:
        heatmap (np.ndarray): Input heatmap as a 2D array.
        alpha (int): Minimum intensity value for normalization.
        beta (int): Maximum intensity value for normalization.
        colormap (int): OpenCV colormap to apply.
        
    Returns:
        np.ndarray: Colormap applied heatmap as a 3D array.
    """
    # Normalize to range from 0 to 255
    heatmap_norm = cv2.normalize(heatmap, None, alpha=alpha, beta=beta, norm_type=cv2.NORM_MINMAX)
    # Convert heatmap to 8-bit and apply a colormap
    heatmap_norm = heatmap_norm.astype(np.uint8)
    heatmap_norm = cv2.applyColorMap(heatmap_norm, colormap)
    return heatmap_norm

def normalize(x, method='standard', axis=None):
    '''Normalizes the input with specified method.
    Parameters
    ----------
    x : array-like
    method : string, optional
        Valid values for method are:
        - 'standard': mean=0, std=1
        - 'range': min=0, max=1
        - 'sum': sum=1
    axis : int, optional
        Axis perpendicular to which array is sliced and normalized.
        If None, array is flattened and normalized.
    Returns
    -------
    res : numpy.ndarray
        Normalized array.
    '''
    # TODO: Prevent divided by zero if the map is flat
    x = np.array(x, copy=False)
    if axis is not None:
        y = np.rollaxis(x, axis).reshape([x.shape[axis], -1])
        shape = np.ones(len(x.shape))
        shape[axis] = x.shape[axis]
        if method == 'standard':
            res = (x - np.mean(y, axis=1).reshape(shape)) / np.std(y, axis=1).reshape(shape)
        elif method == 'range':
            res = (x - np.min(y, axis=1).reshape(shape)) / (np.max(y, axis=1) - np.min(y, axis=1)).reshape(shape)
        elif method == 'sum':
            res = x / np.float_(np.sum(y, axis=1).reshape(shape))
        else:
            raise ValueError('method not in {"standard", "range", "sum"}')
    else:
        if method == 'standard':
            res = (x - np.mean(x)) / np.std(x)
        elif method == 'range':
            res = (x - np.min(x)) / (np.max(x) - np.min(x))
        elif method == 'sum':
            res = x / float(np.sum(x))
        else:
            raise ValueError('method not in {"standard", "range", "sum"}')
    return res

def SIM(saliency_map1, saliency_map2):
    '''
    Similarity between two different heatmaps when viewed as distributions
    (SIM=1 means the distributions are identical).
    This similarity measure is also called **histogram intersection**.
    '''
    map1 = np.array(saliency_map1, copy=False)
    map2 = np.array(saliency_map2, copy=False)
    assert map1.shape == map2.shape, "Size of two maps do not match"
    # Normalize the two maps to have values between [0,1] and sum up to 1
    map1 = normalize(map1, method='range')
    map2 = normalize(map2, method='range')
    map1 = normalize(map1, method='sum')
    map2 = normalize(map2, method='sum')
    # Compute histogram intersection
    intersection = np.minimum(map1, map2)
    return np.sum(intersection)

def CC(saliency_map1, saliency_map2):
    '''
    Pearson's correlation coefficient between two different heatmaps
    (CC=0 for uncorrelated maps, CC=1 for perfect linear correlation).

    '''
    map1 = np.array(saliency_map1, copy=False)
    map2 = np.array(saliency_map2, copy=False)
    assert map1.shape == map2.shape, "Size of two maps do not match"
    # Normalize the two maps to have zero mean and unit std
    map1 = normalize(map1, method='standard')
    map2 = normalize(map2, method='standard')
    # Compute correlation coefficient
    return np.corrcoef(map1.ravel(), map2.ravel())[0,1]

def stationary_entropy(data, x_col, y_col, bin_size=20, screen_dim=(640, 480), show=False):
    """
    Calculate normalized spatial entropy of gaze positions in 2D space.

    Parameters
    ----------
    data : pandas.DataFrame
        DataFrame containing x and y coordinates of gaze samples.
    x_col : str
        Name of the column containing x-coordinates.
    y_col : str
        Name of the column containing y-coordinates.
    bin_size : int, default=20
        Size of histogram bins in pixels.
        (e.g., set to 1 visual degree equivalent for your setup)
    screen_dim : tuple of (int, int), default=(640, 480)
        Screen width and height in pixels.
    show : bool, default=False
        If True, prints intermediate entropy calculations.

    Returns
    -------
    float
        Normalized entropy value (0–1) of the gaze spatial distribution.

    Notes
    -----
    - Entropy is computed from the 2D histogram of gaze positions.
    - Normalization is done by dividing observed entropy by the maximum possible
      entropy given the screen dimensions and bin size.
    """
    df = data[[x_col, y_col]].dropna()
    df['x_range'] = pd.cut(df[x_col], np.arange(0, screen_dim[0] + bin_size, bin_size), right=False)
    df['y_range'] = pd.cut(df[y_col], np.arange(0, screen_dim[1] + bin_size, bin_size), right=False)
    counts = df.groupby(['x_range', 'y_range']).size().reset_index(name='count')
    counts['p'] = counts['count'] / counts['count'].sum()
    # Shannon entropy (base 2)
    counts['p*log(p)'] = counts['p'] * np.log2(counts['p'])
    # Maximum possible entropy (uniform distribution)
    max_H = math.log2((screen_dim[0] / bin_size) * (screen_dim[1] / bin_size))
    # Normalized entropy
    H = abs(counts['p*log(p)'].sum())
    norm_H = H / max_H

    if show:
        print(f"State Spaces: {screen_dim[0]/bin_size} × {screen_dim[1]/bin_size} "
              f"= {(screen_dim[0]/bin_size) * (screen_dim[1]/bin_size)}")
        print(f"Maximum entropy: {max_H:.4f}")
        print(f"Observed entropy: {H:.4f}")
        print(f"Normalized entropy: {norm_H:.4f}")

    return norm_H


def gaze_derivatives(data, x_col, y_col, ts_col="timestamp_corrected"):
    """
    Compute the first, second, and third derivatives (velocity, acceleration, jerk)
    of gaze position data in a 2D space, based on timestamps.

    Parameters
    ----------
    data : pandas.DataFrame
        DataFrame containing gaze coordinates and timestamps.
    x_col : str
        Name of the column containing x-coordinates of gaze.
    y_col : str
        Name of the column containing y-coordinates of gaze.
    ts_col : str, default="timestamp_corrected"
        Name of the column containing timestamps (must be numeric, in seconds or ms).

    Returns
    -------
    tuple
        velocity_mean : float
            Mean velocity magnitude.
        acceleration_mean : float
            Mean acceleration magnitude.
        jerk_mean : float
            Mean jerk magnitude.
        velocity : pandas.Series
            Instantaneous velocity magnitude at each timepoint.
        acceleration : pandas.Series
            Instantaneous acceleration magnitude at each timepoint.
        jerk : pandas.Series
            Instantaneous jerk magnitude at each timepoint.

    Notes
    -----
    - All derivatives are computed in Euclidean space from differences in `x` and `y`.
    - The timestamp column must be uniformly in seconds or milliseconds.
      If in milliseconds, divide `dt` by 1000 before computing derivatives.
    - Magnitudes are used for mean values to avoid cancellation of positive/negative changes.
    """
    data = data[[x_col, y_col, ts_col]].dropna()
    d_x = data[x_col].diff()
    d_y = data[y_col].diff()
    dt = data[ts_col].diff().astype(float)

    # Compute derivatives
    velocity = np.sqrt(d_x**2 + d_y**2) / dt
    acceleration = velocity.diff() / dt #2nd Derivative
    jerk = acceleration.diff() / dt #3rd Derivative

    return velocity.abs().mean(), acceleration.abs().mean(), jerk.abs().mean(), velocity, acceleration, jerk

def std_2D(data, x_col, y_col):
    """
    Calculate the spread of points in a 2D space using the standard deviation of Euclidean distances from each point to the mean point.

    Parameters
    ----------
    data : pandas.DataFrame
        Input DataFrame containing x and y coordinates.
    x_col : str
        Name of the column containing x-coordinates.
    y_col : str
        Name of the column containing y-coordinates.

    Returns
    -------
    float
        Standard deviation of Euclidean distances from each point to the mean point.
        Returns NaN if fewer than 2 valid points are provided.
    """
    pts = data[[x_col, y_col]].dropna().values
    num_points = len(pts)

    if num_points < 2:
        return np.nan
    
    # Euclidean distances to mean point
    x_mean, y_mean = pts.mean(axis=0)
    distances = [distance.euclidean([x_mean, y_mean], [x, y]) for x, y in pts]

    return statistics.stdev(distances)

def convex_hull(data, x_col, y_col, max_peri=None, max_area=None):
    """
    Compute the convex hull for a set of 2D points from a DataFrame and return the perimeter, normalized perimeter, area, normalized area, and point count.

    In 2D:
        - `hull.area` from SciPy is actually the perimeter length.
        - `hull.volume` is actually the polygon area.

    Parameters
    ----------
    data : pandas.DataFrame
        Input DataFrame containing x and y coordinates.
    x_col : str
        Name of the column containing x-coordinates.
    y_col : str
        Name of the column containing y-coordinates.
    max_peri : float, optional
        Maximum possible perimeter for normalization. If None, normalized perimeter is NaN.
    max_area : float, optional
        Maximum possible area for normalization. If None, normalized area is NaN.

    Returns
    -------
    perimeter : float
        Perimeter length of the convex hull.
    normalized_perimeter : float
        Perimeter divided by max_peri.
    area : float
        Area of the convex hull.
    normalized_area : float
        Area divided by max_area.
    num_points : int
        Number of valid points used in the computation.
    """
    pts = data[[x_col, y_col]].dropna().values
    num_points = len(pts)

    if num_points > 2:
        try:
            hull = ConvexHull(pts)
            peri, area = hull.area, hull.volume
            norm_peri = peri / max_peri if max_peri is not None else np.nan
            norm_area = area / max_area if max_area is not None else np.nan
            return peri, norm_peri, area, norm_area, num_points
        except QhullError:
            pass  # Degenerate case: collinear points

    return np.nan, np.nan, np.nan, np.nan, num_points


def DB_centroids(data, eps_spatial, eps_temporal=6, min_samples=2):
    """
    Calculate the centroids of identified clusters from spatial-temporal data using the DBSCAN algorithm.

    Parameters:
    ----------
    data : numpy.ndarray
        A 2D array where each row represents a data point with spatial and temporal dimensions.
    eps_spatial : float
        The maximum distance spatially between two samples from the same fixation cluster.
    eps_temporal : float, optional
        The maximum distance temporally between two samples from the same fixation cluster. 
        Default is set to 6, as determined in Saxena et al. (2023) for data sampled at 30 Hz Ref: https://github.com/ShreshthSaxena/Eye_Tracking_Analysis
    min_samples : int, optional
        The number of samples in a cluster for a point to be considered as a fixation. Default is 2.

    Returns:
    -------
    numpy.ndarray
        An array of centroids for the identified clusters, excluding outliers and the first fixation. 
        The centroids are returned as integer values representing the spatial dimensions.

    """
    st_dbscan = ST_DBSCAN(eps1 = eps_spatial, eps2 = eps_temporal, min_samples = min_samples).fit(data) 
    centroids = np.empty((0,2), int)
    #Exclude outliers and first fixation
    for cl in range(1, max(st_dbscan.labels)):
        centroids = np.append(centroids, np.median(data[st_dbscan.labels==cl,:], axis = 0)[1:].reshape(-1,2), axis=0)
    return centroids.astype(int)




