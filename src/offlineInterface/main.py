"""
main.py

Author: Shreshth Saxena, Biranugan Pirabaharan, Mehak Khan
Purpose: Main script to run that lets user pull recordings from Pupil Cloud,
         and perform homography on them through the console. Events can also 
         be added to the recordings through this script.
"""

import os
import sys
import questionary
import subprocess
from tqdm import tqdm
from config import config

try:
    from homography.main import init_homography
    from visualisation.main import viz_homography, viz_homography_grid, viz_homography_centralonly
    from offlineInterface.offset_adjust import TimeOffsetAdjuster
    from offlineInterface.file_processing import FileProcessor
    from offlineInterface.cloud_api import *
    from adb_download import AdbDownload
except:
    #resolve relative paths when executing the interface independently from src/offlineInterface/    
    import sys
    sys.path.append("../")
    from homography.main import init_homography
    from visualisation.main import viz_homography, viz_homography_grid, viz_homography_centralonly
    from offlineInterface.offset_adjust import TimeOffsetAdjuster
    from offlineInterface.cloud_api import *
    from offlineInterface.file_processing import FileProcessor
    from adb_download import AdbDownload

class Session:
    def __init__(self, root_dir):
        """
        A class to represent and manage a data session consisting of Pupil Labs Neon glasses recordings.
        The class initializes with a root_dir where all recordings are expected to be found.
        """
        self.root_dir = root_dir
        self.device_names = []
        self.device_ips = []
        self.worldview_vids = []
        self.stream_csvs = {}

    def validate_root_dir(self):
        """
        Validates and parses the root directory to locate relevant Neon glasses data.
        """
        questionary.print("Finding worldview and gaze data...", style="bold fg:ansiblue")
        self.device_names, self.worldview_vids, self.stream_csvs = FileProcessor.parse_glasses_dir(self.root_dir)
        
        questionary.print(f"Found {len(self.device_names)} device recordings")
        questionary.print(f"Found {len(self.worldview_vids)} worldview videos")
        for k,v in self.stream_csvs.items():
            questionary.print(f"Found {len(v)} {k} csv files")
    

if __name__ == "__main__":

    questionary.print("Welcome to the SocialEyes offline analysis interface.", style="bold fg:darkred")
    questionary.print("The interface links to some of the functionalities of homography, analysis, and visualisations modules for easy access. For a complete list of actions, check the respective module", style="bold fg:darkred")
    
    root_dir = questionary.path("Select root dir for data").ask()
    session = Session(root_dir)
    
    download_src = questionary.select('''If you already have the gaze and worldview data available locally, you can select the first option. \n If not, please select how would you like to fetch the data?''',
                        choices = ["Data already available",
                                    "Download data from devices on local network",
                                    "Download data from Pupil Cloud with PL_API_KEY"]).ask()

    if download_src == "Download data from Pupil Cloud with PL_API_KEY (beta functionality)":

        questionary.print("""
                        NOTE: To download data from Pupil Cloud, you'll need to setup PL_API_KEY environment variable for authentication)
                        After downloading, please ensure that the files are arranged in the directory structure specified in README""")
        
        if questionary.confirm("""Do you want to download data from PL Cloud?""").ask():            
            base_url = "https://api.cloud.pupil-labs.com/v2"
            api_key = os.environ.get("PL_API_KEY")
            auth_header = {"api-key": api_key}
            
            if not api_key:
                sys.exit("PL_API_KEY not found in environment variables")
            
            #Fetch all workspaces
            workspaces = get_workspaces(base_url, auth_header)
            selected_workspace = questionary.select("Select workspace where you want to search for recordings",
                            choices = workspaces.keys()).ask()
            workspace_id = workspaces[selected_workspace]

            #Select recording IDs
            all_recordings = get_all_recordings(base_url, workspace_id, auth_header)
            questionary.print(f"Found {len(all_recordings)} recordings in workspace: \n{list(all_recordings.keys())}")
            while True:
                resp = questionary.text("Please provide recording ids of selected recordings as a list [id1, id2, ...] OR Press 'a' to select all recordings").ask()
                if resp == "a":
                    recording_ids = list(all_recordings.keys()); break
                else:
                    try:
                        recording_ids = validate_ids(resp, all_recordings); break
                    except Exception as e:
                        questionary.print("Error validating response ", e)
            questionary.print(f"Selected recording_ids:  {recording_ids}", style="bold fg:darkgreen")

            #Download all selected recordings
            download_path = questionary.path("Select path to download recordings into.").ask()
            os.makedirs(session.root_dir, exist_ok=True)
            params = {"api-key": api_key,
                    "ids": recording_ids}
            download_recordings(base_url, workspace_id, params, os.path.join(download_path, "recordings.zip"))

            if questionary.confirm("Do you want to unzip the downloaded file?").ask():
                FileProcessor.unzip_file(os.path.join(download_path, "recordings.zip"), download_path)

    
    elif download_src == "Download data from devices on local network (beta functionality)":
        while True:
            try:
                questionary.print("We'll first initialize the range of IP addrs to lookup the devices")
                network_id = questionary.text("Enter Network ID (first three parts of the IP address, e.g., 192.168.1)").ask()
                questionary.print("Enter the range (start and end) for the host id (last part of IP address)")
                _start = questionary.text("start: ").ask()
                _end = questionary.text("end: ").ask()
                _start = int(_start); _end = int(_end)
                assert (0 <= int(_start) <= 255) and (0 <= int(_end) <= 255) and (_end > _start), "Incorrect range provided" ##Could improve verification to check entire IP addrs

                session.device_ips = [f"{network_id}.{i}" for i in range(_start, _end+1)]
                break
            except Exception as e:
                print(f"Error {e} \n Try again...")
                 
        selected_dev_ips = questionary.checkbox("Select devices to fetch data from", choices = session.device_ips).ask()
        assert len(selected_dev_ips) > 0, "No device selected"

        adb_download_session = AdbDownload(session.root_dir, selected_dev_ips)
        adb_opts = ["Download Neon folder", "Download recordings", "Download latest recording"] 
        operation = questionary.select("Select operation", choices = adb_opts).ask()

        for device_ip in adb_download_session.device_ips:    
            print(f'DEVICE {device_ip}')
            try:
                if operation == adb_opts[0]:
                    adb_download_session.download_neon_folder(device_ip)
                elif operation == adb_opts[1]:
                    adb_download_session.download_recordings(device_ip)
                elif operation == adb_opts[2]:
                    adb_download_session.download_last_recording(device_ip)
            except Exception as e:
                print(e)

    # Check root dir and find gaze/worldview data
    session.validate_root_dir()

    # Move on to actions
    while True:
        #Select action to perform through the console
        action = questionary.select("What action would you like to perform ?",
                        choices = [ "Perform Offset Correction",
                                    "Perform Homography",
                                    "Visualize Homography Results",
                                    "Exit Interface"]).ask()

        if action == "Perform Offset Correction":
            
            use_ransac = questionary.confirm("Use RANSAC (recommended for longer recordings)?").ask()

            offsets_path = questionary.path("Select offsets file (created by the GlassesRecord module) for the corresponding session").ask()
            if questionary.confirm("Would you like to add a search key for filtering files?").ask():
                search_key = questionary.text("Enter search key: ").ask()
            else:
                search_key = ""

            streams_sel = questionary.checkbox(
                'Select data streams to be corrected',
                choices = [questionary.Choice(stream, checked=True) for stream in session.stream_csvs.keys()]).ask()

            for stream in streams_sel:
                try:
                    #Filter based on search key
                    if not (search_key == ""): 
                        file_paths = [path for path in session.stream_csvs[stream] if search_key in path]
                    else:
                        file_paths = session.stream_csvs[stream]
                    
                    #Adjust offsets
                    for file_path in tqdm(file_paths, desc = stream):
                        dname = FileProcessor.device_name_from_path(file_path, config["defaults"]["device_name_as_ip"])
                        if dname == None:
                            print("Skipping, cannot convert to device name: ", file_path)
                            continue

                        adjuster = TimeOffsetAdjuster(dname, offsets_path)
                        if use_ransac:
                            adjuster.adjust_files_ransac([file_path], disable = True) #Disabling tqdm bar since we already add one above 
                        else:
                            adjuster.adjust_files([file_path], disable = True) 
                    
                except Exception as e:
                    print(e)
                    pass
                    
        
        elif action == "Perform Homography":
            offset_corrected = True if questionary.confirm("Use offset-corrected timestamps for homography?").ask() else False                

            if questionary.confirm("Would you like to add a search key for filtering glasses file paths?").ask():
                search_key = questionary.text("Enter search key: ").ask()
            else:
                search_key = ""

            #get central camera files
            cam_dir = questionary.path("Input path of the CentralCam recording dir.").ask()

            output_dir = questionary.path("Select path to dump homography results (transformed gaze in CentralCam coordinates)").ask()
            os.makedirs(output_dir, exist_ok=True)
            
            init_homography(session.root_dir, cam_dir, output_dir=output_dir, multi_thread=True, search_key = search_key, offset_corrected = offset_corrected)
            
        elif action == "Visualize Homography Results":
            action = questionary.select("Please select a visualisation mode from below",
                        choices = [ "1. Single-person gaze and worldview",
                                    # "2. Multi-person gaze and worldview",
                                    # "3. Single-person egocentric and transformed gaze view",
                                    "4. Multi-person transformed gaze on centralview",
                                    "5. Multi-person egocentric views with transformed gaze on centralview"]).ask()
            
            cam_dir = questionary.path("Select path of the central camera recording dir.").ask()
            output_dir = questionary.path("Select dir that contains homography results (transformed gaze in central cam. coordinates)").ask()
            if questionary.confirm("Would you like to add a search key for filtering files?").ask():
                search_key = questionary.text("Enter search key: ").ask()
            else:
                search_key = ""

            if action.startswith("1."):
                viz_homography(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, search_key=search_key)

            elif action.startswith("4."):
                action_overlay = questionary.select("Select one of the visualisation overlays",
                        choices = [ "Heatmap", "Convex Hull", "Gaze points"]).ask()
                if action_overlay == "Heatmap":
                    viz_homography_centralonly(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, show_heatmap=True, search_key=search_key)
                elif action_overlay == "Convex Hull":
                    viz_homography_centralonly(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, show_hull=True, search_key=search_key)
                else:
                    viz_homography_centralonly(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, search_key=search_key)

            elif action.startswith("5."):
                
                preempt = None
                if questionary.confirm("Do you wnat to preempt the rendering automatically after a certain frame number").ask():
                    while True:
                        preempt = questionary.text("Enter the no. of frames to preempt after").ask()
                        try:
                            preempt = int(preempt)
                            break
                        except:
                            questionary.print("Please enter a valid number")
                            pass

                if questionary.confirm("Press y to show heatmap or n to show raw gaze points on centralview").ask():
                    viz_homography_grid(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, show_heatmap=True, search_key=search_key, preempt=preempt, device_name_from_info=True)
                else:
                    viz_homography_grid(session.root_dir, cam_dir, output_dir, custom_dir_structure=True, search_key=search_key, device_name_from_info=True)
        
        elif action == "Exit Interface":
            if questionary.confirm("Are you sure you want to exit?"):
                sys.exit("offline_interface aborted")

        
        