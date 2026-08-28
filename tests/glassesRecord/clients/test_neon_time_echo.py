
import asyncio

from glassesRecord.clients.neon_time_echo import estimate_time_offset


async def test_estimate_time_offset_success(monkeypatch):
    _ip_addr = '192.168.123.123'
    _time_echo_port = 12345

    class MockEstimate:
        def __init__(self):
            self.time_offset_ms = type('TimeOffset', (), {'mean': 10.1})()
            self.roundtrip_duration_ms = type('RoundtripDuration', (), {'mean': 5.2})()
    class MockTimeOffsetEstimator:
        def __init__(self, ip_addr, port):
            assert ip_addr == _ip_addr
            assert port == _time_echo_port
        async def estimate(self):
            return MockEstimate()
    monkeypatch.setattr('glassesRecord.clients.neon_time_echo.TimeOffsetEstimator', MockTimeOffsetEstimator)

    response = await estimate_time_offset(_ip_addr, _time_echo_port)
    assert response.mean_time_offset_ms == 10.1
    assert response.mean_roundtrip_duration_ms == 5.2

async def test_estimate_time_offset_timeout(monkeypatch):
    _ip_addr = '192.168.123.123'
    _time_echo_port = 12345

    class MockTimeOffsetEstimator:
        def __init__(self, ip_addr, port):
            assert ip_addr == _ip_addr
            assert port == _time_echo_port
        async def estimate(self):
            raise asyncio.TimeoutError("Simulated timeout")
    monkeypatch.setattr('glassesRecord.clients.neon_time_echo.TimeOffsetEstimator', MockTimeOffsetEstimator)

    response = await estimate_time_offset(_ip_addr, _time_echo_port)
    assert response.timeout_occurred is True