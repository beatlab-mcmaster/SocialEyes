"""
homography_visualizer.py

Author: Shreshth Saxena
Purpose: Visualization utilities for homography results.
"""

import pandas as pd
import cv2
import os
import numpy as np
from tqdm import tqdm
try:
    from homography.homography_processor import Stream
    from offlineInterface.csv_processor import CSVProcessor
except:
    #resolve relative paths when executing independently    
    import sys
    sys.path.append("../")
    from homography.homography_processor import Stream
    from offlineInterface.csv_processor import CSVProcessor


class HomographyVisualizer:

    def __init__(self, resize, glasses_video_path, glasses_timestamp_path, gaze_path, transformed_path, central_video_path, central_timestamp_path, device_color, device_name):
        """
        Initializes a HomographyVisualizer instance with the necessary video and gaze data.
        """
        self.resize = resize
        self.glasses_video_path = glasses_video_path
        self.glasses_timestamp_path = glasses_timestamp_path
        self.gaze_path = gaze_path
        self.transformed_path = transformed_path
        self.central_video_path = central_video_path
        self.central_timestamp_path = central_timestamp_path
        self.outer_circle_color = device_color
        self.device_name = device_name
        self.gaze_cache = (0, 0) #initial coordinate for blink visualization
        self._init_dataframes()
        self._init_video_streamers()

    def _init_dataframes(self):
        """
        Load CSV data using CSVProcessor and merge the world, gaze, and camera timestamps.
        """
        oftype = {"timestamp_corrected": np.uint64, }
        self.transformed_gaze = CSVProcessor(self.transformed_path, {"timestamp [ns]": np.uint64}).read_csv()
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
        # Add transformed gaze columns to merged_df
        self.merged_df = pd.merge_asof(
                self.merged_df.sort_values("timestamp_corrected") ,
                self.transformed_gaze.sort_values("timestamp [ns]") ,
                left_on="timestamp_corrected",
                right_on="timestamp [ns]",
                direction="nearest",
                suffixes=["", "transformed"],
        )

    def _init_video_streamers(self):
        """
        Initialize video streamers for glasses and central videos.
        """
        self.glasses_cap = Stream(self.glasses_video_path, self.resize)
        self.central_cap = Stream(self.central_video_path, self.resize)

    def draw_gaze(self, frame, gaze_center,blink_id, inner_circle_color = (255,255,255), outer_circle_radius = 8, radius_diff = 2, 
                   overlay_font=True, font_scale = 0.25, font_color=(150,150,150), font_thickness=1, x_off = -1, y_off=3, line_length = 18, line_length_diff = 8):
        """
        Draw gaze visualization on a given frame. The gaze point is visualised as concentric circles of high contrasting colours to aid easy detection in changing environments.

        Args:
            frame (np.ndarray): The image frame on which to draw the gaze.
            gaze_center (tuple): The (x, y) coordinates of the gaze center.
            blink_id (float): Identifier for blink state. If NaN, indicates no blink; otherwise indicates a blink.
            inner_circle_color (tuple, optional): Color of the inner circles. Defaults to white (255, 255, 255).
            outer_circle_radius (int, optional): Radius of the outermost circle. Defaults to 8.
            radius_diff (int, optional): Difference in radius for each concentric circle. Defaults to 2.
            overlay_font (bool, optional): Flag to indicate if the device name should be overlaid on the frame. Defaults to True.
            font_scale (float, optional): Scale factor for the font. Defaults to 0.25.
            font_color (tuple, optional): Color of the font. Defaults to gray (150, 150, 150).
            font_thickness (int, optional): Thickness of the font. Defaults to 1.
            x_off (int, optional): X offset for text placement. Defaults to -1.
            y_off (int, optional): Y offset for text placement. Defaults to 3.
            line_length (int, optional): Length of the lines drawn when a blink occurs. Defaults to 18.
            line_length_diff (int, optional): Difference in length for each line drawn. Defaults to 8.

        Returns:
            np.ndarray: The frame with gaze visualization drawn on it.

        """
        outer_circle_color = tuple([int(255*i) for i in self.outer_circle_color]) #sns to cv2 accepted tupple 
        
        if np.isnan(blink_id):
            for i, radius in enumerate(range(outer_circle_radius, 0, -1*radius_diff)):
                ## Pick color for the circles
                if i==0:
                    color = outer_circle_color #outermost circle has a unique color for each device
                elif i%2!=0:
                    color = inner_circle_color #following inwards from the outer circle(i==0) every odd numbered ring (i == 1,3,..) is white  
                else:
                    color = (0,0,0) #and every even ring (i == 2,4,...) is black
                # Overlay circle on frame
                frame = cv2.circle(frame, gaze_center, radius, color, -1)
            self.gaze_cache = gaze_center
        else:
            #if blink
            for i, length in enumerate(range(line_length, 0, -1*line_length_diff)):
                ## Pick color for the circles
                if i==0:
                    color = outer_circle_color #outermost line has a unique color for each device
                elif i%2!=0:
                    color = inner_circle_color #following inwards from the outer circle(i==0) every odd numbered line (i == 1,3,..) is white  
                else:
                    color = (0,0,0) #and every even line (i == 2,4,...) is black
                #draw line
                frame = cv2.line(frame, (self.gaze_cache[0]-length//2, self.gaze_cache[1]), (self.gaze_cache[0]+length//2, self.gaze_cache[1]), color, thickness=font_thickness*3)
                
        # if overlay_font:
        #     frame = cv2.putText(frame, self.device_name[-2:], (gaze_center[0]+x_off, gaze_center[1]+y_off), cv2.FONT_HERSHEY_SIMPLEX , font_scale, font_color, font_thickness, cv2.LINE_AA)

        return frame
    
    def sync_generator(self, **kargs):
        """
        Returns synchronised worldview and central view frames with resp. gaze coordinates.
        """ 
        for _,row in self.merged_df.iterrows():
            # Read frames from the glasses and central videos
            try:
                image_g, gray_g, scales_g = self.glasses_cap.next_frame()   
                #seek central cap to synced frame number
                image_c, gray_c, scales_c = self.central_cap.next_frame(seek=row["frame_count"])
                image_c_raw = image_c.copy()

                #Fetch gaze coordinates 
                gaze_x, gaze_y = int(row["gaze x [px]"] / scales_g[0]), int(row["gaze y [px]"] / scales_g[1])
                tgaze_x, tgaze_y = int(row['transformed_gaze_x']), int(row['transformed_gaze_y'])

                #Fetch blink id
                blink_id = row["blink id"]

                # Overlay gaze on worldview
                image_g = self.draw_gaze(image_g, (gaze_x, gaze_y), blink_id, **kargs)
                # Overlay transformed gaze on centralview
                image_c = self.draw_gaze(image_c, (tgaze_x, tgaze_y), blink_id, **kargs)
                
                yield image_g, gaze_x, gaze_y, image_c, tgaze_x, tgaze_y, blink_id, image_c_raw
            except Exception as e:
                self.cleanup()
                raise e        

    def render_single_device(self, output_path, fourcc= cv2.VideoWriter_fourcc(*'mp4v'), fps=30.0):
        """
        Renders mp4 video with stacked worldview and centralview.
        
        Args:
            output_path (str): Path to save the output video file.
            fourcc (int, optional): FourCC code for the video codec. Defaults to cv2.VideoWriter_fourcc(*'mp4v').
            fps (float, optional): Frames per second for the output video. Defaults to 30.0.

        Raises:
            Exception: If an error occurs during video processing.
        """

        out = cv2.VideoWriter(output_path, fourcc, fps, (self.resize[0]*2, self.resize[1]))
        try:
            for image_g,_,_,image_c,_,_,_,_ in tqdm(self.sync_generator(overlay_font=False, outer_circle_radius=16, line_length=30, font_thickness=2)):
                # Stack the two views horizontally
                out.write(np.hstack((image_g, image_c)))
        except Exception as e:
            print(e)    
        out.release()

    def cleanup(self):
        """
        Clean up capture objects
        """
        cv2.destroyAllWindows()
        self.glasses_cap.cap.release()
        self.central_cap.cap.release()
