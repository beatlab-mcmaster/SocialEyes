"""
device.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: Implements the device class with Android Debug Bridge (ADB) utility functions to monitor the device.
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import datetime
import logging
import asyncio
from typing import Dict, Optional
from collections import deque
from collections.abc import Callable

from .scripts.statistics_schema import DeviceStatistics, Mp4File
from ..clients.adb import check_adb_connection, check_statistics_script_exists, push_statistics_script, fetch_socialeyes_statistics
from ..clients.neon import is_neon_api_accessible, get_neon_hardware_ids, check_red_light_flashing_indicators
from ..clients.ping import ping_device

REPO_STATISTICS_SCRIPT_PATH_STR = str((Path(__file__).parent / 'scripts' / 'statistics.sh').resolve())
PHONE_STATISTICS_SCRIPT_PATH_STR = '/storage/self/primary/Documents/SocialEyes/statistics.sh'

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
    neon_hardware_ids: Optional[NeonHardwareIDs] = None
    active_recordings: Optional[Dict[str, RecordingInfo]] = None
    latest_statistics: Optional[DeviceStatistics] = None

class Device:

    _ip_addr: str
    _port: int
    _on_change: Optional[Callable[[Optional[DeviceState]], None]] = None
    _target_cycle_period_s: float = 2

    # Internal state
    _background_task: Optional[asyncio.Task] = None
    _statistics_script_pushed: bool = False
    _statistics_history: deque[DeviceStatistics] = deque(maxlen=3)
    _state_history: deque[DeviceState] = deque(maxlen=3)
    _active_recordings: Optional[Dict[str, RecordingInfo]] = None

    @property
    def target_cycle_period_s(self) -> float:
        return self._target_cycle_period_s

    @target_cycle_period_s.setter
    def target_cycle_period_s(self, value: float):
        """Set the target cycle period in seconds. The value must be at least 1 second."""
        self._target_cycle_period_s = max(1, value)

    @property
    def latest_state(self) -> Optional[DeviceState]:
        """Return the latest device state (including the latest statistics) or None if no state has been recorded yet."""
        return self._state_history[-1] if self._state_history else None

    @property
    def previous_state(self) -> Optional[DeviceState]:
        return self._state_history[-2] if len(self._state_history) > 1 else None

    @property
    def _latest_statistics(self) -> Optional[DeviceStatistics]:
        return self._statistics_history[-1] if self._statistics_history else None

    @property
    def _previous_statistics(self) -> Optional[DeviceStatistics]:
        return self._statistics_history[-2] if len(self._statistics_history) > 1 else None

    @property
    def active_recordings(self) -> Optional[Dict[str, RecordingInfo]]:
        """Return the latest active recordings (i.e., recording directories that contain a temp_*.json) or None if no statistics have been collected yet."""
        return self._active_recordings

    def __init__(self, 
                 ip_addr: str, 
                 port: int = 5555,
                 on_change: Optional[Callable[[Optional[DeviceState]], None]] = None
    ):
        self._ip_addr = ip_addr
        self._port = port
        self._on_change = on_change

        self._logger = logging.getLogger(f"Device-{self._ip_addr}:{self._port}")

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

                self._ping = await self._determine_ping()
                self._adb_connection_is_established = await self._determine_adb_connection_is_established()
            
                self._neon_api_is_available = await self._determine_neon_api_is_available()
                self._neon_hardware_ids = await self._determine_neon_hardware_ids()

                if not self._statistics_script_pushed and self._ping is not None and self._adb_connection_is_established: 
                    if await self._push_statistics_script():
                        self._statistics_script_pushed = True
                    else:
                        self._logger.error(f"Failed to push statistics.sh script to device {self._ip_addr}.")

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
        response = await check_statistics_script_exists(self._ip_addr, script_path=PHONE_STATISTICS_SCRIPT_PATH_STR, port=self._port)
        return response.result if response.result is not None else False

    async def _push_statistics_script(self) -> bool:
        response = await push_statistics_script(self._ip_addr, source_path=REPO_STATISTICS_SCRIPT_PATH_STR, dest_path=PHONE_STATISTICS_SCRIPT_PATH_STR, port=self._port)
        return response.result if response.result is not None else False

    async def _fetch_statistics(self) -> Optional[DeviceStatistics]:
        response = await fetch_socialeyes_statistics(self._ip_addr, self._port)
        return response.result

    async def _determine_ping(self) -> Optional[int]:
        ping_response = await ping_device(self._ip_addr)
        return ping_response.result

    async def _determine_adb_connection_is_established(self) -> Optional[bool]:
        response = await check_adb_connection(self._ip_addr, self._port)
        return response.result

    async def _determine_neon_api_is_available(self) -> Optional[bool]:
        response = await is_neon_api_accessible(self._ip_addr)
        return response.result

    async def _determine_neon_hardware_ids(self) -> Optional[NeonHardwareIDs]:
        response = await get_neon_hardware_ids(self._ip_addr)
        return NeonHardwareIDs(
            device_name=response.device_name,
            device_id=response.device_id,
            frame_name=response.frame_name,
            module_serial=response.module_serial
        )

    async def _determine_red_light_indicators_detected(self, workspace_id: str, recording_id: str) -> Optional[bool]:
        response = await check_red_light_flashing_indicators(self._ip_addr, self._port, workspace_id, recording_id)
        return response.result

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
