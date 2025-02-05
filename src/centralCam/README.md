# CentralCam Module
This module is used to record the centralview video and meta data. The centralview is a fixed perspective recording of the shared scene onto which the independent gaze of all viewers is projected for direct comparisons. The module is compatible with any standard webcam or network camera and also to specialised machine vision cameras from ArduCam (set "camera input" parameter in config file accordingly.)

### Usage

1. Before executing the operations please check the config parameters in `config.json`

```

{
    "output_dir": "outputs/",                         // Directory to save output files relative to the config file path.
    "frame_drop_threshold": 600,                      // No. of dropped frames before quitting recording. Set lower for stricter restrictions.
    "show_preview": false,                            // Set to true to show a live preview of the camera feed.
    "camera_input": "standard",                       // Choose the camera input: "standard" for default camera, "arducam" for ArduCam.
    "standard": {     
        "cam_src": 0,                                 // Set the camera source: 0 for the default webcam, or use the camera index for additional USB cameras. For network cameras, provide the RTSP stream URL.
        "write_to_raw": false,                        // Boolean to indicate if raw frames should be saved. Set to true to save unprocessed frames.
        "fps_calc_window": 180,                       // Number of frames to consider for calculating the frames per second (FPS). Adjust based on your needs.
        "resolution": {                               // The resolution depends on the camera and use case. Please ensure that the selected camera can support the selected resolution
            "width": 640,                             // Width of the video frames in pixels.             
            "height": 480                             // Height of the video frames in pixels. 
        }
    },
    "arducam": {                                      // Settings for the ArduCam camera input.
        "arducam_config": "arducam_config/xx.cfg",    // Path to the ArduCam config file for your specific camera. This config file is provided by the manufacturer (ArduCam)   
        "verbose": 0                                  // Verbosity level for ArduCam logs.
        "scale_width" : -1                            // Set scaling factor as required. Setting it to -1 will disable scaling.
    }
}


```

2. Install the requirements with `pip install -r requirements.txt` 

3. Run the module with `python3 main.py` 