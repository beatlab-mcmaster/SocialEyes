"""
device.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: Implements the device class with Android Debug Bridge (ADB) utility functions to monitor the device.
"""
from dataclasses import dataclass, field
from enum import Enum
import os
import re
import numpy as np
import datetime
import json
import numpy as np
import logging
from adb_utils import cmd_wrapper, get_output, get_http, verify_path_or_command
import asyncio
from typing import Dict, Optional
from collections import deque
from scripts.statistics_schema import DeviceStatistics, Mp4File
from collections.abc import Callable


@dataclass
class NeonHardwareIDs:
    device_name: Optional[str] = None
    device_id: Optional[str] = None
    frame_name: Optional[str] = None
    module_serial: Optional[str] = None

class RecordingState(Enum):
    UNKNOWN = 0,
    IDLE = 1,
    RECORDING_IN_PROGRESS = 2,
    RECORDING_HAS_NO_MP4 = 3,
    RECORDING_UNSAVED_OR_FAILED = 4,

@dataclass
class RecordingInfo:
    workspace_id: str
    recording_id: str
    state: RecordingState
    started_at: Optional[datetime.datetime] = None
    duration: Optional[float] = None
    details: Optional[Dict[str, Mp4File]] = None
    red_light_indicator_detected: Optional[bool] = None

@dataclass
class DeviceState:
    ip_addr: str
    now: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    ping: Optional[int] = None
    adb_connection_is_established: Optional[bool] = None
    neon_api_is_available: Optional[bool] = None
    neon_rtsp_is_available: Optional[bool] = None
    neon_hardware_ids: Optional[NeonHardwareIDs] = None
    active_recordings: Optional[Dict[str, RecordingInfo]] = None
    latest_statistics: Optional[DeviceStatistics] = None

class Device:

    _subprocess_timeout_s: int
    _adb_path: str
    _target_cycle_period_s: int = 4

    # Internal state
    _background_task: Optional[asyncio.Task] = None
    _statistics_script_pushed: bool = False
    _statistics_history: deque[DeviceStatistics] = deque(maxlen=10)
    _state_history: deque[DeviceState] = deque(maxlen=10)
    _active_recordings: Optional[Dict[str, RecordingInfo]] = None

    PING_PATTERN_WINDOWS = re.compile(r'time=([0-9.]+)ms TTL=\d+')
    PING_PATTERN = re.compile(r'ttl=\d+\s+time=([0-9.]+)\s+ms')

    @property
    def _latest_statistics(self) -> Optional[DeviceStatistics]:
        return self._statistics_history[-1] if self._statistics_history else None

    @property
    def _previous_statistics(self) -> Optional[DeviceStatistics]:
        return self._statistics_history[-2] if len(self._statistics_history) > 1 else None

    @property
    def latest_state(self) -> Optional[DeviceState]:
        return self._state_history[-1] if self._state_history else None

    @property
    def previous_state(self) -> Optional[DeviceState]:
        return self._state_history[-2] if len(self._state_history) > 1 else None

    @property
    def active_recordings(self) -> Optional[Dict[str, RecordingInfo]]:
        return self._active_recordings

    def __init__(self, 
                 ip_addr: str, 
                 port: int = 5555,
                 on_change: Optional[Callable[[Optional[DeviceState]], None]] = None,
                 subprocess_timeout_s: int = 5,
                 adb_path: str = os.environ.get('ADB_PATH', 'adb')
    ):
        self._ip_addr = ip_addr
        self._port = port
        self._on_change = on_change
        self._subprocess_timeout_s = subprocess_timeout_s
        self._adb_path = adb_path
        self._logger = logging.getLogger(f"Device-{self._ip_addr}:{self._port}")

        if not verify_path_or_command(self._adb_path):
            raise RuntimeError(f"ADB path '{self._adb_path}' is not valid. Please check your ADB installation.")

    async def start(self):
        self._background_task = asyncio.create_task(self._background_worker_run())

    async def stop(self):
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

    async def _background_worker_run(self):
        while True:
            try:
                current_cycle_start = datetime.datetime.now()

                # Host-to-device ping and ADB connection check
                self._ping = await self._determine_ping()
                self._adb_connection_is_established = await self._determine_adb_connection_is_established()

            
                self._neon_api_is_available = await self._determine_neon_api_is_available()
                self._neon_rtsp_is_available = await self._determine_neon_rtsp_is_available()
                self._neon_hardware_ids = await self._determine_neon_hardware_ids()

                if not self._statistics_script_pushed and self._ping is not None and self._ping < 1000 and self._adb_connection_is_established: 
                    if not await self._check_statistics_script_exists():
                        if not await self._push_statistics_script():
                            self._logger.error(f"Failed to push statistics.sh script to device {self._ip_addr}.")
                    else:
                        self._statistics_script_pushed = True

                if self._statistics_script_pushed:
                    statistics = await self._fetch_statistics()
                    if statistics is not None:
                        self._statistics_history.append(statistics)
                    self._active_recordings = await self._determine_active_recordings()

                # Update latest state
                current_state = DeviceState(
                    ip_addr=self._ip_addr,
                    ping=self._ping,
                    adb_connection_is_established=self._adb_connection_is_established,
                    latest_statistics=self._latest_statistics,
                    neon_api_is_available=self._neon_api_is_available,
                    neon_rtsp_is_available=self._neon_rtsp_is_available,
                    neon_hardware_ids=self._neon_hardware_ids,
                    active_recordings=self._active_recordings,
                )
                self._state_history.append(current_state)

                # Notify observer if there are changes in the device statistics
                await self._notify_observer()

                # Sleep to maintain the target cycle period
                elapsed_seconds = (datetime.datetime.now() - current_cycle_start).total_seconds()
                if elapsed_seconds < self._target_cycle_period_s:
                    await asyncio.sleep(self._target_cycle_period_s - elapsed_seconds)
            except asyncio.CancelledError:
                self._logger.info(f"Background worker cancelled for {self._ip_addr}")
                await asyncio.sleep(0.1)
                break
            except Exception as e:
                self._logger.error(f"Unexpected error in background worker: {e}", exc_info=e)
                await asyncio.sleep(5) # Wait 5 seconds before retrying the next cycle

    async def _check_statistics_script_exists(self) -> bool:
        rc, _ , _ = await get_output(f'{self._adb_path} -s {self._ip_addr}:{self._port} shell ls /storage/self/primary/Documents/SocialEyes/statistics.sh')
        if rc != 0:
            return False
        return True

    async def _push_statistics_script(self) -> bool:
        stats_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'scripts/statistics.sh')) # TODO make constant
        rc, _ , err = await get_output(f'{self._adb_path} -s {self._ip_addr}:{self._port} push {stats_script_path} /storage/self/primary/Documents/SocialEyes/statistics.sh')
        if rc != 0:
            return False
        return True

    async def _call_statistics_script(self) -> Optional[str]:
        rc, res, err = await get_output(f'{self._adb_path} -s {self._ip_addr}:{self._port} shell sh /storage/self/primary/Documents/SocialEyes/statistics.sh')
        if rc == 0:
            return res
        else:
            self._logger.error(f'Failed to execute statistics.sh script: rc={rc}, res={res}, err={err}')
            return None

    async def _fetch_statistics(self) -> Optional[DeviceStatistics]:
        result = None
        r = await self._call_statistics_script()
        if r is not None:
            try:
                result = DeviceStatistics.model_validate_json(r)
            except json.JSONDecodeError as e:
                self._logger.error(f'Failed to decode statistics JSON: {e}')
        return result

    async def _determine_ping(self) -> Optional[int]:
        """
        Uses the `ping` command to send requests and record the time taken.
        Updates the `_ping` attribute with the average time in milliseconds or sets it to None if there is no response.
        """
        ping = None

        is_windows = os.name == 'nt'
        ping_command = f'ping /n 1 {self._ip_addr}' if is_windows else f'ping -c 1 {self._ip_addr}'
        ping_pattern = self.PING_PATTERN_WINDOWS if is_windows else self.PING_PATTERN

        async with cmd_wrapper(ping_command, ignore_rc=True, timeout=self._subprocess_timeout_s) as (res,rc):
            if rc == 0:
                if res is not None and len(res) > 0:
                    re_search = ping_pattern.findall(res)
                    if re_search is not None and len(re_search) > 0:
                        times = [float(e) for e in re_search]
                        ping = int(np.average(times))
                    else:
                        self._logger.error(f'Ping command executed but no valid time found in output: {res}')
        return ping

    async def _determine_adb_connection_is_established(self) -> Optional[bool]:
        """
        Checks if the host computer can connect to the device via ADB.
        Uses the ADB command to list connected devices and updates the `_adb_connection_is_established` attribute.

        """
        connection_established = None
        async with cmd_wrapper(f'{self._adb_path} devices', ignore_rc=True) as (res,_):
            connection_established = False
            if res is not None and len(res) > 0:
                lines = res.splitlines()
                connection_established = any(self._ip_addr in line and 'device' in line for line in lines)
        return connection_established

    async def _determine_neon_api_is_available(self) -> Optional[bool]:
        """
        Sends a GET request to the API to check status and updates the `_neon_companion_api_status` attribute based on the response.

        Logs changes in the API status.
        """
        neon_api_is_available = None

        status_code, _ = await get_http(f'http://{self._ip_addr}:8080/api/status', timeout=self._subprocess_timeout_s)
        neon_api_is_available = status_code == 200

        return neon_api_is_available

    async def _determine_neon_rtsp_is_available(self) -> Optional[bool]:
        """
        Attempts to connect to the RTSP server and checks the response to determine its status.
        Updates the `_neon_companion_rtsp_server_status` attribute accordingly.
        """
        rtsp_status = None
        
        try:
            reader, writer = await asyncio.open_connection(self._ip_addr, 8086)

            writer.write('DESCRIBE / RTSP/1.0\r\nCSeq:1\r\n\r\n'.encode('ascii'))
            await writer.drain()
            s_res = (await reader.read(4096)).decode('ascii')

            rtsp_status = 'RTSP/1.0 200 OK' in s_res
        except:
            rtsp_status = False

        return rtsp_status

    async def _determine_neon_hardware_ids(self) -> Optional[NeonHardwareIDs]:
        """
        Makes an API call to the Neon service to retrieve device and module
        information. Updates internal state with new identifiers and logs any changes.
        """
        device_name = None
        device_id = None
        frame_name = None
        module_serial = None

        status_code, res = await get_http(f'http://{self._ip_addr}:8080/api/status', timeout=self._subprocess_timeout_s)

        res_json = json.loads(res) if res is not None and status_code == 200 else {}
        if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
            for e in res_json['result']:
                e_model = e['model']
                e_data  = e['data']
                if e_model == 'Phone':
                    device_name = str(e_data['device_name'])
                    device_id = str(e_data['device_id'])
                elif e_model == 'Hardware':
                    frame_name = str(e_data['frame_name'])
                    module_serial = str(e_data['module_serial'])

        return NeonHardwareIDs(
            device_name=device_name,
            device_id=device_id,
            frame_name=frame_name,
            module_serial=module_serial
        )

    async def _determine_red_light_indicators_detected(self, workspace_id: str, recording_id: str) -> Optional[bool]:
        """
        Checks the log files associated with active recordings to find
        instances of flashing red light indicators, logging any changes
        in the indicators found.
        """
        indicator_detected = None
            
        _, res, _ = await get_output(
            f'{self._adb_path} -s {self._ip_addr}:{self._port} shell grep -e "raw has not changed" /storage/self/primary/Documents/Neon/{workspace_id}/{recording_id}/android.log'
        )
        if res is not None and len(res) > 0:
            for line in res.splitlines():
                re_search = re.search(fr'(\d+-\d+ \d+:\d+:\d+.\d+).+({recording_id}.+)raw has not changed.+last size: (\d+)', line)
                if re_search is not None:
                    indicator_detected = True
                    break

        return indicator_detected

    async def _determine_active_recordings(self) -> Optional[Dict[str, RecordingInfo]]:
        result = None
        if self._latest_statistics is not None and self._latest_statistics.neon.recordings is not None:
            result = {}
            for rec in self._latest_statistics.neon.recordings:
                rec_id = rec.recording_id

                # duration
                earliest_mp4_creation_time = min([mp4.creation_time for mp4 in rec.mp4_files])
                duration = round((max([mp4.modification_time for mp4 in rec.mp4_files]) - earliest_mp4_creation_time).total_seconds())

                # recording state
                old_recording_info = self._active_recordings[rec_id] if self._active_recordings is not None and rec_id in self._active_recordings else None
                state = None
                if old_recording_info is None:
                    # = first time we see this recording, we don't know if it's still recording or not
                    state = RecordingState.UNKNOWN
                else:
                    if len(rec.mp4_files) == 0:
                        state = RecordingState.RECORDING_HAS_NO_MP4
                    else:
                        any_size_increased = False
                        for mp4 in rec.mp4_files:
                            if old_recording_info.details is not None:
                                old_mp4_file_obj = old_recording_info.details.get(mp4.file_name)
                                if old_mp4_file_obj is not None and mp4.file_size_bytes > old_mp4_file_obj.file_size_bytes:
                                    any_size_increased = True
                                    break
                        if any_size_increased:
                            state = RecordingState.RECORDING_IN_PROGRESS
                        else:
                            state = RecordingState.RECORDING_UNSAVED_OR_FAILED

                # red light indicator detection
                if old_recording_info is not None and old_recording_info.red_light_indicator_detected is not None:
                    red_light_indicator_detected = old_recording_info.red_light_indicator_detected
                else:
                    red_light_indicator_detected = await self._determine_red_light_indicators_detected(rec.workspace_id, rec_id)
                
                result[rec_id] = RecordingInfo(
                    workspace_id=rec.workspace_id,
                    recording_id=rec_id,
                    started_at=earliest_mp4_creation_time,
                    duration=duration,
                    state=state,
                    details={mp4.file_name: mp4 for mp4 in rec.mp4_files} if rec.mp4_files else None,
                    red_light_indicator_detected=red_light_indicator_detected
                )
        return result

    async def _notify_observer(self):
        if self._on_change is not None:
            if self.latest_state != self.previous_state:
                self._on_change(self.latest_state)

    async def lock_display(self):
        """
        Locks the device display using ADB command.
        """
        if self._adb_connection_is_established and self._latest_statistics and self._latest_statistics.phone.display.is_on:
            await get_output(f'{self._adb_path} -s {self._ip_addr}:{self._port} shell input keyevent 26')