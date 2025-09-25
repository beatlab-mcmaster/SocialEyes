"""
Stream.py

Author: Shreshth Saxena
Purpose: This script provides a class to handle video streams in SocialEyes.
"""

import cv2
import os
from tqdm import tqdm


class Stream:
     """
     Class to retrieve frames from a video stream

     Attributes:
        vid_path (str): Path to the video file.
        resize_res (tuple): Resolution to which frames are resized (width, height).
        cap (cv2.VideoCapture): Video capture object(s).
        max_length (int): Total number of frames in the video(s).
        curr_length (int): Current frame index in the video stream.
        curr_video_file (str): Name of the current video file being processed.
     """

     def __init__(self, vid_path, resize_res=None):
        """
        Initializes the Stream object with a video path and resize resolution.

        Args:
            vid_path (str): Path to the video file or list of paths for chunked video.
            resize_res (tuple): Resolution to resize frames to, specified as (width, height).
        """      
        
        self.vid_path = vid_path
        self.resize_res = resize_res
        if self.resize_res:
            self.resize_res = (int(resize_res[0]), int(resize_res[1]))
        self.curr_length = 0
        if isinstance(vid_path, list) and len(self.vid_path) > 0:
            self._chunks = True    
            self._gen = self._cap_gen(self.vid_path)
            self.cap = next(self._gen)  
        elif os.path.isfile(self.vid_path):
            self._chunks = False
            self.cap = cv2.VideoCapture(self.vid_path)
            self.curr_video_file = vid_path
        else: 
            raise Exception("Invalid video path provided:", self.vid_path)
        self.max_length = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

     def _cap_gen(self, list_of_vids):
        """
        Generator function to create video capture objects for each video in vid_path. Saves memory by yielding one video at a time.
        Yields:
            cv2.VideoCapture: Video capture object for each video in vid_path.
        """
        for vid in list_of_vids:
            cap = cv2.VideoCapture(vid)
            self.curr_length = 0
            self.curr_video_file = vid
            self.max_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            yield cap

     def _frame_gen(self, image):
        """
        Processes a single frame by resizing it and converting it to grayscale.
        Args:
            image (numpy.ndarray): The original color frame.
        Returns:
            tuple: A tuple containing:
                - image (numpy.ndarray): The resized color frame.
                - gray (numpy.ndarray): The resized grayscale frame.
                - scales (tuple): Scaling factors for width and height (original_width / new_width, original_height / new_height).
        """
        w, h = image.shape[1], image.shape[0]
        if self.resize_res:
            image = cv2.resize(image, self.resize_res, cv2.INTER_AREA)
        w_new, h_new = image.shape[1], image.shape[0]
        scales = (float(w) / float(w_new), float(h) / float(h_new))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image, gray, scales
     
     def get_props(self):
        """
        Retrieves properties of the current video stream.

        Returns:
            dict: A dictionary containing video properties such as FPS, width, height, and total frame count.
        """

        frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        return {
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": fps,
            "frame_count": frame_count,
            "duration":  frame_count/ fps if fps > 0 else 0
        }

     def next_frame(self, seek=0):
        """
        Retrieves the next frame from the video stream, optionally seeking to a specific frame index.
        Args:
            seek (int, optional): Frame index to seek to before retrieving the next frame. Defaults to 0 (no seeking).
        Returns:
            tuple: A tuple containing:
                - image (numpy.ndarray): The resized color frame.
                - gray (numpy.ndarray): The resized grayscale frame.
                - scales (tuple): Scaling factors for width and height (original_width / new_width, original_height / new_height).
        Raises:
            Exception: If seeking exceeds total frames.
            Exception: If unable to read the next frame.
        """
        ## Seek video stream if required
        if seek > 0:
            if self._chunks:
                total = 0
                for i, vid in enumerate(self.vid_path):
                    cap = cv2.VideoCapture(vid)
                    max_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    cap.release()
                    if seek <= total + max_length:
                        # Reset and restart generator from current video
                        self.close()
                        self._gen = self._cap_gen(self.vid_path[i:])  
                        self.cap = next(self._gen)
                        #seek to the correct frame in the current video
                        self.curr_length = seek-total-1
                        if self.curr_length > 0:
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.curr_length)
                        break
                    total += max_length
                if i == len(self.vid_path) - 1 and seek > total + max_length:
                    raise Exception(f"Seek position {seek} exceeds total frames in chunked videos.")
            else:
                if seek > self.max_length:
                    self.close()
                    raise Exception(f"Seek position {seek} exceeds total frames {self.max_length}.")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, seek - 1)
                self.curr_length = seek-1
        
        ## Read the next frame
        ret, image = self.cap.read()
        
        ## Process and return the frame if read successfully
        if ret:
            self.curr_length += 1
            return self._frame_gen(image)
        # If full video length was not read and there was an error reading the frame 
        elif self.curr_length < self.max_length:
            raise Exception(f"Cannot seek to next frame for vid: {self.curr_video_file}")
        # If full video was read check if more chunks are available
        elif self._chunks:
            try:
                self.close() 
                self.cap = next(self._gen)  
                return self.next_frame()                    
            except StopIteration:
                raise Exception("Read all chunks.")
            except Exception as e:
                raise  e
        # If all frames were read for a single video
        else:
            self.close()
            raise Exception(f"Read all frames for vid: {self.curr_video_file}")
        
     def close(self):
        """
        Releases the video capture object.
        """
        if self.cap.isOpened():
            self.cap.release()