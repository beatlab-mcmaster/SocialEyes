"""
device.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: Implements the device class with Android Debug Bring (ADB) utility functions to monitor the device.
"""

import time
import random
import subprocess
import re
import threading
import numpy as np
from datetime import datetime, timedelta
import requests
import socket
import copy
import json
import os
import numpy as np
import traceback
import logging
import pytz
import html


base_dir = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(base_dir,"logs"), exist_ok=True)

logging.basicConfig(
    filename=os.path.join(base_dir,"logs", str(datetime.now().strftime('%y%m%dT%H%M%S')) + '_log.txt'), 
    encoding='utf-8', 
    level=logging.INFO, # change to DEBUG if required
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s') 
from enum import Enum 

class RecordingState(Enum):
    UNKNOWN = 0,
    RECORDING_IN_PROGRESS = 1, 
    RECORDING_HAS_NO_MP4 = 2,
    RECORDING_UNSAVED_OR_FAILED = 3,

class Device():
    """This class represents the state of the devices we use for mobile eye-tracking. 
    The data include ping, battery level, free storage space, ADB connection status, connected usb devices, info on the Neon Companion app.

    This code is tested only on Ubuntu 22.04.03 LTS, ADB v28.
    """    

    def __init__(self, ip_addr, port) -> None:
        self.ip_addr = ip_addr
        self.port = port
        
        self._ping = None
        self._adb_connection_is_established = None
        self._battery_level                 = None
        self._free_disk_space               = None
        self._connected_usb_devices         = None
        self._wifi_networks                 = None
        self._neon_companion_app_is_active  = None
        self._neon_companion_api_status     = None
        self._neon_companion_rtsp_server_status = None
        self._neon_companion_app_running_or_unsaved_recordings = {}
        self._neon_companion_device_name    = None
        self._neon_companion_frame_name     = None
        self._neon_companion_module_serial  = None
        self._vibrator_events               = None
        self._red_light_indicators          = None

        self._rec_id                        = None
        self._rec_state                     = None
        self._rec_duration                  = None

        self._adb_dumpsys_usb_threw_an_exception = False
        self._adb_df_threw_an_exception          = False

        self._logger = logging.getLogger(self.ip_addr)

        self._start_background_worker()

    @property
    def ping(self):
        """Ping from local machine to device

        Returns
        -------
        int
            Ping time in milliseconds, None if not yet determined
        """        
        return self._ping
    
    @property
    def wifi_networks(self):
        """Wifi networks this device is connected to

        Returns
        -------
        list[str]
            List of wifi network SSIDs
        """        
        return self._wifi_networks
    
    @property
    def adb_status(self):
        """Checks if the local machine has established an adb connection to the remote device, and if any adb calls threw an error.
        
        If adb connection isn't established, consider running $ adb connect <ip_addr>:<adb_port>, e.g. $ adb connect 192.168.35.101:5555
        
        Returns
        -------
        bool
            True, if adb connection is established and none of the subsequent adb calls threw an error, False otherwise.
        """        
        return self._adb_connection_is_established and self._adb_dumpsys_usb_threw_an_exception is False and self._adb_df_threw_an_exception is False
    
    @property
    def battery_level(self):
        """Battery level

        Returns
        -------
        int
            Battery level (%)
        """        
        return self._battery_level
    
    @property
    def free_disk_space(self):
        """Free disk space

        Returns
        -------
        float
            Free disk space (GB)
        """        
        return self._free_disk_space
    
    @property
    def connected_usb_devices(self):
        """Connected usb devices

        Returns
        -------
        list
            each element is a dict of {'manufacturer_name':, 'product_name':,}
        """        
        return self._connected_usb_devices
    
    @property
    def vibrator_events(self):
        """Last vibrator events

        Returns
        -------
        list
            each element is a dict of {'start_time':, 'end_time':, 'status':,}
        """
        return self._vibrator_events
    
    @property
    def red_light_indicators(self):
        """Indicators for red light flashing (according to recording log file)

        Returns
        -------
        dict
            key=rec_id, value=list of {'time':, 'file':, 'file_size':}
        """
        return self._red_light_indicators

    @property
    def app_status(self):
        """Checks if Neon Companion app is active

        Returns
        -------
        bool
            True if it is running, False if not, None if not yet determined.
        """        
        return self._neon_companion_app_is_active
    
    @property
    def app_api_status(self):
        """Checks if Neon Companion's API is reachable

        Returns
        -------
        bool
            True if it is running, False if not, None if not yet determined.
        """        
        return self._neon_companion_api_status
    
    @property
    def app_rtsp_status(self):
        """Checks if Neon Companion's RTSP server is reachable

        Returns
        -------
        bool
            True if it is running, False if not, None if not yet determined.
        """        
        return self._neon_companion_rtsp_server_status
    
    @property
    def app_recordings(self):
        """Checks if there are recordings running or unsaved.

        Returns
        -------
        dict
            Key = recording id, value = {workspace_id:, mp4_files:, recording_started_at:, rec_state:, rec_duration:}
        """        
        return self._neon_companion_app_running_or_unsaved_recordings
    
    @property
    def app_device_name(self):
        """Device name as reported by Neon Companion app

        Returns
        -------
        str
            Device name, or None if not yet determined
        """
        return self._neon_companion_device_name
    
    @property
    def app_frame_name(self):
        """Frame name as reported by Neon Companion app

        Returns
        -------
        str
            Frame name, or None if not yet determined
        """
        return self._neon_companion_frame_name
    
    @property
    def app_module_serial(self):
        """Module serial as reported by Neon Companion app

        Returns
        -------
        str
            Module serial, or None if not yet determined
        """
        return self._neon_companion_module_serial

    def _determine_ping(self):
        """
        Uses the `ping` command to send three requests and records the time taken for each.
        Updates the `_ping` attribute with the average time in milliseconds or sets it to None if there is no response.
        Logs a message if the ping value changes to None.
        """
        res = subprocess.getoutput(f'ping -c 3 -W 3 {self.ip_addr}') # 3 ping requests, wait up to 3s for responses
        re_search = re.findall('ttl=\d+\s+time=([0-9.]+)\s+ms', res)        
        if re_search is None or len(re_search) == 0:
            if self._ping is not None:
                self._logger.info('Ping value changed to None.')
            self._ping = None
        else:
            times = [float(e) for e in re_search]
            self._ping = int(np.average(times))
    
    def _determine_battery_status(self):
        """
        Uses the ADB command to fetch battery status and updates the `_battery_level` attribute.
        If unable to retrieve the battery level, sets it to None.
        Logs a message if the battery level changes to None.
        """
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell dumpsys battery')
        re_search = re.search('level:\s+(\d+)', res)        
        if re_search is None:
            if self._battery_level is not None:
                self._logger.info('Battery level value changed to None.')
            self._battery_level = None
        else:
            self._battery_level = int(re_search.groups()[0])

    def _determine_local_adb_connection_is_established(self):
        """
        Checks if a local ADB connection to the specified device is established.
        Uses the ADB command to list connected devices and updates the `_adb_connection_is_established` attribute.
        Logs changes in connection status.

        """
        res = subprocess.getoutput(f'adb devices | grep {self.ip_addr}')
        _adb_connection_is_established = res is not None and 'device' in res
        if res is None:
            if self._adb_connection_is_established is not None:
                self._logger.info('ADB connection changed to None.')
            self._adb_connection_is_established = None
        if self._adb_connection_is_established and not _adb_connection_is_established:
            self._logger.info('ADB connection changed to False.')
        elif not self._adb_connection_is_established and _adb_connection_is_established:
            self._logger.info('ADB connection changed to True.')
        self._adb_connection_is_established = _adb_connection_is_established

    def _determine_connected_usb_devices(self):
        """
        Uses ADB to identify connected USB devices on the specified device.
        Updates the `_connected_usb_devices` attribute with the list of devices.
        Logs errors if an exception occurs during the command execution.
        """
        output = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell dumpsys usb')
        output_lines = [l.strip() for l in output.split("\n")]

        result = []

        if any(['exception' in l.lower() for l in output_lines]):
            if not self._adb_dumpsys_usb_threw_an_exception:
                self._logger.error('Cannot determine connected usb devices due to an exception thrown by adb!')
                self._adb_dumpsys_usb_threw_an_exception = True
            self._connected_usb_devices = None
            return     
        elif self._adb_dumpsys_usb_threw_an_exception:
            self._logger.info('Functionality to detect usb devices has recovered.')
            self._adb_dumpsys_usb_threw_an_exception = False

        ### Determine relevant line boundaries in adb's output ###
        result = []
        try:
            output_lines.index('host_manager={') # raises ValueError

            devices_lines_start = output_lines.index('host_manager={') + 1
            devices_lines_end = devices_lines_start
            opened_curly = 0
            opened_brackets = 0
            for line in output_lines[devices_lines_start:]:
                if '{' in line:
                    opened_curly += 1
                elif '}' in line:
                    opened_curly -= 1
                elif '[' in line:
                    opened_brackets += 1
                elif ']' in line:
                    opened_brackets -= 1
                
                if opened_curly > 0 or opened_brackets > 0:
                    devices_lines_end += 1
                else: # i.e., all opened brackets are closed
                    break

            # Identify lines containing manufacturer_name
            indicators = [idx for idx,e in enumerate(output_lines) if re.search('manufacturer_name', e) is not None and idx > devices_lines_start and idx < devices_lines_end]

            for ind in indicators:
                result.append({
                    'manufacturer_name': output_lines[ind]  .split('=')[1],
                    'product_name':      output_lines[ind+1].split('=')[1]
                })

            if self._connected_usb_devices != result:
                self._logger.info(f'Connected usb devices list changed to: {result}')
        except ValueError:
            pass
        
        self._connected_usb_devices = result
        
    def _determine_neon_companion_api_status(self):
        """
        Sends a GET request to the API to check status and updates the `_neon_companion_api_status` attribute based on the response.

        Logs changes in the API status.
        """
        res = None
        try:
            res = requests.get(f'http://{self.ip_addr}:8080/api/status', timeout=5)
        except Exception as e:
            self._logger.debug(f'Neon API is not available: {e}')

        if res is not None and res.status_code == 200:
            if self._neon_companion_api_status is False:
                self._logger.info('Neon API status changed to True.')
            self._neon_companion_api_status = True
        else:
            if self._neon_companion_api_status is True:
                self._logger.info('Neon API status changed to False.')
            self._neon_companion_api_status = False
    
    def _determine_neon_companion_rtsp_server_status(self):
        """
        Attempts to connect to the RTSP server and checks the response to determine its status.
        Updates the `_neon_companion_rtsp_server_status` attribute accordingly.

        Logs changes in the RTSP server status.
        """
        res = None
        try:
            s = socket.socket()
            s.settimeout(5)
            s.connect((self.ip_addr, 8086))
            s.send('DESCRIBE / RTSP/1.0\r\nCSeq:1\r\n\r\n'.encode('ascii'))
            s_res = s.recv(4096).decode('ascii')

            res = 'RTSP/1.0 200 OK' in s_res
        except Exception as e:
            self._logger.debug(f'Neon RTSP server is not responding: {e}')
            res = False
        finally:
            if s is not None:
                s.close()
        
        if self._neon_companion_rtsp_server_status is False and res is True:
            self._logger.info('Neon RTSP server value changed to True.')
        if self._neon_companion_rtsp_server_status is True and res is False:
            self._logger.info('Neon RTSP server value changed to False.')
        self._neon_companion_rtsp_server_status = res

    def _determine_free_disk_space(self):
        """
        Uses the ADB command to determine the free space in the specified directory and updates the _free_disk_space attribute.

        Logs changes in free disk space or errors if an exception occurs.
        """
        output = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell df /storage/self/primary/Documents')
        output_lines = [l.strip() for l in output.split("\n")]
        
        if any(['exception' in l.lower() for l in output_lines]):
            if not self._adb_df_threw_an_exception:
                self._logger.error('Cannot determine free disk space due to an exception thrown by adb!')
                self._adb_df_threw_an_exception = True
            self._free_disk_space = None
            return     
        elif self._adb_df_threw_an_exception:
            self._logger.info('Functionality to detect free disk space has recovered.')
            self._adb_df_threw_an_exception = False

        if len(output_lines) > 0:
            search = re.search('\s+(\d+)\s+[\d.]+%', output_lines[1])
            result = None
            if search is not None:
                result = int(int(search.groups()[0]) / 1000 / 1000) # Kilobytes to Gigabytes
        
        if self._free_disk_space is not None and result is None:
            self._logger.info('Free disk space value changed to None.')
            self._free_disk_space = result
        elif self._free_disk_space != result:
            self._logger.info(f'Free disk space changed to {result}')
            self._free_disk_space = result

    def _determine_neon_companion_app_is_active(self):
        """
        Checks the stack of active apps on the device with ADB to see if the Neon app is listed as active.
        Updates the internal state and logs any changes in activity status.
        """
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell am stack list | grep neon')
        re_search = re.search('taskId=(\d+)', res)      

        new_value = re_search is not None and len(re_search.groups()) == 1
        if self._neon_companion_app_is_active and new_value is False:
            self._logger.info(f'Neon App activity status changed to False.')
        elif self._neon_companion_app_is_active is False and new_value:
            self._logger.info(f'Neon App activity status changed to True.')
        self._neon_companion_app_is_active = new_value

    def _determine_neon_companion_app_running_or_unsaved_recordings(self):
        """

        Queries the device's file system for temporary recording files and determines
        the state of recordings, including their duration and associated MP4 files.
        Logs changes in the recording state and the list of recordings.
        """
        base_dir = "/storage/self/primary/Documents/Neon/" # NB. trailing slash is part of this string
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell find {base_dir} -name temp_*.json')
        res_lines = res.split("\n")
        
        rec_state = None

        if any(['error' in l.lower() for l in res_lines]): # rec_state unknown
            self._logger.error(f'Cannot determine recording status: {res}')
            self._neon_companion_app_running_or_unsaved_recordings = {}
            rec_state = RecordingState.UNKNOWN

        elif res_lines == ['']: # rec_state no rec
            if len(self._neon_companion_app_running_or_unsaved_recordings) > 0:
                self._logger.info(f'List of running/unsaved recordings changed to 0.')
            self._neon_companion_app_running_or_unsaved_recordings = {}
        else:
            # Copy current state, reset current state
            old_neon_companion_app_running_or_unsaved_recordings = copy.deepcopy(self._neon_companion_app_running_or_unsaved_recordings)
            if self._neon_companion_app_running_or_unsaved_recordings is None:
                self._neon_companion_app_running_or_unsaved_recordings = {}

            for line in res_lines: # note: there can be one active recording, but multiple unsaved recordings
                workspace_id, recording_id, _ = line[len(base_dir):].split('/')

                mp4_filepaths = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell find {base_dir}{workspace_id}/{recording_id} -name *.mp4')
                mp4_filepaths = mp4_filepaths.split("\n") if len(mp4_filepaths) > 0 else []
                
                # Process mp4 files
                mp4_files = {}
                for fp in mp4_filepaths:
                    # Collect data on mp4 files
                    try:
                        fp = fp.replace(' ', '\\\\ ') # escape whitespace for adb shell cmd
                        stats_result = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell stat -t {fp}').split(' ')
                        *file_name_parts, size_bytes, _, _, _, _, _, _, _, _, _, _, modification_time, creation_time, _ = stats_result
                        file_name = ' '.join(file_name_parts)
                        timestamp_now = datetime.now().timestamp()

                        size_bytes = int(size_bytes)
                        creation_time = int(creation_time)
                        modification_time = int(modification_time)

                        size_bytes_change_per_second = None
                        
                        # Determine size change
                        if old_neon_companion_app_running_or_unsaved_recordings is None or recording_id not in old_neon_companion_app_running_or_unsaved_recordings:
                            continue

                        old_mp4_files = old_neon_companion_app_running_or_unsaved_recordings[recording_id]['mp4_files']
                        
                        if file_name not in old_mp4_files:
                            self._logger.info(f'New mp4 file detected: {file_name}')

                        if len(old_mp4_files) > 0 and file_name in old_mp4_files \
                            and '_meta' in old_mp4_files[file_name] and 'size_bytes_change_per_second' in old_mp4_files[file_name]['_meta']:
                            mp4_file_obj = old_mp4_files[file_name]
                            timestamp_old = mp4_file_obj['_meta']['timestamp_now']
                            size_bytes_previous = mp4_file_obj['size_bytes']
                            size_bytes_change_per_second = int((size_bytes - size_bytes_previous) / (timestamp_now - timestamp_old))
                            size_bytes_change_per_second_previous = mp4_file_obj['_meta']['size_bytes_change_per_second']
                            
                            if size_bytes_change_per_second_previous is not None and size_bytes_change_per_second_previous > 0 and size_bytes_change_per_second == 0:
                                self._logger.info(f'File size change rate has dropped to 0, file: {file_name}')
                            elif (size_bytes_change_per_second_previous is None or size_bytes_change_per_second_previous == 0) and size_bytes_change_per_second > 0:
                                self._logger.info(f'File size change rate is greater than 0, file: {file_name}')

                        mp4_files[file_name] = {
                            'size_bytes': size_bytes,
                            'creation_time': creation_time,
                            'modification_time': modification_time,
                            '_meta': {
                                'timestamp_now': timestamp_now,
                                'size_bytes_change_per_second': size_bytes_change_per_second
                            }
                        }
                    except Exception as e:
                        self._logger.error(f'Error while evaluating file {fp}: {e}')
                        self._logger.error(traceback.format_exc())

                # Determine rec_started_at
                recording_started_at = None
                recording_started_at_raw = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell stat -t {base_dir}{workspace_id}/{recording_id}/event.txt').split(' ')
                if len(recording_started_at_raw) >= 13:
                    recording_started_at = int(recording_started_at_raw[13])
                else:
                    self._logger.error(f'Couldn\'t determine recording_started_at, {recording_started_at_raw}')

                # Determine rec_duration
                rec_duration = None
                device_timestamp_now = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell date +"%s"')
                try:
                    device_timestamp_now = float(device_timestamp_now)
                    rec_duration = datetime.fromtimestamp(device_timestamp_now) - datetime.fromtimestamp(recording_started_at)
                except Exception as e:
                    self._logger.error(f'Cannot determine current time on device, {e}')

                # Determine rec_state
                if len(mp4_files) == 0 and rec_duration is not None and rec_duration > timedelta(seconds=5): # no mp4 files found
                    rec_state = RecordingState.RECORDING_HAS_NO_MP4
                else: # mp4 files found
                    files_which_have_no_sbcps = []
                    files_which_have_zero_sbcps = []
                    for file_name,file_obj in mp4_files.items():
                        sbcps = file_obj['_meta']['size_bytes_change_per_second']
                        if sbcps is None:
                            files_which_have_no_sbcps.append(file_name)
                        if sbcps == 0: 
                            files_which_have_zero_sbcps.append(files_which_have_zero_sbcps)
                    
                    if len(mp4_files) == 0 or len(files_which_have_no_sbcps) > 0:
                        rec_state = RecordingState.UNKNOWN
                    elif len(mp4_files) > 0 and len(files_which_have_zero_sbcps) < len(mp4_files):
                        rec_state = RecordingState.RECORDING_IN_PROGRESS
                    else:
                        rec_state = RecordingState.RECORDING_UNSAVED_OR_FAILED

                recording_obj = {
                    'workspace_id': workspace_id,
                    'mp4_files': mp4_files,
                    'recording_started_at': recording_started_at,
                    'rec_state': rec_state,
                    'rec_duration': rec_duration,
                }

                if recording_id not in self._neon_companion_app_running_or_unsaved_recordings.keys():
                    started_at_str = 'UNKNOWN' if recording_started_at is None else datetime.fromtimestamp(recording_started_at).strftime("%Y-%m-%d %H:%M:%S")
                    self._logger.info(f'Detected new recording {recording_id} (started at (rel. to device clock): {started_at_str})')   
                self._neon_companion_app_running_or_unsaved_recordings[recording_id] = recording_obj
            
            # Determine rec_state and rec_duration based on most recent recording object
            if len(self._neon_companion_app_running_or_unsaved_recordings) > 0:
                self._neon_companion_app_running_or_unsaved_recordings = dict(sorted(self._neon_companion_app_running_or_unsaved_recordings.items(), key=lambda item: item[1]['recording_started_at'], reverse=True))

                most_recent_recording_id, most_recent_recording_obj = list(self._neon_companion_app_running_or_unsaved_recordings.items())[0]

                self._rec_id = most_recent_recording_id
                self._rec_state = most_recent_recording_obj['rec_state']
                self._rec_duration = most_recent_recording_obj['rec_duration']

    def determine_neon_companion_app_identifiers(self):
        """
        Makes an API call to the Neon service to retrieve device and module
        information. Updates internal state with new identifiers and logs any changes.
        """
        res = None
        try:
            res = requests.get(f'http://{self.ip_addr}:8080/api/status', timeout=5)
        except Exception as e:
            self._logger.debug(f'Neon API is not reachable: {e}')

        res_json = {} if res is None or res.status_code != 200 else json.loads(res.content)
        if res is None or 'message' not in res_json or res_json['message'] != 'Success' or 'result' not in res_json:
            if self._neon_companion_device_name is None:
                self._logger.error(f'Cannot determine app identifiers: {res_json}')
            return

        device_name = frame_name = module_serial = None
        for e in res_json['result']:
            e_model = e['model']
            e_data  = e['data'] 
            if e_model == 'Phone':
                device_name = e_data['device_name']
            elif e_model == 'Hardware':
                frame_name = e_data['frame_name']
                module_serial = e_data['module_serial']

        if self._neon_companion_device_name != device_name:
            self._logger.info(f'Device name changed to {device_name}')
        if self._neon_companion_frame_name != frame_name:
            self._logger.info(f'Frame name changed to {frame_name}')
        if self._neon_companion_module_serial != module_serial:
            self._logger.info(f'Module serial changed to {module_serial}')

        self._neon_companion_device_name   = device_name
        self._neon_companion_frame_name    = frame_name
        self._neon_companion_module_serial = module_serial
        
    def _determine_wifi_connections(self):
        """
        Queries the device for its current Wi-Fi connections and updates the
        internal state with the network keys.
        """
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell dumpsys netstats | grep wlan')
        wifi_networks = re.search('wifiNetworkKey="([^"]+)"', res)
        if wifi_networks is not None:
            wifi_networks = list(set(wifi_networks.groups()))
        self._wifi_networks = ', '.join(wifi_networks) if isinstance(wifi_networks, list) else ''

    def _determine_indicators_of_red_flashing_light(self):
        """
        Checks the log files associated with active recordings to find
        instances of flashing red light indicators, logging any changes
        in the indicators found.
        """
        indicators = {}
        device_timezone = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell getprop persist.sys.timezone')
        device_tzinfo = pytz.timezone(device_timezone)
        for rec_id,rec_obj in self._neon_companion_app_running_or_unsaved_recordings.items():
            workspace_id = rec_obj['workspace_id']
            res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell grep /storage/self/primary/Documents/Neon/{workspace_id}/{rec_id}/android.log -e 30s')
            
            indicators[rec_id] = []
            
            for line in res.splitlines():
                re_search = re.search(f'(\d+-\d+ \d+:\d+:\d+.\d+).+({rec_id}.+)raw has not changed.+last size: (\d+)', line)
                if re_search is None:
                    continue
                log_time, file, last_size = re_search.groups()
                
                log_time_datetime = datetime.strptime(log_time, '%m-%d %H:%M:%S.%f')
                log_time_datetime.replace(year=self.now().year, tzinfo=device_tzinfo)
                
                file_name = html.unescape(file)

                last_size = int(last_size)

                indicators[rec_id].append({
                    'time': log_time_datetime,
                    'file': file_name,
                    'last_size': last_size
                })
        
        if self._red_light_indicators != indicators:
            self._logger.info(f'Red light indicators have changed: {indicators}')

        self._red_light_indicators = indicators
            

    def _determine_vibration_events(self):
        """
        Queries the device for vibration events, parses the output,
        and logs any changes in the recorded events.
        """
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell cmd vibrator_manager dump | grep neon')
        vibration_requests = re.findall('createTime: (.+), .+endTime: (.+), .+, status: (.+), effect:', res)
        timezone = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell getprop persist.sys.timezone')
        tzinfo = pytz.timezone(timezone)
        vibrator_events = []
        for res in vibration_requests:
            create_time, end_time, status = res

            create_time_datetime = datetime.strptime(create_time, '%m-%d %H:%M:%S.%f')
            create_time_datetime = create_time_datetime.replace(year=datetime.now().year, tzinfo=tzinfo)
            end_time_datetime = datetime.strptime(end_time, '%m-%d %H:%M:%S.%f')
            end_time_datetime = end_time_datetime.replace(year=datetime.now().year, tzinfo=tzinfo)

            vibrator_events.append({
                'create_time': create_time_datetime,
                'end_time': end_time_datetime,
                'status': status
            })
        vibrator_events.sort(key=lambda e: e['create_time'], reverse=True)    
        if vibrator_events != self._vibrator_events:
            self._logger.info(f'Vibrator events have changed: {vibrator_events}')
        self._vibrator_events = vibrator_events

    def now(self):
        """
        Executes a command on the device to retrieve the current date
        and time in ISO format.
        
        Returns:
            datetime: The current date and time of the device.
        """
        res = subprocess.getoutput(f'adb -s {self.ip_addr}:{self.port} shell date -Is')
        return datetime.fromisoformat(res)

    def _reset_values(self, no_ping=False, no_adb=False, no_app=False):
        """
        Resets various internal state variables to None or their default
        values, depending on the flags provided.

        Args:
            no_ping (bool): If True, reset values dependent on ping status.
            no_adb (bool): If True, reset values dependent on ADB connection status.
            no_app (bool): If True, reset values dependent on the app status.
        """
        if no_ping:
            no_adb = True
            no_app = True
        
        if no_adb:
            self._battery_level = None
            self._free_disk_space = None
            self._connected_usb_devices = None
            self._wifi_networks = None
            self._neon_companion_app_is_active = None
            self._neon_companion_app_running_or_unsaved_recordings = {}
            self._neon_companion_device_name   = None
            self._neon_companion_frame_name    = None
            self._neon_companion_module_serial = None
            self._vibrator_events = None
            self._red_light_indicators = None
        
        if no_app:
            self._neon_companion_api_status = None
            self._neon_companion_rtsp_server_status = None

    def _background_worker_run(self):
        """

        Runs in a loop to check the status of the device using above functions for
        network ping, ADB connection, battery status, app state, etc.
        Waits for a short period between checks to avoid overwhelming the device.
        """
        while True:
            try:
                self._determine_ping()
                if self._ping is not None:
                    self._determine_local_adb_connection_is_established()
                    if self._adb_connection_is_established is True:
                        self._determine_battery_status()
                        self._determine_free_disk_space()
                        self._determine_connected_usb_devices()
                        self._determine_vibration_events()
                        self._determine_indicators_of_red_flashing_light()
                        self._determine_wifi_connections()
                        self._determine_neon_companion_app_is_active()
                        self._determine_neon_companion_app_running_or_unsaved_recordings()
                        if self._neon_companion_app_is_active is True:
                            self._determine_neon_companion_api_status()
                            self.determine_neon_companion_app_identifiers()
                            self._determine_neon_companion_rtsp_server_status()
                        else:
                            self._reset_values(no_app=True)
                    else:
                        self._reset_values(no_adb=True)
                else:
                    self._reset_values(no_ping=True)

                time.sleep(2 + random.random() - 0.5)
            except:
                self._logger.error(traceback.format_exc())

    def _start_background_worker(self):
        """
        Initializes and starts a thread that runs the background worker
        to monitor the device's state.
        """
        t1 = threading.Thread(target=self._background_worker_run, daemon=True)
        t1.start()