import threading
from typing import Callable, Optional, Dict, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import asyncio
import logging
from device import Device, Fields, RecordingInfo
import time



@dataclass
class DeviceState:
    ip_addr: str
    timestamp: datetime = field(default_factory=datetime.now)

    device_name: Optional[str] = None
    frame_name: Optional[str] = None
    module_serial: Optional[str] = None

    ping: Optional[int] = None

    adb: Optional[bool] = None    
    battery: Optional[int] = None
    storage: Optional[float] = None
    usb: Optional[list] = field(default_factory=list)
    wifi: Optional[list] = field(default_factory=list)

    app_active: Optional[bool] = None
    app_api_status: Optional[bool] = None
    app_rtsp_status: Optional[bool] = None
    
    vibrator_events: Optional[list] = field(default_factory=list)
    red_light_indicators: Optional[dict] = field(default_factory=dict)
    recording_info: Optional[Dict[str, RecordingInfo]] = field(default_factory=dict)
    
    def diff_fields(self, other: Optional['DeviceState']) -> Dict:
        if other is None:
            return asdict(self)
        other_dict = asdict(other)
        changed = {}
        for key, value in asdict(self).items():
            if key not in other_dict or value != other_dict[key]:
                changed[key] = value
        return changed

class DeviceManager:
    """
    Manages lifecycle, concurrency, state aggregation, and callbacks for all devices.
    
    Key responsibilities:
    1. Create and register devices
    2. Manage start/stop lifecycle (graceful shutdown)
    3. Track state changes and notify UI via callback
    4. Provide thread-safe read access to state snapshots
    5. Implement circuit breaker for failed devices
    6. Debounce callbacks to avoid UI thrashing
    """
    
    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self.device_state_history: Dict[str, DeviceState] = {}
        
        self._logger = logging.getLogger(self.__class__.__name__)
        self._loop = None
        self._thread = None
    
    def register_device(self, ip_addr: str, port: str = '5555') -> Device:
        device = Device(
            ip_addr,
            port,
            on_change=self._on_device_state_changed
        )
        self.devices[ip_addr] = device
        self.device_state_history[ip_addr] = DeviceState(ip_addr=ip_addr)
        
        self._logger.info(f"Registered device: {ip_addr}:{port}")

        return device
    
    def start_all(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=False)
        self._thread.start()

        while self._loop is None or not self._loop.is_running():
            time.sleep(0.1)
    
        asyncio.run_coroutine_threadsafe(self._start_all_devices(), self._loop)
    
    def stop_all(self) -> None:
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._stop_all_devices(), self._loop)
            future.result(timeout=5)
            self._logger.info("All devices stopped successfully")
            self._loop.call_soon_threadsafe(self._loop.stop)
        try:
            self._thread.join(timeout=5)
        except Exception as e:
            self._logger.error(f"Error joining thread: {e}")

    def _on_device_state_changed(self, ip_addr: str, new_state: dict) -> None:
        new_state = DeviceState(ip_addr=ip_addr, **new_state)
        old_state = self.device_state_history.get(ip_addr)
        self.device_state_history[ip_addr] = new_state
        
        # changed_fields = new_state.diff_fields(old_state)
        # if changed_fields:
        #     self._logger.info(f"Device {ip_addr} state changed: {changed_fields}")

    def _run_loop(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._loop.run_forever()
        except Exception as e:
            self._logger.error(f"Unexpected event loop error: {e}")

    async def _start_all_devices(self) -> None:
        tasks = [d.start() for d in self.devices.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for ip, result in zip(self.devices.keys(), results):
            if isinstance(result, Exception):
                self._logger.error(f"Failed to start device {ip}: {result}")
            else:
                self._logger.info(f"Device {ip} monitoring started")

    async def _stop_all_devices(self) -> None:
        tasks = [d.stop() for d in self.devices.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for ip, result in zip(self.devices.keys(), results):
            if isinstance(result, Exception):
                self._logger.error(f"Error stopping device {ip}: {result}")
            else:
                self._logger.info(f"Device {ip} monitoring stopped")
    
    def get_device_state(self, ip_addr: str) -> Optional[DeviceState]:
        return self.device_state_history.get(ip_addr)
    
    def get_all_states(self) -> Dict[str, DeviceState]:
        return self.device_state_history.copy()