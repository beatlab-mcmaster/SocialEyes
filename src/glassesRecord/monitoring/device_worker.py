import asyncio
import logging
import logging.handlers
import multiprocessing.synchronize
from multiprocessing.connection import Connection
from multiprocessing.queues import Queue

from .device import Device, DeviceState


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
    root_logger.addHandler(log_queue_handler)
    
    def on_change(new_state: DeviceState | None):
        pipe.send(new_state)

    device = Device(ip_addr, port, on_change=on_change)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await device.start()
        while not stop_event.is_set():
            await asyncio.sleep(1)
        await device.stop()

    try:
        loop.run_until_complete(run())
    finally:
        pipe.close()
        loop.close()
    