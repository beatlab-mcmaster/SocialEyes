
import asyncio
import json
import logging
import os
from dataclasses import dataclass
import datetime

import anyio

from glassesRecord.tui.device_state import DeviceState


@dataclass
class LoggingDueConditions:
    never_logged: bool
    time_exceeded: bool
    ping_changed: bool
    adb_connection_changed: bool
    recording_state_changed: bool

    def is_due(self) -> bool:
        return self.never_logged or self.time_exceeded or self.ping_changed or self.adb_connection_changed or self.recording_state_changed

class DeviceStateLogger:
    """
    Logs the state of devices at regular intervals.
    """

    _file_lock = asyncio.Lock()
    _logger: logging.Logger = logging.getLogger("DeviceStateLogger")

    def __init__(self, snapshot_dir: str, snapshot_interval_s: float):
        assert os.path.exists(snapshot_dir), f"Snapshot directory {snapshot_dir} does not exist"
        self._snapshot_dir = snapshot_dir
        self._snapshot_interval_s = snapshot_interval_s

        self._snapshot_file = os.path.join(self._snapshot_dir, "device_state_snapshots.jsonl")
        self._last_snapshot_time: dict[str, float] = {} # Key: ip_addr, Value: timestamp of last snapshot written for that device
        self._last_snapshot: dict[str, DeviceState] = {}
        
    async def log_if_due(self, state: DeviceState):
        """
        Writes a snapshot of the device states to a file if the snapshot interval has passed.
        """
        now = asyncio.get_event_loop().time()
        ip_addr = state.ip_addr
        due_conditions = self._determine_logging_due(state)
        if due_conditions.is_due():
            await self._log_state(state, due_conditions)
            self._last_snapshot_time[ip_addr] = now
            self._last_snapshot[ip_addr] = state

    async def _log_state(self, state: DeviceState, due_conditions: LoggingDueConditions):
        async with self._file_lock, await anyio.open_file(self._snapshot_file, "a") as f:
            log_line = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "due_conditions": {
                    "never_logged": due_conditions.never_logged,
                    "time_exceeded": due_conditions.time_exceeded,
                    "ping_changed": due_conditions.ping_changed,
                    "adb_connection_changed": due_conditions.adb_connection_changed,
                    "recording_state_changed": due_conditions.recording_state_changed,
                },
                "state": json.loads(state.model_dump_json())
            }
            await f.write(json.dumps(log_line) + "\n")

    def _determine_logging_due(self, state: DeviceState) -> LoggingDueConditions:
        """
        Checks if a snapshot is due for the given device state.
        """
        now = asyncio.get_event_loop().time()
        ip_addr = state.ip_addr
        old_state = self._last_snapshot.get(ip_addr)

        never_logged = ip_addr not in self._last_snapshot_time
        time_exceeded = (now - self._last_snapshot_time.get(ip_addr, 0)) >= self._snapshot_interval_s
        _ping_changed = ping_changed(old_state, state)
        _adb_connection_changed = adb_connection_changed(old_state, state)
        _recording_state_changed = recording_state_changed(old_state, state)

        return LoggingDueConditions(
            never_logged=never_logged,
            time_exceeded=time_exceeded,
            ping_changed=_ping_changed,
            adb_connection_changed=_adb_connection_changed,
            recording_state_changed=_recording_state_changed
        )

def adb_connection_changed(old_state: DeviceState | None, new_state: DeviceState) -> bool:
    adb_changed_from_none = old_state is not None and old_state.adb_connection_is_established is None and new_state.adb_connection_is_established is not None
    adb_changed_to_none = (old_state is not None and old_state.adb_connection_is_established is not None and new_state.adb_connection_is_established is None) or (old_state is None and new_state.adb_connection_is_established is None)
    return adb_changed_from_none or adb_changed_to_none

def ping_changed(old_state: DeviceState | None, new_state: DeviceState) -> bool:
    ping_changed_from_none = old_state is not None and old_state.ping is None and new_state.ping is not None
    ping_changed_to_none = (old_state is not None and old_state.ping is not None and new_state.ping is None) or (old_state is None and new_state.ping is None)
    return ping_changed_from_none or ping_changed_to_none

def recording_state_changed(old_state: DeviceState | None, new_state: DeviceState) -> bool:
    """
    Checks if the recording info has changed since the last snapshot.
    """
    old_state_active_recordings = old_state.active_recordings if old_state is not None and old_state.active_recordings is not None else {}
    new_state_active_recordings = new_state.active_recordings if new_state is not None and new_state.active_recordings is not None else {}
    old_state_states = [ri.state for ri in old_state_active_recordings.values()]
    new_state_states = [ri.state for ri in new_state_active_recordings.values()]
    return old_state_states != new_state_states # If the *recording* states have changed, we consider the recording info to have changed.