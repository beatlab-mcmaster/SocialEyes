"""
main.py

Author:  Zahid Mirza, Shreshth Saxena
Purpose: Executes operations for the centralCam module, including video capture, recording, and metrics logging.
"""

import cv2
import time
import numpy as np
import sys
import os, shutil
from multiprocessing import Process, Queue
from recording_central import RecordingCentral
# from streaming_central import StreamingCentral
from central_metrics import CentralMetrics, CentralTimestampsOnly
from config import config

# Streaming or Recording or Both (Streaming mode is currently disabled permanently in this implementatiion)
STREAMING = False
RECORDING = True

def metrics_process(queue):
    """
    Separate process to log timestamps and frame data.

    This function runs in a separate process to handle logging of frame-related metrics such as jitter and FPS.
    It continually retrieves frame data from a queue, processes it, and updates metrics in CSV files.
    The process terminates when it receives a special signal (-1 timestamp).

    Args:
        queue (multiprocessing.Queue): Queue from which to retrieve frame data and metrics.
    """
    central_metrics = CentralMetrics(os.path.join(output_dir,"central_metrics_new.csv"), 
                                    ["frame_count", "st. dev (jitter) [s]", "fps"], 
                                    os.path.join(output_dir,"central_timestamp.csv"), 
                                    ["frame_count", "frame_fail_count", "timestamp [ns]"])
    while True:
        try:
            frame_count, frame_fail_count, timestamp, window_size = queue.get()
            if timestamp == -1:
                break
            central_metrics.add_timestamp(frame_count, frame_fail_count, timestamp, window_size)
        except KeyboardInterrupt:
            print("\nClosing metrics_process")
        except Exception as e:
            print(f"\nException in metrics_process: {e}")

def produce_central(cam, central_metrics_queue, frames_failed_threshold, output_dir, preview=False):
    """
    Captures and handles centralview video frames from the camera.

    This function handles capturing video frames, processing them, and either recording them to a file
    or streaming them to a Kafka topic (streaming currently disabled). It also manages frame failures and ensures the consistency of
    frame dimensions with the expected resolution. It sends frame metrics to the provided queue for logging.

    Args:
        cam (cv2.VideoCapture): The camera capture object for reading video frames.
        central_metrics_queue (multiprocessing.Queue): Queue to send frame metrics to another process for logging.
        frames_failed_threshold (int): Maximum number of consecutive failed frames before terminating the program.
        output_dir (str): Directory to save recorded frames (if recording is enabled).
        preview (bool, optional): Whether to show a preview of the captured video. Default is False.

    Raises:
        Exception: If the camera resolution does not match the expected resolution or if the number of consecutive failed frames exceeds the threshold.
        KeyboardInterrupt: If the user manually interrupts the process.

    Saves:
        - Video frames are saved in the specified output directory if recording is enabled.
    """

    #Read config
    window_size = config["standard"]["fps_calc_window"]
    write_to_raw = config["standard"]['write_to_raw']
    camera_resolution = config["standard"]["resolution"]    

    # Create Kafka Producer, if streaming is set
    # stream_obj = None
    # if STREAMING:
    #     stream_obj = StreamingCentral(config)
    # Create Recoding object, if recording is set 
    recording_obj = None
    if RECORDING:
        if write_to_raw:
            recording_obj = RecordingCentral(os.path.join(output_dir,"output_video.raw"), camera_resolution)
        else:
            recording_obj = RecordingCentral(os.path.join(output_dir, "output_video.mp4"), camera_resolution, False)

    frame_counter = 0
    consecutive_frames_failed = 0 # Counter
    print("Starting stream. Use Keyboard interrupt (ctrl/cmd+c) to stop")
    while cam.isOpened():
        try:        
            ret, frame = cam.read()
            current_timestamp = int(time.time() * 1e9) # Convert timestamp to nanoseconds

            if not ret:         
                if consecutive_frames_failed < frames_failed_threshold:
                    print("Failed to grab frame")
                    frame = np.zeros(camera_resolution, dtype=np.uint8) # Add empty frames to keep consistent fps
                    consecutive_frames_failed += 1
                elif consecutive_frames_failed >= frames_failed_threshold:
                    raise Exception(f"The number of failed consecutive frames have reached the threshold of {frames_failed_threshold}, terminating program")
            else:
                if not (frame.shape[1] == camera_resolution["width"] and frame.shape[0] == camera_resolution["height"]):
                    raise Exception(f"Camera resolution({camera_resolution}) does not match input resolution({frame.shape}). Please check config.")
                consecutive_frames_failed = 0
            
            if preview:
                # Show video output for testing
                cv2.imshow("video", frame)
                cv2.waitKey(1)
                
            # Sends timestamps to metrics object to be logged into a CSV file and used in calculations
            central_metrics_queue.put((frame_counter, consecutive_frames_failed,  current_timestamp, window_size))
            frame_counter += 1

            if RECORDING:
                recording_obj.write_frame(frame) # Save the frame to the video
            # if STREAMING:
            #     stream_obj.send_frame_to_kafka(frame, current_timestamp) # Produce frame to Kafka
            
        except KeyboardInterrupt:
            print("Closing stream")
            if not write_to_raw:
                recording_obj.close_file()
            cam.release()
            return
        except Exception as e:
            print("Error: ", e)
            pass



def produce_arducam(camera, output_dir, frames_failed_threshold, scale_width = -1, preview = False):
    """
    Captures video frames from an ArduCam camera , processes them, and saves the video to a file with recorded timestamps.
    
    Parameters:
    - camera (ArduCam object): The camera object for capturing frames.
    - output_dir (str): Directory to save the output video and timestamp CSV file.
    - frames_failed_threshold (int): Maximum number of consecutive failed frames before terminating the program.
    - scale_width (int, optional): The width to scale the frames. Default is -1 (no scaling).
    - preview (bool, optional): If True, displays a preview of the captured frames. Default is False.
    
    Raises:
    - Exception: If the number of consecutive failed frames exceeds the threshold.
    - KeyboardInterrupt: If the user manually stops the process.
    
    Saves:
    - Output video in `output_dir` as `output_video.mp4`.
    - Timestamps of captured frames in `output_dir/central_timestamp.csv`.
    """

    from arducam_utils import filetime_to_unix_ns
    #init camera
    time.sleep(2)
    camera.start()
    # camera.setCtrl("setFramerate", 2)
    # camera.setCtrl("setExposureTime", 20000)
    camera.setCtrl("setAnalogueGain", 800)
    #start counters
    frame_counter = 0
    consecutive_frames_failed = 0 # Max number of consecutive failed frames to handle (treat as blank frames) before stopping the program
    #init save object
    width, height = camera.cameraCfg["u32Width"], camera.cameraCfg["u32Height"]
    recording_obj = RecordingCentral(os.path.join(output_dir, "output_video.mp4"), {"width": width, "height": height}, False)

    #create timestamps csv
    central_metrics = CentralTimestampsOnly(os.path.join(output_dir,"central_timestamp.csv"), 
                                    ["frame_count", "frame_fail_count", "timestamp [u64]", "timestamp_corrected"])

    try:
        while True:
            ret, data, cfg = camera.read()

            if not ret:         
                if consecutive_frames_failed < frames_failed_threshold:
                    print("Failed to grab frame")
                    consecutive_frames_failed += 1
                elif consecutive_frames_failed >= frames_failed_threshold:
                    raise Exception(f"The number of failed consecutive frames have reached the threshold of {frames_failed_threshold}, terminating program")
                
            else:
                consecutive_frames_failed = 0
                timestamp = cfg['u64Time']
                image = convert_image(data, cfg, camera.color_mode)

                if scale_width != -1:
                    scale = scale_width / image.shape[1]
                    image = cv2.resize(image, None, fx=scale, fy=scale)

                recording_obj.write_frame(image)
                frame_counter += 1
                
                # write row to csv
                central_metrics.add_timestamp(frame_counter, consecutive_frames_failed, timestamp, filetime_to_unix_ns(timestamp))
                
                if preview:
                    cv2.imshow("Arducam", image)
                    cv2.waitKey(1)
        
    except KeyboardInterrupt:
        print("Closing stream")
        return
    except Exception as e:
        print("Error: ", e)
        pass
    finally:
        recording_obj.close_file()
        camera.stop()
        camera.closeCamera()


if __name__ == "__main__":

    # Check if camera is Standard or ArduCam
    cam_type = config["camera_input"]
    frames_failed_threshold = config["frame_drop_threshold"]
    preview = config["show_preview"]
    output_dir = os.path.join(config["output_dir"], f"test_{int(time.time())}")
    os.makedirs(output_dir)
    print(f"Initializing {cam_type} camera, outputs will be stored at {output_dir}")
    
    try:
        if  cam_type == "standard":
            # Init camera and output directory
            cam_src = config[cam_type]["cam_src"]
            cam = cv2.VideoCapture(int(cam_src)) 

            # Start the metrics process
            central_metrics_queue = Queue()
            metrics_worker = Process(target=metrics_process, args=(central_metrics_queue,))
            metrics_worker.daemon = True
            metrics_worker.start()
                
            produce_central(cam, central_metrics_queue, frames_failed_threshold, output_dir, preview)
            print(f"Exiting successfully.")
        
        elif cam_type == "arducam":
            from arducam_central import *
            from arducam_ImageConvert import *
            
            arducam_config = config[cam_type]["arducam_config"]
            verbose = config[cam_type]["verbose"]
            scale_width = config[cam_type]["scale_width"]
            
            camera = ArducamCamera()

            if not camera.openCamera(arducam_config):
                raise RuntimeError("Failed to open camera.")

            if verbose:
                camera.dumpDeviceInfo()

            produce_arducam(camera, output_dir, frames_failed_threshold, scale_width=scale_width, preview=preview)
            print(f"Exiting successfully.")

    except Exception as e:
            # Clean up and exit
            print("Error: ", e)
            print("Removing files and exiting")
            shutil.rmtree(output_dir)
            sys.exit()