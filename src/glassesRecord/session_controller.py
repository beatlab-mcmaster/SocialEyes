import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime

from .clients.adb import connect_adb
from .clients.core import SimpleClientResponse
from .clients.neon_adb import start_neon_companion_app, stop_neon_companion_app
from .clients.neon_http import (
    cancel_neon_recording,
    start_neon_recording,
    stop_and_save_neon_recording,
)
from .monitoring.device import DeviceState
from .monitoring.device_manager import DeviceConfig, DeviceManager
from .monitoring.offset_logger import OffsetLogger


@dataclass
class SessionControllerConfig:
    log_level: str # INFO, DEBUG, ...

    session_id: str
    session_dir: str
    is_single_session_mode: bool
    device_ips: list[str]
    offset_logger_interval: int

class SessionController:

    OFFSET_LOGGER_ALL_KEY = "all"  # Key for the offset logger when in single session mode

    _logger: logging.Logger

    _config: SessionControllerConfig

    _events_file: str

    _device_manager: DeviceManager

    _offset_loggers: dict[str, OffsetLogger] # key: device_ip (e.g., "192.168.2.101") or `OFFSET_LOGGER_ALL_KEY`
    _offset_logger_interval: int

    _is_restart_app_in_progress: bool = False

    @property
    def session_id(self) -> str:
        """Returns the unique identifier for the current session."""
        return self._config.session_id

    @property
    def session_dir(self) -> str:
        """Returns the directory path where session-related files are stored."""
        return self._config.session_dir

    @property
    def device_ip_addrs(self) -> list[str]:
        """Returns the list of device IP addresses being monitored."""
        return [d.ip_addr for d in self._device_manager.devices]

    @property
    def is_restart_app_in_progress(self) -> bool:
        return self._is_restart_app_in_progress

    def __init__(self, 
                 config: SessionControllerConfig):
        logging.basicConfig(
            filename=os.path.join(config.session_dir, 'logs.txt'),
            encoding='utf-8',
            level=config.log_level, # change to DEBUG if required
            format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s'
        )
        self._logger = logging.getLogger(__name__)
        self._config = config

        assert os.path.exists(self._config.session_dir), f"Session directory does not exist: {config.session_dir}"
        self._events_file = os.path.join(self._config.session_dir, "events.json")

        self._device_manager = DeviceManager()
        for ip_addr in self._config.device_ips:
            self._device_manager.register_device(str(ip_addr))

        self._offset_logger_interval = self._config.offset_logger_interval
        self._offset_loggers = {}

        self._logger.info(f"SessionController initialized with \n"
                          f"  session ID: {self.session_id}, \n"
                          f"  session directory: {self.session_dir}, \n"
                          f"  devices: {self.device_ip_addrs}, \n"
                          f"  single session mode: {self._config.is_single_session_mode}, \n"
                          f"  offset logger interval: {self._offset_logger_interval} seconds")

    # -------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------

    async def start_device_monitoring(self, monitoring_interval: int | None = None):
        """Start monitoring all registered devices. If `monitoring_interval` is provided, set it for all devices."""
        if monitoring_interval is not None:
            for dev in self.device_ip_addrs:
                self._device_manager.set_monitoring_interval(dev, monitoring_interval)
        await self._device_manager.start_all()

    async def stop_device_monitoring(self):
        await self._device_manager.stop_all()
    
    def get_all_device_states(self) -> dict[str, DeviceState]:
        return self._device_manager.get_all_device_states()

    # -------------------------------------------------------
    # Actions
    # -------------------------------------------------------

    async def start_recording(self, device_ips: list[str] = []) -> None:
        """
        Start offset logging and recording on the specified devices.
        
        Parameters
        ----------
        device_ips : list[str], optional
            List of device IP addresses to start recording on. If empty, recording will be started on all devices.
        """
        # Start offset logging
        if self._config.is_single_session_mode:
            # One offset logger for all devices
            if not self._offset_loggers.get(SessionController.OFFSET_LOGGER_ALL_KEY):
                ol = OffsetLogger(device_ips, log_dir=self._config.session_dir, log_interval=self._offset_logger_interval)
                self._logger.info(f"Starting Offset logger at {ol.log_file}")
                ol.start_logging()
                self._offset_loggers[SessionController.OFFSET_LOGGER_ALL_KEY] = ol
        else:
            # Separate offset logger for each device
            for dev in device_ips:
                if not self._offset_loggers.get(dev):
                    ol = OffsetLogger([dev], log_dir=os.path.join(self._config.session_dir, str(dev)), log_interval=self._offset_logger_interval)
                    self._logger.info(f"Starting Offset logger at {ol.log_file} for device: {dev}")
                    ol.start_logging()
                    self._offset_loggers[dev] = ol

        # Start recording
        if self._config.is_single_session_mode:
            if len(device_ips) != 0:
                self._logger.warning("In single session mode, device_ips parameter is ignored. Recording will be started on all registered devices.")
            device_ips = [d.ip_addr for d in self._device_manager.devices]
        
        t = [start_neon_recording(d) for d in device_ips]
        await asyncio.gather(*t, return_exceptions=True)

    async def stop_and_save_recording(self, device_ips: list[str] = []) -> None:
        """
        Stop offset logging and **save** recording on the specified devices.
        
        Parameters
        ----------
        device_ips : list[str], optional
            List of device IP addresses to stop recording on. If empty, recording will be stopped on all devices.
        """
        self._logger.info(f"Stopping recording on {len(device_ips)} device(s): {device_ips}")
        await self._stop_recording(device_ips, save=True)

    async def stop_and_discard_recording(self, device_ips: list[str] = []) -> None:
        """
        Stop offset logging and **discard** recording on the specified devices.
        
        Parameters
        ----------
        device_ips : list[str], optional
            List of device IP addresses to stop recording on. If empty, recording will be stopped on all devices.
        """
        self._logger.info(f"Discarding recording on {len(device_ips)} device(s): {device_ips}")
        await self._stop_recording(device_ips, save=False)

    async def restart_app_on_devices(self, device_ips: list[str] = []) -> None:
        """
        Restart Neon Companion App on the specified devices.
        If another restart is already in progress, this method will log a message and return without doing anything.
        
        Parameters
        ----------
        device_ips : list[str], optional
            List of device IP addresses to restart app on. If empty, app will be restart on all devices.
        """
        if self._is_restart_app_in_progress:
            self._logger.info('Another restart progress is already in progress, nothing to do...')
            return

        self._is_restart_app_in_progress = True
        devices = [d for d in self._device_manager.devices if d.ip_addr in device_ips]

        async def _do_restart_app(device: DeviceConfig):
            self._logger.info(f'Restarting app on {device.ip_addr}...')
            await stop_neon_companion_app(device.ip_addr, device.port)
            await start_neon_companion_app(device.ip_addr, device.port)
            self._logger.info(f'Restarting app on {device.ip_addr} has finished!')

        t = [_do_restart_app(d) for d in devices]
        await asyncio.gather(*t, return_exceptions=True)
        self._is_restart_app_in_progress = False

    async def reconnect_adb(self, device_ips: list[str] = []) -> None:
        """
        Re-establish the Android Debug Bridge (ADB) connection between the TUI's host computer and the specified devices.
        
        Parameters
        ----------
        device_ips : list[str], optional
            List of device IP addresses to reconnect ADB on. If empty, ADB will be reconnected on all devices.
        """
        tasks = [connect_adb(ip_addr) for ip_addr in device_ips]
        futures = await asyncio.gather(*tasks, return_exceptions=True)
        for ip_addr, future in zip(device_ips, futures):
            if isinstance(future, Exception):
                self._logger.info(f"Error reconnecting ADB for {ip_addr}: {future}")
            elif isinstance(future, SimpleClientResponse) and future.result is False:
                self._logger.info(f"Failed to reconnect ADB for {ip_addr}: {', '.join(future.error_messages)}")
            else:
                self._logger.info(f"Successfully reconnected ADB for {ip_addr}")

    def log_event(self, event_text: str) -> None:
        """
        Log an event to the events.json file in the session directory.
        Each event is a dictionary with a timestamp and the event text (i.e., {timestamp: <timestamp>, event: <event_text>}).
        
        Parameters
        ----------
        event_text : str
            The text of the event to log.
        """
        self._log_event(self._events_file, event_text)

    async def set_monitoring_interval(self, interval_seconds: float, device_ips: list[str] = []) -> None:
        """
        Set the monitoring interval for the specified devices.
        
        Parameters
        ----------
        interval_seconds : float
            The new monitoring interval in seconds.
        device_ips : list[str], optional
            List of device IP addresses to set the monitoring interval on. If empty, the interval will be set on all devices.
        """
        for dev in device_ips:
            self._device_manager.set_monitoring_interval(dev, interval_seconds)


    # -------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------
    
    def _log_event(self, events_file: str, event_text: str) -> None:
        try:
            with open(events_file, "r") as f:
                events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            events = []

        events.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_text
        })

        with open(events_file, "w") as f:
            json.dump(events, f, indent=2)

    async def _stop_recording(self, device_ips: list[str] = [], save: bool = True) -> None:
        """Stop recording on the specified devices."""

        # Stop offset logging
        if self._config.is_single_session_mode:
            if self._offset_loggers.get(SessionController.OFFSET_LOGGER_ALL_KEY):
                await self._offset_loggers[SessionController.OFFSET_LOGGER_ALL_KEY].stop_logging()
                del self._offset_loggers[SessionController.OFFSET_LOGGER_ALL_KEY]
                self._logger.info("Stopped offset logging for all devices.")
        else:
            for dev in device_ips:
                if self._offset_loggers.get(dev):
                    await self._offset_loggers[dev].stop_logging()
                    del self._offset_loggers[dev]
            self._logger.info(f"Stopped offset logging for devices: {device_ips}")

        # Stop recording
        if self._config.is_single_session_mode:
            if len(device_ips) != 0:
                self._logger.warning("In single session mode, device_ips parameter is ignored. Recording will be stopped on all registered devices.")
            device_ips = [d.ip_addr for d in self._device_manager.devices]
        if save:
            t = [stop_and_save_neon_recording(d) for d in device_ips]
        else:
            t = [cancel_neon_recording(d) for d in device_ips]
        await asyncio.gather(*t, return_exceptions=True)
