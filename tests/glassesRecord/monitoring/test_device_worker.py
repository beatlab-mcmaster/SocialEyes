import multiprocessing
import time
from unittest.mock import AsyncMock, Mock

from glassesRecord.monitoring.device_worker import (
    device_worker_process,
    run_device_worker,
)


async def test_run_device_worker_starts_and_stops_device(monkeypatch):
    device = Mock()
    device.start = AsyncMock()
    device.stop = AsyncMock()

    stop_event = Mock()
    stop_event.is_set.side_effect = [False, True]

    monkeypatch.setattr(
        "glassesRecord.monitoring.device_worker.asyncio.sleep",
        AsyncMock(),
    )

    await run_device_worker(device, stop_event)

    device.start.assert_awaited_once()
    device.stop.assert_awaited_once()
    stop_event.is_set.assert_any_call()

def test_device_worker_process_stops_cleanly():
    parent_pipe, child_pipe = multiprocessing.Pipe()
    stop_event = multiprocessing.Event()
    log_queue = multiprocessing.Queue()

    process = multiprocessing.Process(
        target=device_worker_process,
        args=(
            "127.0.0.1",
            5555,
            child_pipe,
            log_queue,
            stop_event,
        ),
    )

    process.start()

    time.sleep(1)
    stop_event.set()
    process.join(timeout=5)

    if process.is_alive():
        process.terminate()
        process.join()

    parent_pipe.close()

    assert process.exitcode == 0