from unittest.mock import AsyncMock

from glassesRecord.clients.core import ProcessResponse
from glassesRecord.clients.ping import is_windows, ping_device


async def test_ping_device_success(monkeypatch):
    ip_addr = '192.168.123.123'
    timeout = 4

    non_windows_ping_output = """
PING 192.168.2.110 (192.168.2.110): 56 data bytes
64 bytes from 192.168.2.110: icmp_seq=0 ttl=64 time=110.848 ms

--- 192.168.2.110 ping statistics ---
1 packets transmitted, 1 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 110.848/110.848/110.848/nan ms
"""
    windows_ping_output = """
Pinging 192.168.2.110 with 32 bytes of data:
Reply from 192.168.2.110: bytes=32 time=110ms TTL=64

Ping statistics for 192.168.2.110:
    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 110ms, Maximum = 110ms, Average = 110ms
"""

    mocked_fetch_response = ProcessResponse(
        stdout=non_windows_ping_output if not is_windows() else windows_ping_output,
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.ping.fetch_command_output",
        mocked_fetch,
    )

    response = await ping_device(ip_addr, timeout)
    if is_windows():
        mocked_fetch.assert_called_once_with(f"ping /n 1 {ip_addr}", timeout=timeout)
    else:
        mocked_fetch.assert_called_once_with(f"ping -c 1 {ip_addr}", timeout=timeout)
    
    assert response.result == 110

async def test_ping_device_host_not_reachable(monkeypatch):
    ip_addr = '192.168.200.110'
    timeout = 4
    
    non_windows_ping_output = """
PING 192.168.200.110 (192.168.200.110): 56 data bytes

--- 192.168.200.110 ping statistics ---
1 packets transmitted, 0 packets received, 100.0% packet loss
"""
    windows_ping_output = """
Pinging 192.168.200.110 with 32 bytes of data:
Request timed out.

Ping statistics for 192.168.200.110:
    Packets: Sent = 1, Received = 0, Lost = 1 (100% loss),
"""

    mocked_fetch_response = ProcessResponse(
        stdout=non_windows_ping_output if not is_windows() else windows_ping_output,
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.ping.fetch_command_output",
        mocked_fetch,
    )

    response = await ping_device(ip_addr, timeout)
    if is_windows():
        mocked_fetch.assert_called_once_with(f"ping /n 1 {ip_addr}", timeout=timeout)
    else:
        mocked_fetch.assert_called_once_with(f"ping -c 1 {ip_addr}", timeout=timeout)
    
    assert response.result is None
    assert response.timeout_occurred is False
    assert len(response.error_messages) == 1

async def test_ping_device_timeout(monkeypatch):
    ip_addr = '192.168.200.110'
    timeout = 1

    mocked_fetch_response = ProcessResponse(
        stdout=None,
        stderr=None,
        return_code=None,
        timeout_occurred=True,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.ping.fetch_command_output",
        mocked_fetch,
    )

    response = await ping_device(ip_addr, timeout)
    
    assert response.result is None
    assert response.timeout_occurred is True
