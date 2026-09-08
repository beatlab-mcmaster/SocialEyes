from unittest.mock import AsyncMock

from glassesRecord.clients.neon_http import (
    get_neon_hardware_ids, 
    is_neon_api_accessible, 
    start_neon_recording,
    stop_and_save_neon_recording,
    cancel_neon_recording
)


async def test_is_neon_api_accessible_success(monkeypatch):
    ip_addr = '192.168.123.123'

    async def mocked_fetch_http_get_response(url: str, timeout = 5):
        assert url == f'http://{ip_addr}:8080/api/status'
        class MockResponse:
            def __init__(self):
                self.status_code = 200 # 200 means success
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()

    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await is_neon_api_accessible(ip_addr)
    assert response.result is True

async def test_is_neon_api_accessible_api_unavailable(monkeypatch):
    ip_addr = '192.168.123.123'

    async def mocked_fetch_http_get_response(url: str, timeout = 5):
        assert url == f'http://{ip_addr}:8080/api/status'
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()

    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await is_neon_api_accessible(ip_addr)
    assert response.result is False

async def test_is_neon_api_accessible_timeout(monkeypatch):
    ip_addr = '192.168.123.123'

    async def mocked_fetch_http_get_response(url: str, timeout = 5):
        assert url == f'http://{ip_addr}:8080/api/status'
        class MockResponse:
            def __init__(self):
                self.status_code = None # 200 means success
                self.timeout_occurred = True
                self.error_messages = []
        return MockResponse()

    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await is_neon_api_accessible(ip_addr)
    assert response.result is False
    assert response.timeout_occurred is True

async def test_get_neon_hardware_ids_with_glasses_connected(monkeypatch):
    ip_addr = '192.168.2.123'
    api_response = """
{
    "message": "Success",
    "result": [
        {
            "data": {
                "conn_type": "WEBSOCKET",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=imu&audioenable=off",
                "port": 8686,
                "protocol": "rtsp",
                "sensor": "imu",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "DIRECT",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=imu&audioenable=on",
                "port": 8086,
                "protocol": "rtsp",
                "sensor": "imu",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "WEBSOCKET",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=world&audioenable=off",
                "port": 8686,
                "protocol": "rtsp",
                "sensor": "world",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "DIRECT",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=world&audioenable=on",
                "port": 8086,
                "protocol": "rtsp",
                "sensor": "world",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "WEBSOCKET",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=gaze&audioenable=off",
                "port": 8686,
                "protocol": "rtsp",
                "sensor": "gaze",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "DIRECT",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=gaze&audioenable=on",
                "port": 8086,
                "protocol": "rtsp",
                "sensor": "gaze",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "WEBSOCKET",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=eye_events&audioenable=off",
                "port": 8686,
                "protocol": "rtsp",
                "sensor": "eye_events",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "DIRECT",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=eye_events&audioenable=on",
                "port": 8086,
                "protocol": "rtsp",
                "sensor": "eye_events",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "WEBSOCKET",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=eyes&audioenable=off",
                "port": 8686,
                "protocol": "rtsp",
                "sensor": "eyes",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "conn_type": "DIRECT",
                "connected": true,
                "ip": "192.168.2.123",
                "params": "camera=eyes&audioenable=on",
                "port": 8086,
                "protocol": "rtsp",
                "sensor": "eyes",
                "stream_error": false
            },
            "model": "Sensor"
        },
        {
            "data": {
                "battery_level": 97,
                "battery_state": "OK",
                "device_id": "1234567890abcdef",
                "device_name": "Neon Companion",
                "ip": "192.168.2.123",
                "memory": 123456789000,
                "memory_state": "OK",
                "time_echo_port": 12321
            },
            "model": "Phone"
        },
        {
            "data": {
                "frame_name": "Is this thing on",
                "glasses_serial": "-1",
                "module_serial": "123456",
                "version": "2.0",
                "world_camera_serial": "-1"
            },
            "model": "Hardware"
        }
    ]
}
"""
    
    async def mocked_fetch_http_get_response(url: str, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/status'
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                    self.response_text = api_response
                    self.timeout_occurred = True
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await get_neon_hardware_ids(ip_addr)
    assert response.device_name == "Neon Companion"
    assert response.device_id == "1234567890abcdef"
    assert response.frame_name == "Is this thing on"
    assert response.module_serial == "123456"

async def test_get_neon_hardware_ids_with_glasses_not_connected(monkeypatch):
    ip_addr = '192.168.2.123'
    api_response = """
{
    "message": "Success",
    "result": [
        {
            "data": {
                "battery_level": 97,
                "battery_state": "OK",
                "device_id": "1234567890abcdef",
                "device_name": "Neon Companion",
                "ip": "192.168.2.123",
                "memory": 1234567890123,
                "memory_state": "OK",
                "time_echo_port": 12321
            },
            "model": "Phone"
        }
    ]
}
"""

    async def mocked_fetch_http_get_response(url: str, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/status'
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                    self.response_text = api_response
                    self.timeout_occurred = True
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await get_neon_hardware_ids(ip_addr)
    assert response.device_name == 'Neon Companion'
    assert response.device_id == '1234567890abcdef'
    assert response.frame_name is None
    assert response.module_serial is None

async def test_get_neon_hardware_ids_timeout(monkeypatch):
    ip_addr = '192.168.2.123'

    async def mocked_fetch_http_get_response(url: str, timeout = 5):
        assert url == f'http://{ip_addr}:8080/api/status'
        class MockResponse:
            def __init__(self):
                self.status_code = None
                self.response_text = None
                self.timeout_occurred = True
                self.error_messages = []
        return MockResponse()

    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_get_response', mocked_fetch_http_get_response)

    response = await get_neon_hardware_ids(ip_addr)
    assert response.timeout_occurred is True
    assert response.device_name is None
    assert response.device_id is None
    assert response.frame_name is None
    assert response.module_serial is None

async def test_start_neon_recording_success(monkeypatch):
    ip_addr = '192.168.123.123'
    api_response = """
{
    "message": "Started recording",
    "result": {
        "id": "ee8a4e00-e1b6-4724-bbb2-75b2c48a58dd"
    }
}
"""
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:start'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                    self.response_text = api_response
                    self.timeout_occurred = False
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await start_neon_recording(ip_addr)
    assert response.timeout_occurred is False
    assert response.result == "ee8a4e00-e1b6-4724-bbb2-75b2c48a58dd"

async def test_start_neon_recording_timeout(monkeypatch):
    ip_addr = '192.168.123.123'
    
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:start'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = None
                    self.response_text = None
                    self.timeout_occurred = True
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await start_neon_recording(ip_addr)
    assert response.timeout_occurred is True
    assert response.result is None

async def test_stop_and_save_neon_recording_success(monkeypatch):
    ip_addr = '192.168.123.123'
    api_response = """
{
    "message": "Stopped recording",
    "result": null
}
""" # v2.9.31: result = null
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:stop_and_save'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                    self.response_text = api_response
                    self.timeout_occurred = False
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await stop_and_save_neon_recording(ip_addr)
    assert response.timeout_occurred is False
    assert response.result is None

async def test_stop_and_save_neon_recording_timeout(monkeypatch):
    ip_addr = '192.168.123.123'
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:stop_and_save'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = None
                    self.response_text = None
                    self.timeout_occurred = True
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await stop_and_save_neon_recording(ip_addr)
    assert response.timeout_occurred is True
    assert response.result is None

async def test_cancel_neon_recording_success(monkeypatch):
    ip_addr = '192.168.123.123'
    api_response = """
{
    "message": "Stopped recording",
    "result": null
}
""" # v2.9.31: result = null
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:cancel'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                    self.response_text = api_response
                    self.timeout_occurred = False
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await cancel_neon_recording(ip_addr)
    assert response.timeout_occurred is False
    assert response.result is None

async def test_cancel_neon_recording_timeout(monkeypatch):
    ip_addr = '192.168.123.123'
    async def mocked_fetch_http_post_response(url: str, data_json=None, timeout = 5):
            assert url == f'http://{ip_addr}:8080/api/recording:cancel'
            assert data_json == {}
            class MockResponse:
                def __init__(self):
                    self.status_code = None
                    self.response_text = None
                    self.timeout_occurred = True
                    self.error_messages = []
            return MockResponse()
    
    monkeypatch.setattr('glassesRecord.clients.neon_http.fetch_http_post_response', mocked_fetch_http_post_response)

    response = await cancel_neon_recording(ip_addr)
    assert response.timeout_occurred is True
    assert response.result is None
    