import csv
from unittest.mock import Mock

from glassesRecord.clients.neon_time_echo import NeonTimeOffsetResponse
from glassesRecord.monitoring.offset_logger import OffsetLogger


def create_neon_time_offset_response(
    offset: float | None = 1.5,
    duration: float | None = 2.5,
) -> NeonTimeOffsetResponse:
    return NeonTimeOffsetResponse(
        timeout_occurred=False,
        error_messages=[],
        mean_time_offset_ms=offset,
        mean_roundtrip_duration_ms=duration,
    )

def test_initialization_creates_log_directory(tmp_path):
    log_dir = tmp_path / "offsets"

    logger = OffsetLogger(["192.168.2.101"], str(log_dir))

    assert log_dir.is_dir()
    assert logger.log_file.startswith(str(log_dir))
    assert logger.log_file.endswith("_offsets.csv")

def test_log_to_file_writes_header_and_values(tmp_path):
    logger = OffsetLogger(["192.168.2.101"], str(tmp_path))

    logger._log_to_file("192.168.2.101", 1.5, 2.5)

    with open(logger.log_file, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["device"] == "192.168.2.101"
    assert rows[0]["mean time offset [ms]"] == "1.5"
    assert rows[0]["mean roundtrip duration [ms]"] == "2.5"


def test_log_to_file_writes_empty_values_for_missing_measurements(tmp_path):
    logger = OffsetLogger(["192.168.2.101"], str(tmp_path))

    logger._log_to_file("192.168.2.101", None, None)

    with open(logger.log_file, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["mean time offset [ms]"] == ""
    assert rows[0]["mean roundtrip duration [ms]"] == ""

def test_log_to_file_writes_header_only_once(tmp_path):
    logger = OffsetLogger(["192.168.2.101"], str(tmp_path))

    logger._log_to_file("192.168.2.101", 1.0, 2.0)
    logger._log_to_file("192.168.2.101", 3.0, 4.0)

    with open(logger.log_file, encoding="utf-8") as file:
        lines = file.readlines()

    assert len(lines) == 3
    assert lines[0].count("device") == 1


async def test_estimate_offsets_logs_each_successful_result(
    tmp_path,
    monkeypatch,
):
    logger = OffsetLogger(
        ["192.168.2.101", "192.168.2.102"],
        str(tmp_path),
    )
    responses = {
        "192.168.2.101": create_neon_time_offset_response(1.0, 2.0),
        "192.168.2.102": create_neon_time_offset_response(3.0, 4.0),
    }

    async def fake_estimate(ip_addr):
        return responses[ip_addr]

    log_mock = Mock()
    logger._log_to_file = log_mock
    monkeypatch.setattr(
        "glassesRecord.monitoring.offset_logger.estimate_time_offset",
        fake_estimate,
    )

    await logger._estimate_offsets()

    assert log_mock.call_count == 2
    log_mock.assert_any_call("192.168.2.101", 1.0, 2.0)
    log_mock.assert_any_call("192.168.2.102", 3.0, 4.0)

async def test_estimate_offsets_logs_and_continues_after_device_failure(
    tmp_path,
    monkeypatch,
    caplog,
):
    logger = OffsetLogger(
        ["192.168.2.101", "192.168.2.102"],
        str(tmp_path),
    )

    async def fake_estimate(ip_addr):
        if ip_addr == "192.168.2.101":
            raise TimeoutError("device timed out")
        return create_neon_time_offset_response(3.0, 4.0)

    log_mock = Mock()
    logger._log_to_file = log_mock
    monkeypatch.setattr(
        "glassesRecord.monitoring.offset_logger.estimate_time_offset",
        fake_estimate,
    )

    await logger._estimate_offsets()

    assert "Failed to log offset for device 192.168.2.101" in caplog.text
    log_mock.assert_called_once_with("192.168.2.102", 3.0, 4.0)