"""
OffsetLogger.py
Author: Areez Vizram, Alexander Nguyen, Shreshth Saxena
Purpose: Implemets the OffsetLogger class to log the time offset of each device to a log file
"""

import asyncio
import csv
import logging
import os
import time
from datetime import datetime, timezone

from ..clients.neon_time_echo import NeonTimeOffsetResponse, estimate_time_offset


class OffsetLogger:
    """This class logs the time offset for a list of devices (or just one) to a log file"""

    _logger: logging.Logger

    _log_file: str
    _log_interval: int
    _device_ips: list[str]
    _task: asyncio.Task | None

    @property
    def log_file(self) -> str:
        """Returns the path to the log file."""
        return self._log_file

    def __init__(self, device_ips: list[str], log_dir: str, log_interval: int = 10):
        """Initializes the OffsetLogger instance.

        Args:
            device_ips (List[str]): List of device IP addresses to log offsets for.
            log_dir (str, optional): Path to a custom log file. If not provided, a timestamped log file will be created.
            log_interval (int, optional): Time in seconds between logging offsets. Default is 10 seconds.
        """
        self._logger = logging.getLogger("OffsetLogger")

        os.makedirs(log_dir, exist_ok=True)

        self._log_file = os.path.join(log_dir, f"{datetime.now(timezone.utc).strftime('%y%m%dT%H%M%S')}_offsets.csv")
        self._log_interval = log_interval
        self._device_ips = device_ips

        self._stop_event = asyncio.Event()
        self._task = None

    def start_logging(self):
        """Starts the logging process for time offsets."""
        if self._task is not None:
            self._logger.warning("OffsetLogger is already running.")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop_logging(self):
        """Stops the time offset logging process."""
        if self._task is not None:
            self._stop_event.set()
            await self._task
            self._task = None

    # -------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------

    async def _run(self):
        while not self._stop_event.is_set():
            now = asyncio.get_event_loop().time()
            try:
                await self._estimate_offsets()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Unexpected error while logging offsets")
            elapsed = asyncio.get_event_loop().time() - now
            timeout = max(0, self._log_interval - elapsed)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass

    async def _estimate_offsets(self):
        results = await asyncio.gather(
            *(estimate_time_offset(ip) for ip in self._device_ips),
            return_exceptions=True,
        )
        for ip_addr, result in zip(self._device_ips, results):
            if isinstance(result, NeonTimeOffsetResponse):
                self._log_to_file(ip_addr, result.mean_time_offset_ms, result.mean_roundtrip_duration_ms)
            elif isinstance(result, Exception):
                self._logger.error(f"Failed to log offset for device {ip_addr}", exc_info=result)

    def _log_to_file(self, device_name: str, mean_offset: float | None, mean_duration: float | None):
        """Logs the time offset and roundtrip duration to the log file. If either value is None, it will be logged as an empty field.

        Args:
            device_name (str): The name of the device being logged.
            mean_offset (Optional[float]): The mean time offset in milliseconds.
            mean_duration (Optional[float]): The mean roundtrip duration in milliseconds.
        """
        
        timestamp = int(time.time_ns())
        with open(self._log_file, 'a', newline='', encoding='utf-8') as csvfile:
            field_names = ['device', 'timestamp [ns]', 'mean time offset [ms]', 'mean roundtrip duration [ms]']
            writer = csv.DictWriter(csvfile, fieldnames=field_names)

            if csvfile.tell() == 0:
                writer.writeheader()

            writer.writerow({
                'device': device_name, 
                'timestamp [ns]': timestamp, 
                'mean time offset [ms]': '' if mean_offset is None else mean_offset, 
                'mean roundtrip duration [ms]': '' if mean_duration is None else mean_duration
            })
