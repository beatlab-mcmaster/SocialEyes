"""
draw_on_central.py

Author: Biranugan Pirabaharan
Purpose: [Deprecated] This script draws all the transformed gazes onto the central perspective video.
"""

import random
import numpy as np
import cv2
import os
from csv_processor import CSVProcessor
from SuperGluePretrainedNetwork.models.utils import VideoStreamer


def draw_transformed_gaze_on_central(opt, csv_files, central_path, central_timestamp_path):
    """
    Draws transformed gaze on the central perspective video, final result is written to an MP4
    video file.

    Parameters:
        opt (options.NameSpace): Options object containing resize, skip, image_glob, and max_length parameters.
        csv_files (list[str]): List of CSV file paths containing transformed gaze data.
        central_path (str): File path to the original central perspective video.
        central_timestamp_path (str): File path to the CSV file containing central timestamps.
    
    Returns
    """
    # Load CSV data using CSVProcessor
    oftype = {"timestamp [ns]": np.uint64}
    central_timestamps_df = CSVProcessor(central_timestamp_path, oftype, [
                                         'timestamp [ns]']).read_csv()

    # Iterate through each CSV file and draw the transformed gaze on the central perspective video sequentially.
    count_file = 0
    for csv_file in csv_files:
        # If it is the first file, use the original central path. Otherwise, use the output path of the previous file.
        if count_file == 0:
            central_path = central_path
        print("Current CSV", csv_file)

        # Randomly generate colours for gaze points.
        colour = (random.randint(66, 255), random.randint(
            66, 255), random.randint(66, 255))
        outline_colour = (random.randint(66, 255), random.randint(
            66, 255), random.randint(66, 255))
        print("Color", colour)

        # Load the transformed gaze data and the central perspective video.
        gaze_df = CSVProcessor(csv_file, oftype, [
                               'timestamp [ns]', 'transformed_gaze_x', 'transformed_gaze_y']).read_csv()
        print("Central Path", central_path)
        central_cap = VideoStreamer(
            central_path, opt.resize, opt.skip, opt.image_glob, opt.max_length)
        gaze_counter = 0

        # Write video with transformed gaze drawn on central perspective.
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        outputPath = opt.output_dir
        if not os.path.exists(outputPath):
            os.makedirs(outputPath)
        outputFile = 'testOutput' + str(count_file) + '.mp4'
        outputFilePath = os.path.join(outputPath, outputFile)
        central_image, grey_central, central_success = central_cap.next_frame()
        out = cv2.VideoWriter(outputFilePath, fourcc, 30.0,
                              (central_image.shape[1], central_image.shape[0]))

        # Determine which DataFrame has the later first absolute timestamp.
        ahead_source = "world" if gaze_df.iloc[0,
                                               0] > central_timestamps_df.iloc[0, 0] else "central"
        larger_timestamp_df = gaze_df if ahead_source == "world" else central_timestamps_df
        smaller_timestamp_df = central_timestamps_df if larger_timestamp_df is gaze_df else gaze_df

        # Find the index where the timestamp in larger_timestamp_df is greater than the first timestamp in smaller_timestamp_df.
        skip_frames = (
            smaller_timestamp_df['timestamp [ns]'] > larger_timestamp_df.iloc[0, 0]).idxmax()
        print("Ahead source is:", ahead_source)
        print("Matched timestamp is:", skip_frames)

        # Fastforward in the video that started earlier: Syncing timestamps so looping through videos at same timestamp.
        if ahead_source == "world":
            for i in range(skip_frames):
                central_image, grey_central, central_success = central_cap.next_frame()
                out.write(central_image)
        else:
            for i in range(skip_frames):
                gaze_counter += 1

        # Determine which DataFrame has the later first absolute timestamp.
        ahead_source = "world" if gaze_df.iloc[0,
                                               0] > central_timestamps_df.iloc[0, 0] else "central"
        larger_timestamp_df = gaze_df if ahead_source == "world" else central_timestamps_df
        smaller_timestamp_df = central_timestamps_df if larger_timestamp_df is gaze_df else gaze_df

        # Find the index where the timestamp in larger_timestamp_df is greater than the first timestamp in smaller_timestamp_df.
        skip_frames = (
            smaller_timestamp_df['timestamp [ns]'] > larger_timestamp_df.iloc[0, 0]).idxmax()
        print("Ahead source is:", ahead_source)
        print("Matched timestamp is:", skip_frames)

        # Fast forward in the video that started earlier: Syncing timestamps so looping through videos at same timestamp.
        if ahead_source == "world":
            for i in range(skip_frames):
                central_image, _, central_success = central_cap.next_frame()
                out.write(central_image)
        else:
            for i in range(skip_frames):
                gaze_counter += 1

        # Draw gaze on central perspective using the transformed coordinates.
        while central_success and gaze_counter < len(gaze_df):
            central_image, _, central_success = central_cap.next_frame()
            # Draw gaze on central perspective using the transformed coordinates.
            gaze_x, gaze_y, _ = gaze_df.iloc['transformed_gaze_x'], gaze_df.iloc[
                'transformed_gaze_y'], gaze_df.iloc['timestamp [ns]']
            cv2.circle(central_image, (int(gaze_x), int(gaze_y)),
                       radius=10, color=outline_colour, thickness=5)
            cv2.circle(central_image, (int(gaze_x), int(gaze_y)),
                       radius=9, color=colour, thickness=-1)
            out.write(central_image)
            gaze_counter += 1

        # Continue writing video after gaze
        while central_success:
            central_image, _, central_success = central_cap.next_frame()
            out.write(central_image)

        out.release()
        central_path = outputFilePath
        count_file += 1
