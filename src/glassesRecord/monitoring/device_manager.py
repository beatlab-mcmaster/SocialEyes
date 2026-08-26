import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
from collections.abc import Callable
from dataclasses import dataclass

from .device import DeviceState
from .device_worker import device_worker_process


@dataclass
class DeviceConfig:
    ip_addr: str
    port: int = 5555

@dataclass
class DeviceWorkerHandle:
    device_config: DeviceConfig
    process: multiprocessing.Process
    pipe: multiprocessing.connection.Connection
    stop_event: multiprocessing.synchronize.Event

def create_device_worker_process(
        ip_addr: str, 
        port: int, 
        pipe: multiprocessing.connection.Connection, 
        log_queue: multiprocessing.Queue, 
        stop_event: multiprocessing.synchronize.Event
    ) -> multiprocessing.Process:
    return multiprocessing.Process(
        target=device_worker_process,
        args=(ip_addr, port, pipe, log_queue, stop_event)
    )

class DeviceManager:

    _DEVICE_POLLING_INTERVAL_S: float = 1.0

    _process_factory: Callable[..., multiprocessing.Process]

    _logger: logging.Logger
    _logger_queue: multiprocessing.Queue # Queue for logging messages from device worker processes
    _logger_queue_listener: logging.handlers.QueueListener | None

    _workers: dict[str, DeviceWorkerHandle] # Key: ip_addr, Value: DeviceWorkerHandle instance
    
    _collect_states_task: asyncio.Task | None
    _collect_states_stop_event: asyncio.Event

    _device_states: dict[str, DeviceState] # Key: ip_addr, Value: DeviceState instance

    @property
    def devices(self) -> list[DeviceConfig]:
        return [w.device_config for w in self._workers.values()]

    def __init__(self, process_factory: Callable[..., multiprocessing.Process] = create_device_worker_process):
        self._logger = logging.getLogger("DeviceManager")
        self._logger_queue = multiprocessing.Queue()
        self._logger_queue_listener = logging.handlers.QueueListener(self._logger_queue, *logging.getLogger().handlers)
        self._logger_queue_listener.start()

        self._workers = {}
        self._process_factory = process_factory

        self._collect_states_task = None
        self._collect_states_stop_event = asyncio.Event()

        self._device_states = {}

    def register_device(self, ip_addr: str, port: int = 5555):
        """
        Register a new device and start its worker process.
        If the device is already registered, this method does nothing.
        """
        if ip_addr in self._workers:
            self._logger.warning(f"Device {ip_addr} is already registered.")
            return
        
        parent_conn, child_conn = multiprocessing.Pipe()
        stop_event = multiprocessing.Event()

        p = self._process_factory(ip_addr, port, child_conn, self._logger_queue, stop_event)
        p.start()
        child_conn.close()  # Close the child end in the parent process

        self._workers[ip_addr] = DeviceWorkerHandle(
            device_config=DeviceConfig(ip_addr, port),
            process=p,
            pipe=parent_conn,
            stop_event=stop_event
        )

    async def start_all(self):
        """
        Start the device state collection task if it's not already running.
        """
        if self._collect_states_task is not None and not self._collect_states_task.done():
            self._logger.warning("Device state collection task is already running.")
            return
        self._collect_states_stop_event.clear()
        self._collect_states_task = asyncio.create_task(self._collect_states())

    async def stop_all(self, join_timeout: float = 2):
        self._collect_states_stop_event.set()
        if self._collect_states_task is not None:
            self._collect_states_task.cancel()

        for worker in self._workers.values():
            self._stop_worker(worker, join_timeout)
        await asyncio.sleep(0)

    def get_device_state(self, ip_addr: str) -> DeviceState | None:
        return self._device_states.get(ip_addr)

    def get_all_device_states(self) -> dict[str, DeviceState]:
        return self._device_states.copy()

    def set_monitoring_interval(self, ip_addr: str, interval_s: float):
        worker = self._workers[ip_addr]
        try:
            worker.pipe.send(("set_monitoring_interval", interval_s))
        except Exception as e:
            self._logger.error(f"Failed to set monitoring interval for {ip_addr}: {e}")
    
    # -------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------

    async def _collect_states(self):
        """Collect device states from worker processes."""
        while not self._collect_states_stop_event.is_set():
            now = asyncio.get_event_loop().time()
            self._poll_worker_pipes()
            time_elapsed = asyncio.get_event_loop().time() - now
            timeout = max(0, self._DEVICE_POLLING_INTERVAL_S - time_elapsed)
            try:
                await asyncio.wait_for(self._collect_states_stop_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass

    def _poll_worker_pipes(self):
        for ip_addr, worker in self._workers.items():
            try:
                if worker.pipe.poll():
                    state_update: DeviceState = worker.pipe.recv()
                    self._device_states[ip_addr] = state_update
            except Exception as e:
                self._logger.error(f"Error polling worker pipe for {ip_addr}: {e}")

    def _stop_worker(self, worker: DeviceWorkerHandle, join_timeout: float):
        worker.process.terminate()
        worker.process.join(timeout=join_timeout)
