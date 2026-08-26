import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .device_state import DeviceState, DeviceStateField, DeviceStateSnapshot
from .formatting.rich_text import as_colored_text
from .formatting.text import time_ago

_FORMATTERS: dict[DeviceStateField, Callable[[Any], Any]] = {
    DeviceStateField.PING: lambda v: as_colored_text(v, thresh_low=200, thresh_high=500, reverse=True),
    DeviceStateField.ADB: as_colored_text,
    DeviceStateField.APP_ACTIVE: as_colored_text,
    DeviceStateField.APP_API_STATUS: as_colored_text,
    DeviceStateField.DEVICE_NAME: lambda v: v,  # plain text, no formatting
    DeviceStateField.USB: as_colored_text,
    DeviceStateField.FRAME_NAME: as_colored_text,
    DeviceStateField.PL_REC: as_colored_text,
    DeviceStateField.RED_LIGHT_INDICATORS: lambda v: as_colored_text(v, reverse=True),
    DeviceStateField.BATTERY: lambda v: as_colored_text(v, thresh_low=25, thresh_high=50),
    DeviceStateField.STORAGE: lambda v: as_colored_text(v, thresh_low=25, thresh_high=50),
    DeviceStateField.PHONE_LOCKED: as_colored_text,
    DeviceStateField.APP_VERSION: lambda v: v,  # plain text, no formatting
}

class DeviceTablePresenter:

    _logger: logging.Logger = logging.getLogger(__name__)

    _current_snapshots: dict[str, DeviceStateSnapshot]
    _time_ago_threshold: dict[str | None, float]

    def __init__(self):
        self._current_snapshots: dict[str, DeviceStateSnapshot] = {}
        self._time_ago_threshold = {None: 1}

    def time_ago_threshold(self, threshold_seconds: float, ip_addrs: list[str] | None = None) -> None:
        if ip_addrs is None:
            self._time_ago_threshold[None] = threshold_seconds
        else:
            for ip_addr in ip_addrs:
                self._time_ago_threshold[ip_addr] = threshold_seconds

    def diff_updates(self, states: dict[str, DeviceState]) -> list[tuple[str, DeviceStateField, Any]]:
        """
        Compares the current `DeviceState`s with the previously rendered states and identifies any changes.
        
        Returns
        -------
        list[tuple[str, DeviceStateField, Any]]
            A list of tuples containing the IP address, the field that changed, and the new value, formatted for display.
        """
        updates: list[tuple[str, DeviceStateField, Any]] = []

        now = datetime.now(timezone.utc)
        for ip_addr, state in states.items():
            old_snapshot = self._current_snapshots.get(ip_addr)
            new_snapshot = DeviceStateSnapshot(state)

            # "Last updated" always refreshes, even if no tracked field changed
            last_updated_val = as_colored_text(time_ago(now, new_snapshot.get(DeviceStateField.LAST_UPDATED), self._time_ago_threshold.get(ip_addr, self._time_ago_threshold[None])), thresh_low=5, thresh_high=30, reverse=True)
            updates.append((ip_addr, DeviceStateField.LAST_UPDATED, last_updated_val))

            # Other fields only update if they have changed since the last snapshot
            changed_fields = new_snapshot.get_changed_fields(old_snapshot)
            for field, raw_value in changed_fields.items():
                if field == DeviceStateField.LAST_UPDATED:
                    continue  # Already handled above
                formatter = _FORMATTERS.get(field)
                if formatter is not None:
                    updates.append((ip_addr, field, formatter(raw_value)))
                else:
                    self._logger.warning("No formatter defined for field: %s", field)
                    updates.append((ip_addr, field, raw_value))

            # Update the rendered state for the next comparison
            self._current_snapshots[ip_addr] = new_snapshot

        return updates
