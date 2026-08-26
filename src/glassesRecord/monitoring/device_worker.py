import asyncio
import logging
import logging.handlers
import multiprocessing.synchronize
from multiprocessing.connection import Connection
from multiprocessing.queues import Queue

from .device import Device, DeviceState


async def run_device_worker(
    device: Device,
    stop_event: multiprocessing.synchronize.Event,
    pipe: Connection
) -> None:
    await device.start()
    try:
        while not stop_event.is_set():
            if pipe.poll():
                message = pipe.recv()
                if isinstance(message, tuple) and len(message) == 2:
                    command, value = message
                    if command == "set_monitoring_interval":
                        device.monitoring_interval_s = value
            await asyncio.sleep(1)
    finally:
        await device.stop()

def device_worker_process(
        ip_addr: str, 
        port: int, 
        pipe: Connection, 
        log_queue: Queue,
        stop_event: multiprocessing.synchronize.Event
    ):
    """
    This is the worker process that manages a single device.
    The process communicates with the main process via the `pipe` and sends log messages via the `log_queue`.
    """

    # Setup logging to send logs to the main process via a queue
    log_queue_handler = logging.handlers.QueueHandler(log_queue)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_queue_handler)
    
    def on_change(new_state: DeviceState | None):
        pipe.send(new_state)

    device = Device(ip_addr, port, on_change=on_change)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(run_device_worker(device, stop_event, pipe))
    except asyncio.CancelledError:
        pass
    finally:
        pipe.close()
        loop.close()

    