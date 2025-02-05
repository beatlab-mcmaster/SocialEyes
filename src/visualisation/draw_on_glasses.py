"""
draw_on_glasses.py

Author: Biranugan Pirabaharan
Purpose: [Deprecated] This script draws the gaze onto the glasses videos.
"""

import random
import numpy as np
import pandas as pd
import cv2
import os
from csv_processing import CSVProcessor
from SuperGluePretrainedNetwork.models.utils import VideoStreamer


def draw_transformed_gaze_on_glasses(opt, csv_file, glasses_file, glasses_timestamp_path, glasses_name):
    """
    Draws transformed gaze on the central perspective video.

    Args:
        opt (object): Options object containing resize, skip, image_glob, and max_length parameters.
        csv_files (list): CSV file path containing gaze data.
        glasses_file (str): Path to the original glasses perspective video.
        glasses_timestamp_path (str): Path to the CSV file containing glasses timestamps.

    Output:
        MP4 file with gaze drawn on the glasses perspective video.
    """
    # Load CSV data using CSVProcessor
    oftype = {"timestamp [ns]": np.uint64}

    glasses_timestamps_df = CSVProcessor(glasses_timestamp_path, oftype, [
                                         'timestamp [ns]']).read_csv()

    # Randomly generate colours for gaze points.
    colour = (random.randint(66, 255), random.randint(
        66, 255), random.randint(66, 255))
    outline_colour = (random.randint(66, 255), random.randint(
        66, 255), random.randint(66, 255))
    print("Color", colour)

    print(csv_file)
    # Load the transformed gaze data and the central perspective video.
    gaze_df = CSVProcessor(
        csv_file, oftype, ['timestamp [ns]', 'gaze x [px]', 'gaze y [px]']).read_csv()
    print("Central Path", glasses_file)
    glasses_cap = VideoStreamer(
        glasses_file, opt.resize, opt.skip, opt.image_glob, opt.max_length)

    merged_df = pd.merge_asof(
        glasses_timestamps_df,
        gaze_df,
        on="timestamp [ns]",
        direction="nearest",
        suffixes=["video", "central"],
    )
    gaze_counter = 0

    # Write video with transformed gaze drawn on central perspective.
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    outputPath = opt.output_dir
    if not os.path.exists(outputPath):
        os.makedirs(outputPath)
    outputFile = 'glasses_with_gaze' + glasses_name + '.mp4'
    outputFilePath = os.path.join(outputPath, outputFile)
    central_image, grey_central, central_success = glasses_cap.next_frame()
    out = cv2.VideoWriter(outputFilePath, fourcc, 30.0,
                          (central_image.shape[1], central_image.shape[0]))

    # Draw gaze on central perspective using the transformed coordinates.
    while central_success:
        central_image, grey_central, central_success = glasses_cap.next_frame()
        # Draw gaze on central perspective using the transformed coordinates.
        gaze_x, gaze_y = merged_df.iloc[gaze_counter,
                                        1], merged_df.iloc[gaze_counter, 2]
        cv2.circle(central_image, (int(gaze_x/2.5), int(gaze_y/2.5)),
                   radius=10, color=outline_colour, thickness=5)
        cv2.circle(central_image, (int(gaze_x/2.5), int(gaze_y/2.5)),
                   radius=9, color=colour, thickness=-1)
        out.write(central_image)
        gaze_counter += 1

    out.release()
