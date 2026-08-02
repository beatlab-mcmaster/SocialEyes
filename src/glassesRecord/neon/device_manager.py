from dataclasses import dataclass
from typing import Optional, Dict
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection
import asyncio
import datetime

from .device import DeviceState
from .device_worker import device_worker_process

@dataclass
class DeviceConfig:
    ip_addr: str
    port: int = 5555

class DeviceManager:

    _target_cycle_period_s: float = 1.0

    _logger: logging.Logger
    _logger_queue: multiprocessing.Queue # Queue for logging messages from device worker processes
    _logger_queue_listener: Optional[logging.handlers.QueueListener] = None

    _processes: Dict[str, multiprocessing.Process] = {} # Key: ip_addr, Value: Process instance
    _pipes: Dict[str, multiprocessing.connection.Connection] = {} # Key: ip_addr, Value: Pipe instance

    _collect_states_task: Optional[asyncio.Task] = None
    _collect_states_thread_stop_requested = False

    _devices: list[DeviceConfig] = []
    _device_states: Dict[str, DeviceState] = {} # Key: ip_addr, Value: DeviceState instance

    @property
    def devices(self) -> list[DeviceConfig]:
        return self._devices

    def __init__(self):
        self._logger = logging.getLogger("DeviceManager")
        self._logger_queue = multiprocessing.Queue()
        self._logger_queue_listener = logging.handlers.QueueListener(self._logger_queue, *logging.getLogger().handlers)
        self._logger_queue_listener.start()

    def register_device(self, ip_addr: str, port: int = 5555):
        parent_conn, child_conn = multiprocessing.Pipe()

        p = multiprocessing.Process(target=device_worker_process, args=(ip_addr, port, child_conn, self._logger_queue))
        p.start()
        self._logger.info(f"Started device worker process for {ip_addr}")

        self._processes[ip_addr] = p
        self._pipes[ip_addr] = parent_conn
        self._devices.append(DeviceConfig(ip_addr, port))

    async def start_all(self):
        self._collect_states_task = asyncio.create_task(self._collect_states())

    def stop_all(self):
        self._collect_states_thread_stop_requested = True
        if self._collect_states_task is not None:
            self._collect_states_task.cancel()
        for ip_addr, process in self._processes.items():
            if process.is_alive():
                process.terminate()
                process.join()
                self._logger.info(f"Stopped device worker process for {ip_addr}")

    def get_device_state(self, ip_addr: str) -> Optional[DeviceState]:
        return self._device_states.get(ip_addr)

    def get_all_device_states(self) -> Dict[str, DeviceState]:
        return self._device_states.copy()

    async def _collect_states(self):
        """Collect device states from worker processes."""
        while not self._collect_states_thread_stop_requested:
            now = datetime.datetime.now()

            for ip_addr, pipe in self._pipes.items():
                if pipe.poll():
                    state_update: DeviceState = pipe.recv()
                    self._device_states[ip_addr] = state_update

            time_since_last_update = (datetime.datetime.now() - now).total_seconds()
            if time_since_last_update < self._target_cycle_period_s:
                await asyncio.sleep(self._target_cycle_period_s - time_since_last_update)