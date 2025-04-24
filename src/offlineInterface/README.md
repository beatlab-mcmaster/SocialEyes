# Offline Interface
The offline interface provides access to homography, visualisation, and analysis functions through an intuitive command line interface.

### Requirements
If you intend to use the interface to download data from Pupil Cloud please ensure that you have added your Pupil Labs Authentication token to an environment variable called PL_API_KEY

The utility finds eye-tracking data using the filenames set in `config.json`. Please verify that the filenames are set correctly in the config before execution. Data for each recording should be stored in a separate folder named as the recording ID set by the Companion App. Each recording should in turn be in the parent folder of the device that was used to record it. Device folders could be either named as an IP address address or following the convention `Gxxx` with xxx representing a three digit device ID, to uniquely identify each device. 


### Usage
1. Install the requirements with `pip install -r requirements.txt` 
2. Set/verify parameters in `config.json`
3. Run the module with `python3 main.py` 