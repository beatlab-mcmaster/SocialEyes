from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..monitoring.device import DeviceState
from .formatting.text import format_date, short_recording_id


class DeviceStateField(str, Enum):
    IP = 'ip'
    PING = 'ping'
    ADB = 'adb'
    BATTERY = 'battery'
    STORAGE = 'storage'
    USB = 'usb'
    WIFI = 'wifi'

    APP_ACTIVE = 'app_active'
    APP_API_STATUS = 'app_api_status'
    RECORDING_INFO = 'recording_info'

    DEVICE_NAME = 'device_name'
    FRAME_NAME = 'frame_name'
    MODULE_SERIAL = 'module_serial'

    VIBRATOR_EVENTS = 'vibrator_events'
    RED_LIGHT_INDICATORS = 'red_light_indicators'

    PL_REC = 'PL_Rec'
    LAST_UPDATED = 'last_updated'

def format_recording_status(active_recordings: dict | None) -> str:
    if not active_recordings:
        return ''
    by_start_time = dict(sorted(active_recordings.items(), key=lambda x: x[1].started_at or datetime.min, reverse=True))
    return ', '.join(f"{short_recording_id(rid)} since {format_date(r.started_at)} ({r.state.name})" for rid, r in by_start_time.items())

class DeviceStateSnapshot:
    """
    Represents a snapshot of the :class:`~glassesRecord.neon.device.DeviceState` containing
    only the values relevant for the TUI.
    Provides methods to compare snapshots and retrieve :class:`~glassesRecord.device_state.DeviceStateField` values.
    """

    def __init__(self, state: DeviceState | None):
        self._data: dict[DeviceStateField, Any] = {}
        if state is not None:
            self._data[DeviceStateField.IP] = state.ip_addr
            self._data[DeviceStateField.PING] = state.ping
            self._data[DeviceStateField.ADB] = state.adb_connection_is_established
            self._data[DeviceStateField.BATTERY] = state.latest_statistics.phone.battery_level if state.latest_statistics else None
            self._data[DeviceStateField.STORAGE] = state.latest_statistics.phone.storage.free_gb if state.latest_statistics else None
            self._data[DeviceStateField.USB] = any("Neon" in d.product_name if d.product_name else False for d in state.latest_statistics.phone.usb_devices) if state.latest_statistics else None
            self._data[DeviceStateField.WIFI] = state.latest_statistics.phone.wifi.ssid if state.latest_statistics else None
            self._data[DeviceStateField.APP_ACTIVE] = state.latest_statistics.neon.is_active if state.latest_statistics else None
            self._data[DeviceStateField.APP_API_STATUS] = state.neon_api_is_available
            self._data[DeviceStateField.DEVICE_NAME] = state.neon_hardware_ids.device_name if state.neon_hardware_ids else None
            self._data[DeviceStateField.FRAME_NAME] = state.neon_hardware_ids.frame_name if state.neon_hardware_ids else None
            self._data[DeviceStateField.MODULE_SERIAL] = state.neon_hardware_ids.module_serial if state.neon_hardware_ids else None
            self._data[DeviceStateField.RECORDING_INFO] = state.active_recordings
            self._data[DeviceStateField.RED_LIGHT_INDICATORS] = any(ri.red_light_indicator_detected for ri in state.active_recordings.values()) if state.active_recordings else None
            self._data[DeviceStateField.PL_REC] = format_recording_status(state.active_recordings)
            self._data[DeviceStateField.LAST_UPDATED] = state.latest_statistics.created_at if state.latest_statistics else state.now
        else:
            for field in DeviceStateField:
                self._data[field] = None

    def get_changed_fields(self, old: Optional['DeviceStateSnapshot']) -> dict[DeviceStateField, Any]:
        """
        Compares the current snapshot with an old snapshot and returns a dictionary of fields that have changed.
        
        Returns
        -------
        Dict[DeviceStateField, Any]
            A dictionary where keys are the fields that have changed and values are the new values. Returns all fields if the `old` is None.
        """
        changed_fields = {}
        if old is None:
            changed_fields = dict(self._data)
        else:
            for key in self._data.keys():
                if self._data[key] != old._data.get(key):
                    changed_fields[key] = self._data[key]
        return changed_fields

    def get(self, field: DeviceStateField) -> Any:
        return self._data.get(field)
