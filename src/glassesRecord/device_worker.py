from device import Device, DeviceState
import asyncio
import logging
import logging.handlers
from typing import Optional

def device_worker_process(ip_addr, port, pipe, log_queue):
    """Each device runs in its own process"""

    # Setup logging to send logs to the main process via a queue
    log_queue_handler = logging.handlers.QueueHandler(log_queue)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_queue_handler)
    
    def on_change(new_state: Optional[DeviceState]):
        """Callback to send state changes to the main process via queue"""
        if new_state is not None:
            pipe.send(new_state)
        else:
            logging.getLogger().warning("Received None as new_state in on_change callback")

    device = Device(ip_addr, port, on_change=on_change)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await device.start()
        while True:
            await asyncio.sleep(1)

    loop.run_until_complete(run())
    