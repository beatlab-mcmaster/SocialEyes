"""
homography_processor.py

Author: Biranugan Pirabaharan, Mehak Khan, Zahid Mirza, Shreshth Saxena
Purpose: This class contains all the main processing for homography.
"""

import pandas as pd
import cv2
import re, os
import numpy as np
import torch
torch.set_grad_enabled(False)
from SuperGluePretrainedNetwork.models.matching import Matching
from SuperGluePretrainedNetwork.models.utils import (process_resize, frame2tensor)
from tqdm import tqdm

try:
    from offlineInterface.csv_processor import CSVProcessor
except:
    #resolve relative paths when executing independently  
    import sys
    sys.path.append("../")
    from offlineInterface.csv_processor import CSVProcessor

class Stream:
     """
     Class to retrieve frames from a video stream

     Attributes:
        vid_path (str): Path to the video file.
        cap (cv2.VideoCapture): Video capture object.
        max_length (int): Total number of frames in the video.
        resize_res (tuple): Resolution to which frames are resized (width, height).
     """

     def __init__(self, vid_path, resize_res):
        """
        Initializes the Stream object with a video path and resize resolution.

        Args:
            vid_path (str): Path to the video file.
            resize_res (tuple): Resolution to resize frames to, specified as (width, height).
        """ 
        self.vid_path = vid_path
        self.cap = cv2.VideoCapture(vid_path)
        self.max_length = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.resize_res = (resize_res[0], resize_res[1])

     def next_frame(self, seek=0):
        """
        Retrieves the next frame from the video stream, optionally seeking to a specific frame.

        Args:
            seek (int, optional): Frame number to seek to. Defaults to 0, which continues from the current frame.

        Returns:
            tuple: A tuple containing:
                - image (numpy.ndarray): The resized color frame.
                - gray (numpy.ndarray): The resized grayscale frame.
                - scales (tuple): Scaling factors for width and height (original_width / new_width, original_height / new_height).

        Raises:
            Exception: If the frame cannot be retrieved.
        """
        if seek != 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, seek-1)
        ret, image = self.cap.read()
        if ret:
            w, h = image.shape[1], image.shape[0]    
            image = cv2.resize(image, self.resize_res, cv2.INTER_AREA)
            w_new, h_new = image.shape[1], image.shape[0]
            scales = (float(w) / float(w_new), float(h) / float(h_new))
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            return image, gray, scales
        else:
            raise Exception("Cannot seek to next frame for vid:", self.vid_path)

class HomographyProcessor:
    """
    Class for performing homography calculations and transforming gaze coordinates.

    Attributes:
        opt (object): Options object containing configuration parameters.
        glasses_video_path (str): Path to the glasses video file.
        glasses_timestamp_path (str): Path to the glasses timestamp CSV file.
        gaze_path (str): Path to the gaze CSV file.
        transformed_path (str): Path to the transformed gaze CSV file.
        central_video_path (str): Path to the central video file.
        central_timestamp_path (str): Path to the central timestamp CSV file.
        device (str): Runs homography process on GPU if CUDA is detected. Otherwise runs on CPU
        config (dict[str,dict[str,int]]): Defines configuration values to be used
        matching (Matching): SuperGlue defined object that matches key points between two images
        world_timestamps_df (pd.dataFrame): DataFrame of all the world timestamps
        webcam_timestamps_df (pd.dataFrame): Data Frame of all the webcam timestamps
        transformed_gaze (CSVProcessor): CSV file containing all the transformed gazes
        gaze_df (pd.dataFrame): Data Frame of the gaze data
        glasses_cap (VideoStreamer): Video of the glasses footage
        central_cap (VideoStreamer): Video of the central footage
        gaze_iterator (iterator): Contains all merged central and scene rows (merged by timestamp)
        gaze_counter (int): Counts row of the gaze data that the homography processor is currently on.

    Methods:
    - perform_homography(): Runs the main homography code
    - load_config(): Loads all the configuration variables
    - init_dataframes(): Loads all the CSV files. Additionally, it merges the glasses video and gaze data CSV files together by timestamp.
    - init_video_streamers(): Initializes the glasses and central videos.
    - sync_timestamps(): Syncs the timestamps between the glasses and central videos.
    - homography_loop(): Computes homography matrix to get transformed gazes throughout the entire video. Logs these gazes to a CSV.
    - cleanup(): Cleans up entire module after use.
    """

    def __init__(self, opt, glasses_video_path, glasses_timestamp_path, gaze_path, transformed_path, homography_failure_path, central_video_path, central_timestamp_path):
        self.opt = opt
        self.glasses_video_path = glasses_video_path
        self.glasses_timestamp_path = glasses_timestamp_path
        self.gaze_path = gaze_path
        self.transformed_path = transformed_path
        self.homography_failure_path = homography_failure_path
        self.central_video_path = central_video_path
        self.central_timestamp_path = central_timestamp_path
        #test start
        # ip = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', glasses_video_path)[0]
        # test_video_dump_path = os.path.join("/InPerson/test_dumps",ip+".mp4") 
        # fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
        # self.out = cv2.VideoWriter(test_video_dump_path, fourcc, 30.0, (self.opt.resize[0]*2, self.opt.resize[1]))
        #test end
        self.device = None
        self.config = None
        self.matching = None
        self.clahe = None
        self.world_timestamps_df = None
        self.glasses_cap = None
        self.glasses_counter = 0
        self.central_cap = None
        self.central_timestamps_df = None
        self.central_counter = 0
        self.gaze_df = None
        self.merged_df = None
        self.gaze_counter = 0
        self.transformed_gaze = None
        
    def perform_homography(self):
        """
        Perform the homography process.
        """
        self.load_config()
        self.init_dataframes()
        self.init_video_streamers()
        self.homography_loop()
        self.cleanup()

    def load_config(self):
        """
        Load configuration parameters and initialize the matching model.
        """
        # Load configuration parameters
        self.device = 'cuda' if torch.cuda.is_available() and not self.opt.force_cpu else 'cpu'
        print("Using device", self.device)
        self.config = {
            'superpoint': {
                'nms_radius': self.opt.nms_radius,
                'keypoint_threshold': self.opt.keypoint_threshold,
                'max_keypoints': self.opt.max_keypoints
            },
            'superglue': {
                'weights': self.opt.superglue,
                'sinkhorn_iterations': self.opt.sinkhorn_iterations,
                'match_threshold': self.opt.match_threshold,
            }
        }
        self.matching = Matching(self.config).eval().to(self.device)

    def init_dataframes(self):
        """
        Load CSV data using CSVProcessor and merge the world, gaze, and camera timestamps.
        """
        oftype = {"timestamp_corrected": np.uint64, }
        self.transformed_gaze = CSVProcessor(self.transformed_path)
        self.homography_failure = CSVProcessor(self.homography_failure_path)
        self.world_timestamps_df = CSVProcessor(self.glasses_timestamp_path, oftype, ['timestamp_corrected']).read_csv()
        self.central_timestamps_df = CSVProcessor(self.central_timestamp_path, oftype, ["timestamp_corrected", "frame_count"]).read_csv()
        self.gaze_df = CSVProcessor(self.gaze_path, oftype, 
                                    ['timestamp_corrected', 'gaze x [px]', 'gaze y [px]']).read_csv()
        # Sync world and gaze timestamps.
        gaze_and_world_df = pd.merge_asof(
                self.world_timestamps_df.sort_values("timestamp_corrected") ,
                self.gaze_df.sort_values("timestamp_corrected") ,
                on="timestamp_corrected",
                direction="nearest",
                suffixes=["_world", "_gaze"],
        )
        # Sync world and gaze with central video timestamps
        self.merged_df = pd.merge_asof(
                gaze_and_world_df.sort_values("timestamp_corrected") ,
                self.central_timestamps_df.sort_values("timestamp_corrected") ,
                on="timestamp_corrected",
                direction="nearest",
                suffixes=["", "_central"],
        )
        self.gaze_counter = 0

    def init_video_streamers(self):
        """
        Initialize video streamers for glasses and central videos.
        """
        self.glasses_cap = Stream(self.glasses_video_path, self.opt.resize)
        self.central_cap = Stream(self.central_video_path, self.opt.resize)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))      

    def homography_loop(self):
        """
        Calculates and transform gaze coordinates using homography.
        These transformed gaze coordinates are then logged into a CSV File.
        """
        # Perform homography loop
        for i,row in tqdm(self.merged_df.iterrows()):
            # Read frames from the glasses and central videos
            try:
                image_g, gray_g, scales_g = self.glasses_cap.next_frame()
                self.glasses_counter += 1   
                #seek central cap to synced frame number
                image_c, gray_c, scales_c = self.central_cap.next_frame(seek=row["frame_count"])
                self.central_counter += 1
            except Exception as e:
                print(e)
                break

            #Apply histogram equalization
            # grey_glasses = self.clahe.apply(grey_glasses)
            # grey_central = self.clahe.apply(grey_central)

            ##Render stacked video to test time sync 
            # self.out.write(np.hstack((image_g, image_c)))
            
            ## Perform homography
            
            trans_row = [row["timestamp_corrected"], -1, -1, np.nan, row["gaze x [px]"], scales_g[0], row["gaze y [px]"], scales_g[1]]
            inp0 = frame2tensor(gray_g, self.device)
            inp1 = frame2tensor(gray_c, self.device)
            pred = self.matching({'image0': inp0, 'image1': inp1})
            pred = {k: v[0].cpu().detach().numpy() for k, v in pred.items()}
            kpts0, kpts1 = pred['keypoints0'], pred['keypoints1']
            matches, conf = pred['matches0'], pred['matching_scores0']
            valid = matches > -1# -1 if the keypoint is unmatched
            point_set1 = kpts0[valid]
            matching_indexes = matches[valid]  
            point_set2 = kpts1[matching_indexes]
            mconf = conf[valid]
            # print("In glasses image:", len(point_set1), "\nIn central image:", len(point_set2))
            # Homography calculation
            if len(point_set1) > 4 and len(point_set2) > 4:
                H, _ = cv2.findHomography(point_set1, point_set2, method=0)
                if np.any(H): #non empty array  
                    gaze_point = np.array([[row["gaze x [px]"] / scales_g[0], row["gaze y [px]"] / scales_g[1]]], dtype=np.float32).reshape(-1, 1, 2)
                    transformed_gaze_point = cv2.perspectiveTransform(gaze_point, H)
                    transformed_gaze_x, transformed_gaze_y = transformed_gaze_point[0][0]
                    #Update transformed gaze values in the row
                    trans_row[1] = int(transformed_gaze_x)
                    trans_row[2] = int(transformed_gaze_y) 
                    trans_row[3] = H 
                else: #rare but possible that findhomography is not able to estimate the homography matrix
                    self.homography_failure.append_csv([row["timestamp_corrected"], self.glasses_counter, self.central_counter, row["gaze x [px]"], scales_g[0], row["gaze y [px]"], scales_g[1]])     
            else:
                self.homography_failure.append_csv([row["timestamp_corrected"], self.glasses_counter, self.central_counter, row["gaze x [px]"], scales_g[0], row["gaze y [px]"], scales_g[1]])
            self.transformed_gaze.append_csv(trans_row)
            self.gaze_counter += 1

    def cleanup(self):
        """
        Clean up all capture instances.
        """
        # cv2.destroyAllWindows()
        self.glasses_cap.cap.release()
        self.central_cap.cap.release()
        # self.out.release()