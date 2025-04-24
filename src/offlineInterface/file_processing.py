"""
csv_processor.py

Author: Biranugan Pirabaharan, Shreshth Saxena
Purpose: File management related to the Pupil Devices exported format.
"""

import os, glob
import zipfile
import json
import re 
from tqdm import tqdm

try:
    from offlineInterface.csv_processor import CSVProcessor
    from config import config
except:
    #resolve relative paths when executing the interface independently from src/offlineInterface/    
    import sys
    sys.path.append("../")
    from offlineInterface.csv_processor import CSVProcessor
    from config import config


class FileProcessor:
    """
    A class that provides methods for processing files.

    Methods:
    - unzip_file(zip_path, extract_to): Unzips a file to the specified directory.
    - parse_directories(input_path): Retrieves the paths of glasses-related files from a directory and its subdirectories.
    - get_central_data(input_path): Retrieves the paths of central video and timestamp files from a directory.
    - generate_transformed_gaze_csv_templates(output_path, glasses_names): Generates transformed gaze CSV templates for each pair of glasses.

    """

    @staticmethod
    def unzip_file(zip_path, extract_to):
        """
        Unzips a file to the specified directory.

        Args:
        - zip_path (str): The path of the zip file.
        - extract_to (str): The directory to extract the files to.

        """

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Filter out __MACOSX directory entries
            valid_files = [file for file in zip_ref.namelist(
            ) if not file.startswith('__MACOSX/')]
            # Extract only the valid files
            for file in valid_files:
                zip_ref.extract(file, extract_to)
    
    @staticmethod
    def device_name_from_path(path, name_as_ip = True):
        """
        Extracts a device name from a file system path based on Pupil Labs naming conventions.

        The device name can be searched as an identifier (e.g., "G001") or an IP address (e.g., "192.168.1.101")
        within a file path, starting from the last directory segment and moving backwards.

        Args:
            path (str): The file path from which to extract the device name or IP address.
            name_as_ip (bool, optional): 
                If True, returns the name as corresponding IP address.
                If False, returns the name in the "G###" format. Defaults to True.

        Returns:
            str or None: The extracted device name or IP address, or None if no valid match is found.

        """
        g_pattern = re.compile(r'^G\d{3}$')
        ip_pattern = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')

        for node in path.split(os.sep)[::-1]:  #Match last node first
            if g_pattern.fullmatch(node):
                if name_as_ip:
                    return config["defaults"]["network_id"] + "." + str(config["defaults"]["offset"] + int(node[-3:]))
                else:
                    return node
            elif ip_pattern.fullmatch(node):
                # Validate IP numbers are 0–255
                if name_as_ip and all(0 <= int(part) <= 255 for part in node.split('.')):
                    return node
                elif not name_as_ip:
                    return "G" + str(int(node.split()[-1]) - config["defaults"]["offset"]).zfill(3)
        return None

    @staticmethod
    def parse_glasses_dir(input_path, offset_corrected = True, search_key="", device_name_from_info = False):
        """
        Parses a directory to find recordings and relevant data files.

        This function recursively scans the given directory path for Pupil Labs recording folders, 
        identified by UUID-named directories. It collects file paths to key data streams such as 
        gaze, world, fixations, blinks, events, IMU, and saccades, as well as worldview videos. 
        Optionally, it determines the name of the glasses device either from metadata files or 
        from the directory structure.

        Args:
            input_path (str): The root directory to search through recursively.
            offset_corrected (bool, optional): 
                If True, expects files prefixed with 'ts_corr_' (offset-corrected versions).
                Defaults to False.
            search_key (str, optional): 
                If provided, only files containing this string in their path will be processed.
                Useful for filtering specific subsets of files. Defaults to "".
            device_name_from_info (bool, optional): 
                If True, attempts to read device name from the 'info.json' file within each recording.
                If False, device name is derived from the directory path. Defaults to False.

        Returns:
            tuple:
                - glasses_names (list of str): List of device names or IPs (based on config settings).
                - worldview_vids (list of str): List of file paths to worldview video files.
                - stream_csvs (dict of str: list of str): Dictionary mapping stream names
                ('gaze', 'world', 'fixations', 'blinks', 'events', 'imu', 'saccades', '3d_eye_states')
                to lists of corresponding file paths.
        """
        glasses_names, worldview_vids = [], []
        stream_csvs = {"gaze": [], "world": [], "fixations": [], "blinks": [], "events": [], "imu": [], "saccades": [], "3d_eye_states": []}
        pre = "ts_corr_" if offset_corrected else ""

        #Pupil Labs recording directories are named as UIDs so the following lines recursively searches for all dirs that match the UID regex
        uid_pattern = re.compile(r'[a-fA-F0-9]{8}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{12}')

        for p in tqdm(glob.glob(os.path.join(input_path, "**"), recursive=True), desc = "Scanning files..."):
            try:
                if os.path.isdir(p) and uid_pattern.fullmatch(os.path.basename(p)) and not os.path.basename(p).startswith("b5b4"): #rejecting workspace dirs which are also named as UIDs
                    name = None
                    for file_ in glob.glob(os.path.join(p, "**"), recursive=True):
                        if (not os.path.isfile(file_)) or (search_key not in file_):
                            continue
                        elif os.path.basename(file_) == config["paths"]["worldview_video_filename"]:
                            worldview_vids.append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["worldview_csv_filename"]:
                            stream_csvs["world"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["gaze_csv_filename"]:
                            stream_csvs["gaze"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["blinks_csv_filename"]:
                            stream_csvs["blinks"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["fixations_csv_filename"]:
                            stream_csvs["fixations"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["events_csv_filename"]:
                            stream_csvs["events"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["imu_csv_filename"]:
                            stream_csvs["imu"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["saccades_csv_filename"]:
                            stream_csvs["saccades"].append(file_)
                        elif os.path.basename(file_) == pre + config["paths"]["eye_states_csv_filename"]:
                            stream_csvs["3d_eye_states"].append(file_)
                        elif device_name_from_info and os.path.basename(file_) == config["paths"]["info_filename"]:
                            with open(file_, 'r') as f:
                                data = json.load(f)
                                name = data.get('android_device_name')
                    
                    name = name if name is not None else FileProcessor.device_name_from_path(p, name_as_ip=config["defaults"]["device_name_as_ip"])
                    glasses_names.append(name)
            except Exception as e:
                print(e)
                continue
                
        return glasses_names, worldview_vids, stream_csvs

    @staticmethod
    def parse_central_camera_dir(input_path, 
                                video_fname = "output_video.mp4", 
                                csv_fname = "central_timestamp.csv"):
        """
        Retrieves the paths of central video and corresponding timestamp file from a directory.

        Args:
        - input_path (str): The path of the directory.
        - video_fname (str): Filename for video file inside directory. Default value = "output_video.mp4"
        - csv_fname (str): Filename for timestamp csv file inside directory. Defaule value = "central_timestamp.csv"

        Returns:
        - central_video_path (str): The path of the central video file.
        - central_timestamp_path (str): The path of the central timestamp CSV file.
        """
        central_video_path = None
        central_timestamp_path = None
        # offset_path = None

        for file in os.listdir(input_path):
            if file == video_fname:
                central_video_path = os.path.join(input_path, file)
            elif file == csv_fname:
                # if file == 'offsets.csv':
                #     offset_path = os.path.join(input_path, file)
                # else:
                central_timestamp_path = (os.path.join(input_path, file))
        return central_video_path, central_timestamp_path 

    @staticmethod
    def generate_csv_templates(output_path, goal, glasses_names, cols):
        """
        Generates CSV templates for each pair of glasses.

        Args:
        - output_path (str): The path of the output directory for the transformed gaze CSV files.
        - glasses_names (list[str]): A list of glasses names.

        Returns:
        - csv_file_paths (list): A list of CSV file paths.

        """

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        csv_file_paths = []
        for name in glasses_names:
            csv_filename = f'{goal}_{name}.csv'
            csv_file_path = os.path.join(output_path, csv_filename)
            csv_file = CSVProcessor(csv_file_path, cols=cols)
            csv_file.write_csv()
            csv_file_paths.append(csv_file_path)
        return csv_file_paths
