# Recording Export Utility

This utility extract data from raw recording files made on **Invisible** and **Neon** devices.

Gaze, IMU and world video data are exported as CSV files. Template data as json.

In addition, it performs post-hoc blink and fixation detection, and exports the data
as CSV.

```
Usage: pl-rec-export [OPTIONS] [RECORDINGS]...

Options:
  -e, --export-folder TEXT      Relative export path  [default:
                                (<recording>/export)]
  -f, --force                   Overwrite an existing export
  -v, --verbose                 Show more log messages (repeat for even more)
  --blinks / --no-blinks
  --fixations / --no-fixations
  --help                        Show this message and exit.
```

## Caveats

1. This script requires unaltered recordings that have been directly downloaded from Pupil Cloud or exported from the phone. It will not work on recordings that have been opened in Pupil Player.
2. Does not handle incomplete recordings (missing/corrupted files)
3. Fixations and saccades detected locally might vary from those exported from Pupil Cloud. This is due to differences in real-time gaze inference when compared to the full 200 Hz gaze data available in the Cloud.

## Installation

1. Install Python 3.8 or higher
2. ```bash
   pip install -e git+https://github.com/pupil-labs/pl-rec-export.git#egg=pl-rec-export
   ```
3. ```bash
   pl-rec-export /path/to/rec
   ```

**Note:**  The [`xgboost`](https://pypi.org/project/xgboost/) Python dependency might
require you to install further non-Python dependencies. If this is the case, it will
tell you how during the install or when running the script.

## Changelog

### 1.0.11

- Add support for exporting saccade data

### 1.0.10

- Use hardware timestamps for world.csv

### 1.0.9

- Add support for recordings lacking .time_aux files
- Fix issues with progress bars

### 1.0.8

- Add world video data export in world.csv

### 1.0.7

- Add roll/pitch/yaw to imu.csv
- Add azimuth/elevation to fixations.csv
- Allow processing of fixations when scene video is missing

### 1.0.6

- Fix bug when getting gaze in fixation detector

### 1.0.5

- Logs add debugging information about recording

### 1.0.4

- Mac M1 compatibility

### 1.0.3

- Bug fixes

### 1.0.2

- Python 3.8 compatibility

### 1.0.1

- Show version in cli

### 1.0.0

- Initial release
