"""
recording_central.py

Authors:  Zahid Mirza, Shreshth Saxena
Purpose: Records centralview video frames to either a raw file or an MP4 file.
"""


import cv2
class RecordingCentral:
    def __init__(self, file_name, resolution, write_to_raw=True) -> None:
        """
        Initializes the recording setup based on the desired file format and resolution.

        Args:
            file_name (str): The path to the file where video frames will be recorded.
            resolution (dict): A dictionary containing 'width' and 'height' for the video resolution.
            write_to_raw (bool): Flag indicating whether to write to a raw file (True) or MP4 file (False).

        Raises:
            IOError: If there is an issue creating the file object for recording.
        """
        try:    
            self.write_to_raw = write_to_raw
            if write_to_raw:
                self.out = open(file_name, 'wb')
                self.outMP4 = None
            else:
                # Get offline video setup
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                self.out = None
                self.outMP4 = cv2.VideoWriter(file_name, fourcc, 30.0, (resolution["width"],resolution["height"]))
        except IOError as e:
            print(f"Failed to create recording file object: {e}")
            self.out = None
            self.outMP4 = None
    def write_frame(self, frame):
        """
        Writes a single video frame to the appropriate file based on the recording format.

        Args:
            frame (numpy.ndarray): The video frame to be written. Should be in BGR format.

        Raises:
            Exception: If there is an issue writing the frame to the file.
        """
        if self.out is not None and frame is not None:
            try:
                self.out.write(frame.tobytes())
            except Exception as e:
                print(f"Failed to write frame to RAW due to exception: {e}")
        elif self.outMP4 is not None and frame is not None:
            try:
                self.outMP4.write(frame)
            except Exception as e:
                print(f"Failed to write frame to MP4 due to exception: {e}")
    def close_file(self):
        """
        Releases resources associated with the video file.

        This method should be called to properly close the file and release resources associated
        with the video recording. It is particularly important for MP4 files to ensure that 
        all data is written and the file is properly finalized.

        Raises:
            AttributeError: If attempting to release a non-existent VideoWriter object.
        """

        if self.outMP4 is not None:
            try:
                self.outMP4.release()
            except AttributeError as e:
                print(f"Failed to release MP4 file due to exception: {e}")
