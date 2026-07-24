"""
device.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: Implements the device class with Android Debug Bring (ADB) utility functions to monitor the device.
"""
import os
import re
from attr import dataclass
import numpy as np
import datetime
import copy
import json
import numpy as np
import traceback
import logging
import pytz
import html
from enum import Enum
from adb_utils import get_output, get_http
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
import traceback

class RecordingState(Enum):
    UNKNOWN = 0,
    IDLE = 1,
    RECORDING_IN_PROGRESS = 2,
    RECORDING_HAS_NO_MP4 = 3,
    RECORDING_UNSAVED_OR_FAILED = 4,

@dataclass
class RecordingInfoMp4Details:
    file_name: str
    size_bytes: int
    creation_time: int
    modification_time: int

@dataclass
class RecordingInfo:
    workspace_id: str
    recording_id: str
    state: RecordingState
    started_at: Optional[int] = None
    duration: Optional[float] = None
    details: Optional[dict] = None

class Fields(str, Enum):
    IP = 'ip'
    PING = 'ping',
    ADB = 'adb',
    BATTERY = 'battery'
    STORAGE = 'storage'
    USB = 'usb'
    WIFI = 'wifi'

    APP_ACTIVE = 'app_active'
    APP_API_STATUS = 'app_api_status'
    APP_RTSP_STATUS = 'app_rtsp_status'
    RECORDING_INFO = 'recording_info'

    DEVICE_NAME = 'device_name'
    FRAME_NAME = 'frame_name'
    MODULE_SERIAL = 'module_serial'

    VIBRATOR_EVENTS = 'vibrator_events'
    RED_LIGHT_INDICATORS = 'red_light_indicators'


class Device():
    """This class represents the state of the devices we use for mobile eye-tracking.
    The data include ping, battery level, free storage space, ADB connection status, connected usb devices, info on the Neon Companion app.

    This code is tested only on Ubuntu 22.04.03 LTS, ADB v28.
    """

    TIMEOUT = 30

    def __init__(self, ip_addr, port, on_change) -> None:
        self.ip_addr = ip_addr
        self.port = port
        self.on_change = on_change

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

        self._recording_info: Optional[dict[str, RecordingInfo]] = None

        self._adb_dumpsys_usb_threw_an_exception = False
        self._adb_df_threw_an_exception          = False

        self._logger = logging.getLogger(self.ip_addr)

        self._background_task: Optional[asyncio.Task] = None

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
        """Checks if the local machine has established an adb connection to the remote device.

        If adb connection isn't established, consider running $ adb connect <ip_addr>:<adb_port>, e.g. $ adb connect 192.168.35.101:5555

        Returns
        -------
        bool
            True, if adb connection is established, False otherwise.
        """
        return self._adb_connection_is_established

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

    PING_PATTERN = re.compile(r'ttl=\d+\s+time=([0-9.]+)\s+ms')
    BATTERY_PATTERN = re.compile(r'level:\s+(\d+)')
    APP_STATUS_PATTERN = re.compile(r'taskId=(\d+)')
    WIFI_NETWORKS_PATTERN = re.compile(r'wifiNetworkKey="([^"]+)"')

    _counters = {}
    async def _get_output(self, cmd):
        cmd_begin = cmd.split(' ')[0]
        if cmd_begin not in self._counters:
            self._counters[cmd_begin] = 0
        self._counters[cmd_begin] += 1
        self._logger.info([f"total = {len(asyncio.all_tasks())}", ", ".join([f'{k} = {v}' for k,v in self._counters.items()])])
        rc, res, err = await get_output(cmd, timeout=self.TIMEOUT)
        self._counters[cmd_begin] -= 1
        res = res if res is not None else ''
        return rc, res, err

    @asynccontextmanager
    async def _cmd_wrapper(self, cmd, ignore_rc=False):
        rc, res, err = await self._get_output(cmd)
        if len(err) > 0 or (not ignore_rc and rc != 0):
            self._logger.error(f'Executing command `{cmd}` failed: rc={rc}, err={err}')
        else:
            yield(res, rc)

    async def _update_ping(self):
        """
        Uses the `ping` command to send requests and record the time taken.
        Updates the `_ping` attribute with the average time in milliseconds or sets it to None if there is no response.
        """
        ping = None
        async with self._cmd_wrapper(f'ping -w 1 {self.ip_addr}; exit 0') as (res,_):
            if len(res) > 0:
                re_search = self.PING_PATTERN.findall(res)
                if re_search is not None and len(re_search) > 0:
                    times = [float(e) for e in re_search]
                    ping = int(np.average(times))
        self._ping = ping

    async def _update_battery_level(self):
        """
        Uses the ADB command to fetch battery status and updates the `_battery_level` attribute.
        If unable to retrieve the battery level, sets it to None.
        """
        battery_level = None
        async with self._cmd_wrapper(f'adb -s {self.ip_addr}:{self.port} shell dumpsys battery') as (res,_):
            if len(res) == 0:
                self._logger.error(f'Could not retrieve battery level')
            else:
                re_search = self.BATTERY_PATTERN.search(res)
                if re_search is not None:
                    battery_level = int(re_search.groups()[0])
                else:
                    battery_level = None
        self._battery_level = battery_level

    async def _update_adb_connection_is_established(self):
        """
        Checks if the host computer can connect to the device via ADB.
        Uses the ADB command to list connected devices and updates the `_adb_connection_is_established` attribute.

        """
        async with self._cmd_wrapper(f'adb devices | grep {self.ip_addr}', ignore_rc=True) as (res,rc):
            connection_established = None
            if len(res) > 0:
                connection_established = 'device' in res
            self._adb_connection_is_established = connection_established

    def _extract_manufacturer_name_and_product_name(self, adb_dumpsys_usb_output: str) -> list[dict]:
        result = []

        output_lines = [l.strip() for l in adb_dumpsys_usb_output.splitlines()]
        if any(['exception' in l.lower() for l in output_lines]) and not self._adb_dumpsys_usb_threw_an_exception:
            self._logger.warning('Cannot determine connected usb devices due to an exception thrown by adb!')
            self._adb_dumpsys_usb_threw_an_exception = True
        else:
            if self._adb_dumpsys_usb_threw_an_exception:
                self._logger.info('adb dumpsys usb no longer throws an exception, continuing to determine connected usb devices.')
                self._adb_dumpsys_usb_threw_an_exception = False

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
            except ValueError:
                pass

        return result

    async def _update_connected_usb_devices(self):
        """
        Uses ADB to identify connected USB devices on the specified device.
        Updates the `_connected_usb_devices` attribute with the list of devices.
        """
        connected_usb_devices = None
        async with self._cmd_wrapper(f'adb -s {self.ip_addr}:{self.port} shell dumpsys usb') as (res,_):
            connected_usb_devices = self._extract_manufacturer_name_and_product_name(res)
        self._connected_usb_devices = connected_usb_devices

    async def _update_api_status(self):
        """
        Sends a GET request to the API to check status and updates the `_neon_companion_api_status` attribute based on the response.

        Logs changes in the API status.
        """
        api_status = None

        status_code, res = await get_http(f'http://{self.ip_addr}:8080/api/status', timeout=self.TIMEOUT)
        api_status = status_code == 200

        self._neon_companion_api_status = api_status

    async def _update_rtsp_server_status(self):
        """
        Attempts to connect to the RTSP server and checks the response to determine its status.
        Updates the `_neon_companion_rtsp_server_status` attribute accordingly.
        """
        rtsp_status = None
        try:
            reader, writer = await asyncio.open_connection(self.ip_addr, 8086)

            writer.write('DESCRIBE / RTSP/1.0\r\nCSeq:1\r\n\r\n'.encode('ascii'))
            await writer.drain()
            s_res = (await reader.read(4096)).decode('ascii')

            rtsp_status = 'RTSP/1.0 200 OK' in s_res
        except Exception as e:
            if self._neon_companion_app_is_active:
                self._logger.error(f'Error while checking RTSP server status: {e}')
            rtsp_status = False

        self._neon_companion_rtsp_server_status = rtsp_status

    async def _update_free_disk_space(self):
        """
        Uses the ADB command to determine the free space in the specified directory and updates the _free_disk_space attribute.

        Logs changes in free disk space or errors if an exception occurs.
        """
        rc, output, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell df /storage/self/primary/Documents')

        if rc != 0:
            self._free_disk_space = None
            return

        output = output if output is not None else ''
        output_lines = [l.strip() for l in output.split("\n")]

        if any(['exception' in l.lower() for l in output_lines]):
            self._adb_df_threw_an_exception = True
            self._free_disk_space = None
            return
        elif self._adb_df_threw_an_exception:
            self._adb_df_threw_an_exception = False

        if len(output_lines) > 0:
            result = None

            if len(output_lines) >= 2 and "Available" in output_lines[0]:
                # Expected output:
                # Filesystem     1K-blocks     Used Available Use% Mounted on
                # /dev/fuse      237327340 26193832 211002436  12% /storage/emulated
                search = re.search(r'\s+(\d+)\s+[\d.]+%', output_lines[1])

                if search is not None:
                    result = int(int(search.groups()[0]) / 1000 / 1000) # Kilobytes to Gigabytes

        self._free_disk_space = result

    async def _update_app_status(self):
        """
        Checks the stack of active apps on the device with ADB to see if the Neon app is listed as active.
        Updates the internal state and logs any changes in activity status.
        """
        app_status = None
        async with self._cmd_wrapper(f'adb -s {self.ip_addr}:{self.port} shell am stack list | grep neon', ignore_rc=True) as (res, rc):
            if rc == 1 or len(res) == 0:
                app_status = False
            else:
                re_search = self.APP_STATUS_PATTERN.search(res)
                app_status = re_search is not None and len(re_search.groups()) == 1
        self._neon_companion_app_is_active = app_status

    async def _extract_mp4_details(self, filepath: str) -> Optional[RecordingInfoMp4Details]:
        result = None
        filepath = filepath.replace(' ', '\\\\ ')
        async with self._cmd_wrapper(f'adb -s {self.ip_addr}:{self.port} shell stat -t {filepath}') as (stats_result,_):
            stats_result = stats_result.split(' ') if stats_result is not None else []
            # <file_name_parts...> 383571347 751600 81b0 10341 1023 d2 34241 1 0 0 1784849101 1784849957 1784849957 4096
            *file_name_parts, size_bytes, _, _, _, _, _, _, _, _, access_time, modification_time, creation_time, _ = stats_result
            file_name = os.path.basename(' '.join(file_name_parts))

            size_bytes = int(size_bytes)
            creation_time = min(int(access_time), int(creation_time)) # TODO: This is a workaround for the fact that the creation time seems to always get updated while recording...
            modification_time = int(modification_time)

            result = RecordingInfoMp4Details(
                file_name=file_name,
                size_bytes=size_bytes,
                creation_time=creation_time,
                modification_time=modification_time
            )
        return result

    async def _extract_recording_info_details(self, base_dir: str, workspace_id: str, recording_id: str) -> dict[str, RecordingInfoMp4Details]:
        result = {}
        recording_dir = f"{base_dir}{workspace_id}/{recording_id}"
        async with self._cmd_wrapper(
            f'adb -s {self.ip_addr}:{self.port} shell find {recording_dir} -name "*.mp4"',
            ignore_rc=True
        ) as (mp4_filepaths,_):
            for mp4_filepath in mp4_filepaths.splitlines():
                details = await self._extract_mp4_details(mp4_filepath)
                result[mp4_filepath] = details

        return result


    async def _update_recording_info(self):
        """
        Queries the device's file system for temporary recording files and determines
        the state of recordings, including their duration and associated MP4 files.
        Logs changes in the recording state and the list of recordings.
        """
        base_dir = "/storage/self/primary/Documents/Neon/" # NB. trailing slash is part of this string

        recording_info = None

        # Use temp_*.json files to determine if there are any recordings in progress or unsaved recordings
        async with self._cmd_wrapper(
            f'adb -s {self.ip_addr}:{self.port} shell find {base_dir} -name temp_*.json',
            ignore_rc=True
        ) as (temp_json_file_paths,_):
            temp_json_file_paths = temp_json_file_paths.splitlines() if len(temp_json_file_paths) > 0 else []
            recording_info = {}
            # If there are multiple temp_*.json files, there is at least one unsaved (or orphan) recording
            for temp_json_file_path in temp_json_file_paths:
                workspace_id, recording_id, _ = temp_json_file_path[len(base_dir):].split('/')

                details = await self._extract_recording_info_details(base_dir, workspace_id, recording_id)

                # Determine recording duration
                recording_started_at = min([d.creation_time for d in details.values()]) if len(details) > 0 else None
                recording_modified_at = max([d.modification_time for d in details.values()]) if len(details) > 0 else None
                if recording_started_at is not None and recording_modified_at is not None:
                    if recording_modified_at < recording_started_at:
                        self._logger.warning(f"Recording {recording_id} has a modification time earlier than its start time.")
                    duration_seconds = recording_modified_at - recording_started_at
                else:
                    duration_seconds = None

                # Determine recording state
                if len(details) == 0:
                    state = RecordingState.RECORDING_HAS_NO_MP4
                else:
                    old_state = self._recording_info.get(recording_id) if self._recording_info is not None else None
                    if old_state is None:
                        if len(details) > 0:
                            state = RecordingState.RECORDING_IN_PROGRESS
                        else:
                            state = RecordingState.UNKNOWN
                    else:
                        self._logger.info(f"Past state found for recording {recording_id}. Determining state based on size changes.")
                        # old_state is not None
                        any_size_increased = False
                        for mp4_file_path,d in details.items():
                            current_size = d.size_bytes
                            old_size = old_state.details.get(mp4_file_path).size_bytes if mp4_file_path in old_state.details else None
                            self._logger.info(f"Comparing sizes for {mp4_file_path}: current size = {current_size}, old size = {old_size}")
                            if old_size is not None and current_size > old_size:
                                any_size_increased = True
                                break
                        state = RecordingState.RECORDING_IN_PROGRESS if any_size_increased else RecordingState.RECORDING_UNSAVED_OR_FAILED

                ri = RecordingInfo(
                    workspace_id=workspace_id,
                    recording_id=recording_id,
                    started_at=recording_started_at,
                    duration=duration_seconds,
                    state=state,
                    details=details,
                )
                recording_info[recording_id] = ri

        self._recording_info = recording_info

    async def _update_neon_companion_app_identifiers(self):
        """
        Makes an API call to the Neon service to retrieve device and module
        information. Updates internal state with new identifiers and logs any changes.
        """
        device_name = None
        frame_name = None
        module_serial = None

        if self._neon_companion_app_is_active:
            status_code, res = await get_http(f'http://{self.ip_addr}:8080/api/status', timeout=self.TIMEOUT)

            res_json = json.loads(res) if res is not None and status_code == 200 else {}
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
                for e in res_json['result']:
                    e_model = e['model']
                    e_data  = e['data']
                    if e_model == 'Phone':
                        device_name = e_data['device_name']
                    elif e_model == 'Hardware':
                        frame_name = e_data['frame_name']
                        module_serial = e_data['module_serial']

        self._neon_companion_device_name   = device_name
        self._neon_companion_frame_name    = frame_name
        self._neon_companion_module_serial = module_serial

    async def _update_wifi_connections(self):
        """
        Queries the device for its current Wi-Fi connections and updates the
        internal state with the network keys.
        """
        wifi_networks = None
        async with self._cmd_wrapper(
            f'adb -s {self.ip_addr}:{self.port} shell dumpsys netstats | grep wlan', 
            ignore_rc=True
        ) as (res, rc):
            if rc != 0:
                wifi_networks = []
            else:
                wifi_networks = self.WIFI_NETWORKS_PATTERN.search(res)
                if wifi_networks is not None:
                    wifi_networks = list(set(wifi_networks.groups()))
        self._wifi_networks = wifi_networks

    async def _update_red_light_indicators(self):
        """
        Checks the log files associated with active recordings to find
        instances of flashing red light indicators, logging any changes
        in the indicators found.
        """
        red_light_indicators = {}
        
        device_tzinfo = await self.device_timezone()
        for rec_id,rec_info in self._recording_info.items():
            workspace_id = rec_info.workspace_id
            # TODO test!
            rc, res, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell grep -e "raw has not changed" /storage/self/primary/Documents/Neon/{workspace_id}/{rec_id}/android.log')
            res = res if res is not None else ''
            red_light_indicators[rec_id] = []

            for line in res.splitlines():
                re_search = re.search(fr'(\d+-\d+ \d+:\d+:\d+.\d+).+({rec_id}.+)raw has not changed.+last size: (\d+)', line)
                if re_search is None:
                    continue
                log_time, file, last_size = re_search.groups()

                log_time_datetime = datetime.datetime.strptime(log_time, '%m-%d %H:%M:%S.%f')
                log_time_datetime.replace(year=self.now().year, tzinfo=device_tzinfo)

                file_name = html.unescape(file)

                last_size = int(last_size)

                red_light_indicators[rec_id].append({
                    'time': log_time_datetime,
                    'file': file_name,
                    'last_size': last_size
                })

        self._red_light_indicators = red_light_indicators

    async def _update_vibration_events(self):
        """
        Queries the device for vibration events, parses the output,
        and logs any changes in the recorded events.
        """
        vibrator_events = []
        rc, res, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell cmd vibrator_manager dump | grep neon')
        res = res if res is not None else ''
        vibration_requests = re.findall(r'createTime: (.+), .+endTime: (.+), .+, status: (.+), effect:', res)
        device_tzinfo = await self.device_timezone()
        for res in vibration_requests:
            create_time, end_time, status = res

            create_time_datetime = datetime.datetime.strptime(create_time, '%m-%d %H:%M:%S.%f')
            create_time_datetime = create_time_datetime.replace(year=datetime.datetime.now().year, tzinfo=device_tzinfo)
            end_time_datetime = datetime.datetime.strptime(end_time, '%m-%d %H:%M:%S.%f')
            end_time_datetime = end_time_datetime.replace(year=datetime.datetime.now().year, tzinfo=device_tzinfo)

            vibrator_events.append({
                'create_time': create_time_datetime,
                'end_time': end_time_datetime,
                'status': status
            })
        vibrator_events.sort(key=lambda e: e['create_time'], reverse=True)

        self._vibrator_events = vibrator_events

    async def now_iso(self) -> datetime.datetime | None:
        """
        Executes a command on the device to retrieve the current date
        and time in ISO format.

        Returns:
            datetime.datetime: The current date and time of the device.
        """
        rc, res, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell date -Is')
        if res is None:
            return None
        return datetime.datetime.fromisoformat(res)

    async def now_timestamp(self) -> int | None:
        rc, res, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell date +%s')
        if res is None:
            return None
        return int(res)

    async def device_timezone(self) -> datetime.tzinfo | None:
        rc, device_timezone, err = await self._get_output(f'adb -s {self.ip_addr}:{self.port} shell getprop persist.sys.timezone')
        device_timezone = device_timezone if device_timezone is not None else ''
        if not any(e in device_timezone for e in ["adb:", "exception", "error"]) and len(device_timezone) > 0:
            device_tzinfo = pytz.timezone(device_timezone)
            return device_tzinfo
        return None
    async def _background_worker_run(self):
        """
        Runs in a loop to check the status of the device using above functions for
        network ping, ADB connection, battery status, app state, etc.
        Waits for a short period between checks to avoid overwhelming the device.
        """
        last_state = {}

        while True:
            try:
                cycle_start = datetime.datetime.now()

                results = await asyncio.gather(
                    asyncio.wait_for(self._update_ping(), timeout=1.5),
                    asyncio.wait_for(self._update_adb_connection_is_established(), timeout=self.TIMEOUT),
                    return_exceptions=True
                )
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        self._logger.error(f"Error during background worker cycle #1 for task #{idx}: {res}", exc_info=res)


                if self._ping is not None and self._adb_connection_is_established is True:
                    results = await asyncio.gather(
                        asyncio.wait_for(self._update_battery_level(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_free_disk_space(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_connected_usb_devices(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_vibration_events(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_wifi_connections(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_app_status(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_recording_info(), timeout=self.TIMEOUT),

                        asyncio.wait_for(self._update_api_status(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_neon_companion_app_identifiers(), timeout=self.TIMEOUT),
                        asyncio.wait_for(self._update_rtsp_server_status(), timeout=self.TIMEOUT),

                        return_exceptions=True
                    )
                    for idx, res in enumerate(results):
                        if isinstance(res, Exception):
                            self._logger.error(f"Error during background worker cycle #2 for task #{idx}: {res}", exc_info=res)

                new_state = {
                    Fields.PING: self._ping,
                    Fields.ADB: self._adb_connection_is_established,

                    Fields.BATTERY: self.battery_level,
                    Fields.STORAGE: self.free_disk_space,
                    Fields.USB: self.connected_usb_devices,
                    Fields.WIFI: self.wifi_networks,
                    Fields.APP_ACTIVE: self._neon_companion_app_is_active,
                    Fields.APP_API_STATUS: self._neon_companion_api_status,
                    Fields.APP_RTSP_STATUS: self.app_rtsp_status,
                    Fields.DEVICE_NAME: self._neon_companion_device_name,
                    Fields.FRAME_NAME: self._neon_companion_frame_name,
                    Fields.MODULE_SERIAL: self._neon_companion_module_serial,
                    Fields.RECORDING_INFO: self._recording_info,
                    Fields.RED_LIGHT_INDICATORS: self.red_light_indicators,
                    Fields.VIBRATOR_EVENTS: self.vibrator_events
                }

                if new_state != last_state and self.on_change:
                    self.on_change(self.ip_addr, new_state)
                    last_state = new_state
                else:
                    self._logger.debug(f"No state change for {self.ip_addr}: {new_state}")

                elapsed_s = (datetime.datetime.now() - cycle_start).total_seconds()
                await asyncio.sleep(max(2 - elapsed_s, 0.1))
            except asyncio.CancelledError:
                self._logger.info(f"Background worker cancelled for {self.ip_addr}")
                await asyncio.sleep(0.1)
                break
            except Exception as e:
                self._logger.error(f"Unexpected error in background worker: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def start(self):
        """
        Start background monitoring the device's state.
        """
        self._background_task = asyncio.create_task(self._background_worker_run())

    async def stop(self):
        """Stop the background monitoring task"""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

