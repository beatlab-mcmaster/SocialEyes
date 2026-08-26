
from unittest.mock import AsyncMock, Mock

import pytest

from glassesRecord.app import TableApp, TableAppConfig


@pytest.fixture
def fake_session_controller():
    session = AsyncMock()
    session.session_id = "session-1"
    session.device_ip_addrs = ["192.168.2.101"]
    session.start_device_monitoring = AsyncMock()
    session.stop_device_monitoring = AsyncMock()
    session.log_event = Mock()
    session.get_all_device_states.return_value = {}
    return session


@pytest.fixture
def app(monkeypatch, fake_session_controller, tmp_path):
    monkeypatch.setattr(
        "glassesRecord.app.create_session_controller",
        Mock(return_value=fake_session_controller),
    )

    config = TableAppConfig(
        log_level="INFO",
        log_dir=str(tmp_path),
        device_ips=["192.168.2.101"],
        is_single_session_mode=False,
        status_log_max_len=10,
        offset_logger_interval=10,
    )

    return TableApp(config)

async def test_app_composes_expected_widgets(app):
    async with app.run_test():
        assert app.query_one("#event_tag") is not None
        assert app.query_one("SelectableRowsDataTable") is not None
        assert app.query_one("Footer") is not None
        assert app.query_one("Label") is not None        

async def test_app_starts_device_monitoring_on_mount(
    app,
    fake_session_controller,
):
    async with app.run_test():
        fake_session_controller.start_device_monitoring.assert_awaited_once()
