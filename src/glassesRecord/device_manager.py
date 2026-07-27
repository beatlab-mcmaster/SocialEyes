from typing import Optional, Dict
import logging
import logging.handlers
from device import Device, DeviceState
import multiprocessing
import multiprocessing.connection
import asyncio

from device_worker import device_worker_process

class DeviceManager:

    _logger: logging.Logger
    _logger_queue: multiprocessing.Queue
    _logger_queue_listener: Optional[logging.handlers.QueueListener] = None

    _devices: Dict[str, Device] = {} # Key: ip_addr, Value: Device instance
    _device_states: Dict[str, DeviceState] = {} # Key: ip_addr, Value: DeviceState instance

    _processes: Dict[str, multiprocessing.Process] = {} # Key: ip_addr, Value: Process instance
    _pipes: Dict[str, multiprocessing.connection.Connection] = {} # Key: ip_addr, Value: Pipe instance
    _collect_states_task: Optional[asyncio.Task] = None
    _collect_states_thread_stop_requested = False

    @property
    def devices(self) -> Dict[str, Device]:
        return self._devices

    def __init__(self):
        self._logger = logging.getLogger("DeviceManager")
        self._logger_queue = multiprocessing.Queue()
        self._logger_queue_listener = logging.handlers.QueueListener(self._logger_queue, *logging.getLogger().handlers)
        self._logger_queue_listener.start()

    def register_device(self, ip_addr: str, port: int = 5555):
        parent_conn, child_conn = multiprocessing.Pipe()
        p = multiprocessing.Process(target=device_worker_process, args=(ip_addr, port, child_conn, self._logger_queue))
        self._processes[ip_addr] = p
        self._pipes[ip_addr] = parent_conn
        
        p.start()
        self._logger.info(f"Started device worker process for {ip_addr}")

        self._devices[ip_addr] = Device(ip_addr, port, on_change=None) # TODO remove placeholder

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
        while not self._collect_states_thread_stop_requested:
            for ip_addr, pipe in self._pipes.items():
                if pipe.poll():
                    state_update: DeviceState = pipe.recv()
                    self._device_states[ip_addr] = state_update
            await asyncio.sleep(0.5)