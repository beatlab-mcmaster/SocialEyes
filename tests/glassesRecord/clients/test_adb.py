
from glassesRecord.clients.adb import check_adb_connection, check_statistics_script_exists, fetch_socialeyes_statistics, get_default_adb_path, push_statistics_script


def test_get_default_adb_path_reads_from_env(monkeypatch):
    test_path = "/custom/path/to/adb"
    monkeypatch.setenv("ADB_PATH", test_path)
    assert get_default_adb_path() == test_path

    monkeypatch.delenv("ADB_PATH", raising=False)
    assert get_default_adb_path() == "adb"

async def test_check_adb_connection_result_is_false_if_not_connected(monkeypatch, adb_devices_response):
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_devices_response([])
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    
    response = await check_adb_connection("192.168.1.123")
    assert response.result is False

async def test_check_adb_connection_result_is_true_if_connected(monkeypatch, adb_devices_response):
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_devices_response(['192.168.1.123:5555'])
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    
    response = await check_adb_connection("192.168.1.123")
    assert response.result is True

async def test_check_adb_connection_result_is_false_if_ip_doesnt_match(monkeypatch, adb_devices_response):
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_devices_response(['192.168.1.123:5555'])
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    
    response = await check_adb_connection("192.168.1.222")
    assert response.result is False

async def test_check_adb_connection_result_is_false_if_port_doesnt_match(monkeypatch, adb_devices_response):
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_devices_response(['192.168.1.123:5555'])
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    
    response = await check_adb_connection("192.168.1.223", port=6666)
    assert response.result is False
    assert len(response.error_messages) == 0

async def test_fetch_socialeyes_statistics_success(monkeypatch, adb_run_socialeyes_statistics_script_response):
    sample_response = """
{
  "version": "1.0",
  "phone": {
    "now": "2026-08-25T16:09:31,318536419+00:00",
    "timezone": "America/Toronto",
    "battery_level": 58,
    "storage": {
      "total_gb": 243,
      "used_gb": 76,
      "free_gb": 167
    },
    "display": {
      "is_locked": true,
      "is_on": false
    },
    "usb_devices": [

    ],
    "wifi": {
      "ssid": "TEST_net",
      "bssid": "12:34:56:78:9A:BC",
      "rssi": -34
    },
    "android_version": "14",
    "android_build": "1234"
  },
  "neon": {
    "app_version": {
        "version_name": "1.2.3-prod",
        "version_code": "1",
        "last_update_time_str": "2026-01-01 01:23:45"
    },
    "is_active": "false",
    "recordings": [

    ]
  }
}
"""
    
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_run_socialeyes_statistics_script_response(sample_response)
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)

    response = await fetch_socialeyes_statistics("192.168.1.123")
    assert response.result is not None
    assert len(response.error_messages) == 0

async def test_fetch_socialeyes_statistics_result_is_none_if_empty_response(monkeypatch, adb_run_socialeyes_statistics_script_response):
    sample_response = ""
    
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_run_socialeyes_statistics_script_response(sample_response)
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)

    response = await fetch_socialeyes_statistics("192.168.1.123")
    assert response.result is None
    assert len(response.error_messages) > 0

async def test_fetch_socialeyes_statistics_result_is_none_if_invalid_json(monkeypatch, adb_run_socialeyes_statistics_script_response):
    sample_response = "{invalid_json123}"
    
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_run_socialeyes_statistics_script_response(sample_response)
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)

    response = await fetch_socialeyes_statistics("192.168.1.123")
    assert response.result is None
    assert len(response.error_messages) > 0

async def test_fetch_socialeyes_statistics_result_is_none_if_timeout(monkeypatch, adb_run_socialeyes_statistics_script_response):
    sample_response = None
    timeout_occurred = True
    
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        return adb_run_socialeyes_statistics_script_response(sample_response, timeout_occurred)
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)

    response = await fetch_socialeyes_statistics("192.168.1.123")
    assert response.result is None
    assert response.timeout_occurred is True
    assert len(response.error_messages) > 0

async def test_check_statistics_script_exists_uses_script_path(monkeypatch):
    script_path = "/storage/self/primary/Documents/SocialEyes/statistics.sh"
    ip_addr = "192.168.123.222"
    port = 6666
    expected_cmd = f'-s {ip_addr}:{port} shell ls {script_path}'
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        assert cmd == expected_cmd
        class MockResponse:
            def __init__(self):
                self.return_code = 0
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    response = await check_statistics_script_exists(ip_addr, script_path, port=port)
    assert response.result is True

async def test_check_statistics_script_exists_returns_false_if_ls_returns_nonzero(monkeypatch):
    script_path = "/storage/self/primary/Documents/SocialEyes/statistics.sh"
    ip_addr = "192.168.123.222"
    port = 6666
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        class MockResponse:
            def __init__(self):
                self.return_code = 1
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    response = await check_statistics_script_exists(ip_addr, script_path, port=port)
    assert response.result is False

async def test_push_statistics_script_uses_script_path(monkeypatch):
    source_path = "/local/path/to/statistics.sh"
    script_path = "/storage/self/primary/Documents/SocialEyes/statistics.sh"
    ip_addr = "192.168.123.222"
    port = 6666
    expected_cmd = f'-s {ip_addr}:{port} push {source_path} {script_path}'
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        assert cmd == expected_cmd
        class MockResponse:
            def __init__(self):
                self.return_code = 0
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    response = await push_statistics_script(ip_addr, source_path, script_path, port=port)
    assert response.result is True

async def test_push_statistics_script_returns_false_if_push_fails(monkeypatch):
    source_path = "/local/path/to/statistics.sh"
    script_path = "/storage/self/primary/Documents/SocialEyes/statistics.sh"
    ip_addr = "192.168.123.223"
    port = 6667
    async def mock_fetch_adb_command_output(cmd, timeout=5):
        class MockResponse:
            def __init__(self):
                self.return_code = 1
                self.timeout_occurred = False
                self.error_messages = []
        return MockResponse()
    monkeypatch.setattr("glassesRecord.clients.adb.fetch_adb_command_output", mock_fetch_adb_command_output)
    response = await push_statistics_script(ip_addr, source_path, script_path, port=port)
    assert response.result is False