"""
device.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: Implements the device class with Android Debug Bridge (ADB) utility functions to monitor the device.
"""
import asyncio
import datetime
import logging
from collections import deque
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from glassesRecord.monitoring.recording_state import (
    RecordingInfo,
    determine_recording_state,
)

from .device_clients import DeviceClients
from .scripts.statistics_schema import DeviceStatistics

REPO_STATISTICS_SCRIPT_PATH_STR = str((Path(__file__).parent / 'scripts' / 'statistics.sh').resolve())
PHONE_STATISTICS_SCRIPT_PATH_STR = '/storage/self/primary/Documents/SocialEyes/statistics.sh'

class NeonHardwareIDs(BaseModel):
    device_name: str | None = None
    device_id: str | None = None
    frame_name: str | None = None
    module_serial: str | None = None

class DeviceState(BaseModel):
    ip_addr: str
    now: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    ping: int | None = None
    adb_connection_is_established: bool | None = None
    neon_api_is_available: bool | None = None
    neon_hardware_ids: NeonHardwareIDs | None = None
    active_recordings: dict[str, RecordingInfo] | None = None
    latest_statistics: DeviceStatistics | None = None

class Device:

    _ip_addr: str
    _port: int
    _on_change: Callable[[DeviceState], None] | None = None
    _monitoring_interval_s: float = 2

    # Internal state
    _background_task: asyncio.Task | None
    _background_task_interrupt_event: asyncio.Event
    _background_task_cancel_event: asyncio.Event
    _statistics_script_pushed: bool
    _statistics_history: deque[DeviceStatistics]
    _state_history: deque[DeviceState]
    _active_recordings: dict[str, RecordingInfo] | None

    @property
    def monitoring_interval_s(self) -> float:
        return self._monitoring_interval_s

    @monitoring_interval_s.setter
    def monitoring_interval_s(self, value: float):
        """Set the monitoring interval in seconds."""
        self._monitoring_interval_s = value
        self._background_task_interrupt_event.set() # Apply new interval immediately

    @property
    def latest_state(self) -> DeviceState | None:
        """Return the latest device state (including the latest statistics) or None if no state has been recorded yet."""
        return self._state_history[-1] if self._state_history else None

    @property
    def previous_state(self) -> DeviceState | None:
        return self._state_history[-2] if len(self._state_history) > 1 else None

    @property
    def _latest_statistics(self) -> DeviceStatistics | None:
        return self._statistics_history[-1] if self._statistics_history else None

    @property
    def active_recordings(self) -> dict[str, RecordingInfo] | None:
        """Return the latest active recordings (i.e., recording directories that contain a temp_*.json) or None if no statistics have been collected yet."""
        return self._active_recordings

    def __init__(self, 
                 ip_addr: str, 
                 port: int = 5555,
                 on_change: Callable[[DeviceState | None], None] | None = None,
                 clients: DeviceClients | None = None,
                 history_max_length: int = 3
    ):
        self._ip_addr = ip_addr
        self._port = port
        self._on_change = on_change
        self._clients = clients if clients is not None else DeviceClients()

        self._background_task = None
        self._background_task_interrupt_event = asyncio.Event()
        self._background_task_cancel_event = asyncio.Event()
        self._statistics_script_pushed = False
        self._statistics_history = deque(maxlen=history_max_length)
        self._state_history = deque(maxlen=history_max_length)
        self._active_recordings = None

        self._logger = logging.getLogger(f"Device-{self._ip_addr}:{self._port}")

    async def start(self):
        self._background_task_interrupt_event.clear()
        self._background_task = asyncio.create_task(self._background_worker_run())

    async def stop(self):
        if self._background_task:
            self._background_task_cancel_event.set()
            self._background_task_interrupt_event.set()
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

    # -------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------

    async def _background_worker_run(self):
        assert self._background_task is not None, "Background task should be initialized before running."
        while not self._background_task_cancel_event.is_set():
            try:
                current_cycle_start = asyncio.get_running_loop().time()

                try:
                    current_state = await asyncio.wait_for(self._poll_once(), timeout=self._monitoring_interval_s + 1)
                except asyncio.TimeoutError:
                    current_state = DeviceState(ip_addr=self._ip_addr)
                self._record_state(current_state)

                # Sleep to maintain the target cycle period
                elapsed_seconds = asyncio.get_running_loop().time() - current_cycle_start
                timeout = max(0, self._monitoring_interval_s - elapsed_seconds)
                try:
                    await asyncio.wait_for(self._background_task_interrupt_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass
                if self._background_task_interrupt_event.is_set():
                    self._background_task_interrupt_event.clear()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Unexpected error in background worker")

    async def _poll_once(self) -> DeviceState:
        await self._update_connectivity()
        await self._ensure_statistics_script()
        await self._update_statistics()
        return self._build_state()

    async def _update_connectivity(self) -> None:
        tasks = [
            self._determine_ping(),
            self._determine_adb_connection_is_established(),
            self._determine_neon_api_is_available()
        ]
        await asyncio.gather(*tasks)

    async def _ensure_statistics_script(self) -> None:
        if not self._statistics_script_pushed and self._ping is not None and self._adb_connection_is_established: 
            if await self._push_statistics_script():
                self._statistics_script_pushed = True
            else:
                self._logger.error(f"Failed to push statistics.sh script to device {self._ip_addr}.")

    async def _update_statistics(self) -> None:
        tasks = [
            self._determine_neon_hardware_ids(),
            self._fetch_statistics(),
            self._determine_active_recordings()
        ]
        await asyncio.gather(*tasks)

    def _build_state(self) -> DeviceState:
        return DeviceState(
            ip_addr=self._ip_addr,
            ping=self._ping,
            adb_connection_is_established=self._adb_connection_is_established,
            latest_statistics=self._latest_statistics,
            neon_api_is_available=self._neon_api_is_available,
            neon_hardware_ids=self._neon_hardware_ids,
            active_recordings=self._active_recordings,
        )

    def _record_state(self, state: DeviceState) -> None:
        previous_state = self.latest_state
        self._state_history.append(state)

        if self._on_change is not None and state != previous_state:
            self._on_change(state)

    async def _push_statistics_script(self) -> bool:
        response = await self._clients.push_statistics_script(self._ip_addr, REPO_STATISTICS_SCRIPT_PATH_STR, PHONE_STATISTICS_SCRIPT_PATH_STR, self._port)
        return response.result if response.result is not None else False

    async def _fetch_statistics(self) -> None:
        if self._statistics_script_pushed:
            response = await self._clients.fetch_socialeyes_statistics(self._ip_addr, self._port)
            statistics = response.result
            if statistics is not None:
                self._statistics_history.append(statistics)

    async def _determine_ping(self) -> None:
        ping_response = await self._clients.ping_device(self._ip_addr)
        self._ping = ping_response.result

    async def _determine_adb_connection_is_established(self) -> None:
        response = await self._clients.check_adb_connection(self._ip_addr, self._port)
        self._adb_connection_is_established = response.result

    async def _determine_neon_api_is_available(self) -> None:
        response = await self._clients.is_neon_api_accessible(self._ip_addr)
        self._neon_api_is_available = response.result

    async def _determine_neon_hardware_ids(self) -> None:
        response = await self._clients.get_neon_hardware_ids(self._ip_addr)
        self._neon_hardware_ids = NeonHardwareIDs(
            device_name=response.device_name,
            device_id=response.device_id,
            frame_name=response.frame_name,
            module_serial=response.module_serial
        )

    async def _determine_red_light_indicators_detected(self, workspace_id: str, recording_id: str) -> bool | None:
        response = await self._clients.check_red_light_flashing_indicators(self._ip_addr, self._port, workspace_id, recording_id)
        return response.result

    async def _determine_active_recordings(self) -> None:
        result = None
        if self._latest_statistics is not None and self._latest_statistics.neon.recordings is not None:
            result = {}
            for rec in self._latest_statistics.neon.recordings:
                rec_id = rec.recording_id

                # started_at & duration
                if not rec.mp4_files:
                    started_at = None
                    duration = None
                else:
                    started_at = min([mp4.creation_time for mp4 in rec.mp4_files])
                    duration = round(
                        (max([mp4.modification_time for mp4 in rec.mp4_files]) - started_at)
                        .total_seconds()
                    )

                # recording state
                old_recording_info = self._active_recordings[rec_id] if self._active_recordings is not None and rec_id in self._active_recordings else None
                state = determine_recording_state(neon_recording=rec, old_recording_info=old_recording_info)

                # red light indicator detection
                if old_recording_info is not None and old_recording_info.red_light_indicator_detected is not None:
                    red_light_indicator_detected = old_recording_info.red_light_indicator_detected
                else:
                    red_light_indicator_detected = await self._determine_red_light_indicators_detected(rec.workspace_id, rec_id)
                
                result[rec_id] = RecordingInfo(
                    workspace_id=rec.workspace_id,
                    recording_id=rec_id,
                    started_at=started_at,
                    duration=duration,
                    state=state,
                    details={mp4.file_name: mp4 for mp4 in rec.mp4_files} if rec.mp4_files else None,
                    red_light_indicator_detected=red_light_indicator_detected
                )
        self._active_recordings = result
