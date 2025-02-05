"""
csv_processor.py

Author: Biranugan Pirabaharan, Shreshth Saxena
Purpose: File management related to the Pupil Devices exported format.
"""

import os, glob
import zipfile
import json
import re 

try:
    from offlineInterface.csv_processor import CSVProcessor
except:
    #resolve relative paths when executing the interface independently from src/offlineInterface/    
    import sys
    sys.path.append("../")
    from offlineInterface.csv_processor import CSVProcessor


class FileProcessor:
    """
    A class that provides methods for processing files.

    Methods:
    - unzip_file(zip_path, extract_to): Unzips a file to the specified directory.
    - find_glasses_files(folder_path): Finds the paths of glasses-related files in a folder.
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
    def find_glasses_files(folder_path, 
                           worldview_fname = "Neon Scene Camera v1 ps1.mp4", 
                           gazecsv_fname = "ts_corr_gaze.csv",
                           worldtime_fname_pattern = r"ts_corr_world.*\.csv",
                           info_fname = 'info.json',
                           search_key = "",
                           use_info_json = False): #info.json is not included in exported PL rec files but included in PL cloud files
        """
        Finds the paths of glasses-related files in a folder.

        Parameters:
        - folder_path (str): The path to a device's eye tracking data directory.

        Returns:
        - glasses_video_path (str): The path of the glasses video file.
        - gaze_path (str): The path of the gaze CSV file.
        - glasses_timestamp_path (str): The path of the glasses timestamp CSV file.
        - name (str): The name of the glasses.

        """

        glasses_video_path = None
        gaze_path = None
        glasses_timestamp_path = None
        name = None

        for file_ in glob.glob(os.path.join(folder_path, "Neon/**/*"), recursive=True):
            if os.path.basename(file_) == worldview_fname and search_key in file_:  ##TODO: update filtering logic to be dynamic
                glasses_video_path = file_
            elif os.path.basename(file_) == gazecsv_fname and search_key in file_:
                gaze_path = file_
            elif re.match(worldtime_fname_pattern, os.path.basename(file_)) and search_key in file_:
                glasses_timestamp_path = file_
            elif use_info_json and os.path.basename(file_) == info_fname and search_key in file_:
                json_path = os.path.join(folder_path, file_)
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    name = data.get('android_device_name')
        if glasses_video_path and glasses_timestamp_path and glasses_timestamp_path:
            name = name if use_info_json else os.path.basename(folder_path)        
            return glasses_video_path, gaze_path, glasses_timestamp_path, name
        else:
            raise Exception("Error retrieving all files for device ", folder_path)

    @staticmethod
    def parse_glasses_dir(input_path, custom_dir =False, search_key="", device_name_from_info = False):
        """
        Retrieves the paths of glasses-related files from a directory and its subdirectories.

        Args:
        - input_path (str): The path of the directory where the Pupil Cloud files are located.

        Returns:
        - glasses_video_paths (list): A list of glasses video file paths.
        - glasses_timestamp_paths (list): A list of glasses timestamp CSV file paths.
        - gaze_paths (list): A list of gaze CSV file paths.
        - glasses_names (list): A list of glasses names.

        """
        glasses_video_paths, gaze_paths, glasses_names, glasses_timestamp_paths = [], [], [], []

        if not custom_dir:
            for file in os.listdir(input_path):
                if file.endswith('.zip'):
                    zip_file_path = os.path.join(input_path, file)
                    unzip_dir = os.path.join(input_path, 'recordings')
                    FileProcessor.unzip_file(zip_file_path, unzip_dir)

            # Finding paths for glasses files
            for file in os.listdir(unzip_dir):
                if os.path.isdir(os.path.join(unzip_dir, file)):
                    video_path, gaze_path, timestamp_path, name = FileProcessor.find_glasses_files(
                        os.path.join(unzip_dir, file), use_info_json=device_name_from_info)
                    glasses_video_paths.append(video_path)
                    gaze_paths.append(gaze_path)
                    glasses_timestamp_paths.append(timestamp_path)
                    glasses_names.append(name)
            
        else:
            for subject_dir in os.listdir(input_path):
                try:
                    video_path, gaze_path, timestamp_path, name = FileProcessor.find_glasses_files(os.path.join(input_path, subject_dir), search_key=search_key, use_info_json=device_name_from_info)
                except Exception as e:
                    print(e)
                    continue
                glasses_video_paths.append(video_path)
                gaze_paths.append(gaze_path)
                glasses_timestamp_paths.append(timestamp_path)
                glasses_names.append(name)
        print(f"Found files for {len(glasses_names)} glasses")
        print(f"found {len(glasses_video_paths)} glasses_videos, {len(gaze_paths)} gaze paths, and {len(glasses_timestamp_paths)} glasses timestamps")

        return glasses_video_paths, glasses_timestamp_paths, gaze_paths, glasses_names

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
