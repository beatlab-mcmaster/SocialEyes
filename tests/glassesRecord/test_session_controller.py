from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest

from glassesRecord.session_controller import SessionController, SessionControllerConfig


@dataclass
class FakeDevice:
    ip_addr: str
    port: int = 5555

@pytest.fixture
def fake_device_manager(monkeypatch):
    manager = Mock()
    manager.devices = [
        FakeDevice("192.168.2.101"),
        FakeDevice("192.168.2.102"),
    ]
    manager.register_device = Mock()
    manager.start_all = AsyncMock()
    manager.stop_all = AsyncMock()
    manager.get_all_device_states.return_value = {}

    monkeypatch.setattr(
        "glassesRecord.session_controller.DeviceManager",
        Mock(return_value=manager),
    )
    return manager


@pytest.fixture
def session_controller(tmp_path, fake_device_manager):
    config = SessionControllerConfig(
        session_id="session-1",
        session_dir=str(tmp_path),
        is_single_session_mode=False,
        device_ips=["192.168.2.101", "192.168.2.102"],
        offset_logger_interval=10,
        log_level="INFO",
        device_state_logger_interval=10
    )
    return SessionController(config)

def test_initialization_registers_configured_devices(
    session_controller,
    fake_device_manager,
):
    assert session_controller.session_id == "session-1"
    assert session_controller.session_dir

    assert fake_device_manager.register_device.call_count == 2
    fake_device_manager.register_device.assert_any_call("192.168.2.101")
    fake_device_manager.register_device.assert_any_call("192.168.2.102")

async def test_start_device_monitoring_delegates(session_controller, fake_device_manager):
    await session_controller.start_device_monitoring()

    fake_device_manager.start_all.assert_awaited_once()

async def test_stop_device_monitoring_delegates(session_controller, fake_device_manager):
    await session_controller.stop_device_monitoring()

    fake_device_manager.stop_all.assert_awaited_once()
    