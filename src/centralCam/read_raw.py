"""
read_raw.py

Authors:  Zahid Mirza, Shreshth Saxena
Purpose: Reads and displays frames from a raw video file.
Note: This file is not a mandatory component, rather a utility to see the output of the raw video recorded by the centralCam module.
"""

import cv2
import numpy as np

if __name__ == "__main__":
    """
    Read and display frames from a raw video file.

    This script opens a raw video file ('output.raw'), reads frames from the file,
    converts the raw pixel data into a format compatible with OpenCV, and displays
    the frames in a window. The script continues to display frames until the end of the
    file or until the user presses the 'q' key.

    The raw data is assumed to be in BGR format with 3 bytes per pixel.

    The video dimensions (width and height) must be provided by the user and should match
    the dimensions used when creating the raw video file.
    """

    # Input these values to match your raw data
    width = int(input("Enter width of video"))  
    height = int(input("Enter height of video"))
    frame_size = width * height * 3  # 3 bytes per pixel for BGR

    # Open the raw file
    with open('output.raw', 'rb') as f:
        try:
            while True:
                # Read a single frame's worth of raw pixel data
                raw_data = f.read(frame_size)
                if len(raw_data) != frame_size:
                    break  # End of file

                # Convert the raw bytes to a format OpenCV can work with
                frame = np.frombuffer(raw_data, dtype=np.uint8).reshape((height, width, 3))

                # Display the frame
                cv2.imshow('frame', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except Exception as e:
            print("Error: ", e)
        finally:
            cv2.destroyAllWindows()