# Offline Interface
The offline interface provides access to homography, visualisation, and analysis functions through an intuitive command line interface.

### Requirements
If you intend to use the interface to download data from Pupil Cloud please ensure that you have added your Pupil Labs Authentication token to an environment variable called PL_API_KEY

For all other operations, this utility assumes the following directory structure of eye-tracking data to operate:

```root_directory/  
│
├── device_ip_1/                      # Example device subdirectory (formatted as an IPv4 address xxx.xxx.xxx.xxx)
│   ├── Neon Scene Camera v1 ps1.mp4  # Worldview video file
│   ├── world_timestamps.csv           # Worldview timestamps CSV
│   ├── export_PLCloud/
│   │   ├── gaze.csv                   # Gaze data CSV file
│   │   └── blinks.csv                 # Blink data CSV file
│
├── device_ip_2/
│   ├── Neons Scene Camera v1 ps1.mp4
│   ├── world_timestamps.csv
│   ├── export_PLCloud/
│   │   ├── gaze.csv
│   │   └── blinks.csv
│
└── device_ip_n/
    ├── Neon Scene Camera v1 ps1.mp4
    ├── world_timestamps.csv
    ├── export_PLCloud/
    │   ├── gaze.csv
    │   └── blinks.csv
```

### Usage
1. Install the requirements with `pip install -r requirements.txt` 
2. Run the module with `python3 main.py` 