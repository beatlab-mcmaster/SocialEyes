
import multiprocessing.connection
import multiprocessing.synchronize
from unittest.mock import Mock

import pytest

from glassesRecord.monitoring.device_manager import DeviceConfig, DeviceManager


@pytest.fixture
def fake_process_factory():
    def create_fake_process(
        ip_addr: str, 
        port: int, 
        pipe: multiprocessing.connection.Connection, 
        log_queue: multiprocessing.Queue, 
        stop_event: multiprocessing.synchronize.Event,
        log_level: str
    ) -> multiprocessing.Process:
        # Create a Mock process that does nothing
        process = Mock(spec=multiprocessing.Process)
        return process

    return create_fake_process

def test_register_device_passes_expected_arguments():
    process_factory_mock = Mock()
    manager = DeviceManager(process_factory=process_factory_mock)
    manager.register_device("192.168.2.123", 5555)

    assert process_factory_mock.call_args[0][:2] == (
        "192.168.2.123",
        5555,
    )

def test_register_device_stores_worker(fake_process_factory):
    manager = DeviceManager(process_factory=fake_process_factory)

    manager.register_device("127.0.0.2", port=5555)

    assert manager.devices == [DeviceConfig("127.0.0.2", 5555)]
    assert "127.0.0.2" in manager._workers

    worker = manager._workers["127.0.0.2"]
    assert worker is not None

def test_registering_duplicate_device_does_nothing(fake_process_factory):
    manager = DeviceManager(process_factory=fake_process_factory)
    manager.register_device("192.168.2.123")
    manager.register_device("192.168.2.123")
    manager.register_device("192.168.2.124")
    assert len(manager.devices) == 2

async def test_start_all_creates_collection_task(fake_process_factory):
    manager = DeviceManager(process_factory=fake_process_factory)
    await manager.start_all()

    assert manager._collect_states_task is not None
    assert manager._collect_states_task.done() is False

    await manager.stop_all()

async def test_start_all_does_not_start_duplicate_tasks(fake_process_factory):
    manager = DeviceManager(process_factory=fake_process_factory)
    await manager.start_all()
    first_task = manager._collect_states_task

    await manager.start_all()
    second_task = manager._collect_states_task

    assert second_task is first_task

async def test_stop_all_signals_every_worker():
    manager = DeviceManager(process_factory=Mock())
    fake_workers = {
        "192.168.2.101": Mock(stop_event=Mock(), process=Mock(join_called=False)),
        "192.168.2.102": Mock(stop_event=Mock(), process=Mock(join_called=False)),
    }
    for ip_addr, worker in fake_workers.items():
        manager._workers[ip_addr] = worker

    await manager.stop_all()

    for worker in fake_workers.values():
        worker.process.join.assert_called()
