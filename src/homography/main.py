"""
main.py

Author: Biranugan Pirabaharan, Mehak Khan, Zahid Mirza, and Shreshth Saxena
Purpose: This script performs homography on each of the Pupil Devices.
         The transformed gazes of each Pupil Device from homography will be outputted to a CSV file.
"""

import time
import os
import torch
torch.set_grad_enabled(False)
import argparse
import concurrent.futures
import seaborn as sns
import cv2
import numpy as np
from matplotlib import cm 
from tqdm import tqdm

try:
    from homography.homography_processor import HomographyProcessor
    from offlineInterface.file_processing import FileProcessor
    from homography.config import config
except:
    #resolve relative paths when executing independently    
    import sys
    sys.path.append("../")
    from homography.homography_processor import HomographyProcessor
    from offlineInterface.file_processing import FileProcessor
    from homography.config import config


class Params:
    """
    A class to hold configuration parameters for homography processing.
    """
    def __init__(self, homography_config, input_dir, cam_dir, output_dir):
        # Assign Values from config file.
        self.superglue = homography_config['setting']  # Indoor or outdoor
        # Maximum number of keypoints detected by Superpoint
        self.max_keypoints = homography_config['max_keypoints']
        # SuperPoint keypoint detector confidence threshold
        self.keypoint_threshold = homography_config['keypoint_threshold']
        # SuperPoint Non Maximum Suppression (NMS) radius
        self.nms_radius = homography_config['nms_radius']
        self.resize = homography_config['resize']  # Resize video frames dimensions
        self.skip = homography_config['skip']  # Frame increment for video frames
        # Number of iterations for Sinkhorn by SuperGlue
        self.sinkhorn_iterations = homography_config['sinkhorn_iterations']
        # SuperGlue match threshold
        self.match_threshold = homography_config['match_threshold']
        # Force pytorch to run in CPU mode.
        self.force_cpu = homography_config['force_cpu']
        #set dir paths
        self.input_dir = input_dir
        self.cam_dir = cam_dir
        self.output_dir = output_dir


def init_homography(input_dir, cam_dir, output_dir="./", multi_thread=False, **kargs):
    """
    Initialize homography processing using provided directories and configuration.

    Args:
        input_dir (str): Directory containing input files (e.g., video and gaze data).
        cam_dir (str): Directory containing centralview camera files.
        output_dir (str, optional): Directory to store output files. Defaults to "./".
        multi_thread (bool, optional): If True, use multithreading for faster processing. Defaults to False.

    Returns:
        None: This function does not return a value, but it initiates the homography processing and prints execution time.
    """

    # Get the homography configuration from the config file.
    homography_config = config['homography']    
    opt = Params(homography_config, input_dir, cam_dir, output_dir)
    
    start = time.time()
    
    # Unzip zip from pupil cloud
    glasses_names, worldview_video_paths, stream_csvs  = FileProcessor.parse_glasses_dir(opt.input_dir, **kargs)
    worldview_timestamps_paths = stream_csvs["world"]
    gaze_paths = stream_csvs["gaze"]

    # Finding paths for central files
    central_video_path, central_timestamps_path = FileProcessor.parse_central_camera_dir(opt.cam_dir)

    # Generate transformed gaze csv templates
    gaze_tranforms_paths = FileProcessor.generate_csv_templates(opt.output_dir, 'transformed_gaze', glasses_names, [
                                                                'timestamp [ns]', 'transformed_gaze_x', 'transformed_gaze_y', 'matches_conf', "gaze_x", "scale_w", "gaze_y", "scale_h"])
    # Generate homograph failure csv templates
    homography_failure_paths = FileProcessor.generate_csv_templates(
        opt.output_dir, 'homography_fails', glasses_names, ['timestamp [ns]', 'glasses frame #', 'central frame #', "gaze_x", "scale_w", "gaze_y", "scale_h"])

    # # Create HomographyProcessor instances
    homography_instances = []
    for i in range(len(glasses_names)):
        # Perform homography
        homography_instances.append(HomographyProcessor(
            opt,
            worldview_video_paths[i],
            worldview_timestamps_paths[i],
            gaze_paths[i],
            gaze_tranforms_paths[i],
            homography_failure_paths[i],
            central_video_path,
            central_timestamps_path
        ))
    print(f"Starting homography for {len(homography_instances)} recordings")

    if multi_thread:
        concurrent_start = time.time()
        # Use ProcessPoolExecutor to execute perform_homography concurrently
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submit all tasks to the executor
            futures = [
                executor.submit(
                    instance.perform_homography,
                )
                for instance in homography_instances
            ]

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
        
        concurrent_final = time.time()
        print("Time for concurrent: ", concurrent_final - concurrent_start)

    else:
        for instance in homography_instances:
            instance.perform_homography()

    # Prints time to execute.
    final = time.time()
    print(final - start)



if __name__ == "__main__":
    # Perform homography concurrently for multiple instances.
    parser = argparse.ArgumentParser(
        description='Perform homography with Superglue features',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Add arguments
    parser.add_argument(
        '--input_dir', type=str, default='./',
        help='Path to the directory that contains data for glasses in separate sub-directories')
    parser.add_argument(
        '--cam_dir', type=str, default='./',
        help='Path to the directory that contains data for centralcam recording')
    parser.add_argument(
        '--output_dir', type=str, default='./',
        help='Path to store results and outputs from the module')

    opt = parser.parse_args()
    init_homography(opt.input_dir, opt.cam_dir, opt.output_dir)


    