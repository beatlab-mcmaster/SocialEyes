from unittest.mock import AsyncMock

from glassesRecord.clients.core import ProcessResponse, SimpleClientResponse
from glassesRecord.clients.neon_adb import (
    check_red_light_flashing_indicators,
    get_neon_companion_app_task_id,
    start_neon_companion_app,
    stop_neon_companion_app,
)


async def test_check_red_light_flashing_indicators_indicator_present(monkeypatch):
    ip_addr = '192.168.2.123'
    port = 5555
    workspace_id = 'workspace_1'
    recording_id = '81024c9d-52eb-4a1d-a6d6-17d918731038'
    
    mocked_adb_fetch_response = ProcessResponse(
        stdout=f"10-02 13:44:00.254  6162  6200 E RecWatchdogService: File content://com.android.externalstorage.documents/tree/primary%3ADocuments/document/primary%3ADocuments%2FNeon%2Fb5b4d161-eea9-46af-aabc-393608306e84%2F{recording_id}%2Fextimu%20ps2.raw has not changed size in the last 30s! last size: 13226298",
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    response = await check_red_light_flashing_indicators(ip_addr, port, workspace_id, recording_id, timeout=100)
    assert response.result is True

async def test_check_red_light_flashing_indicators_indicator_not_present(monkeypatch):
    ip_addr = '192.168.2.123'
    port = 5555
    workspace_id = 'workspace_1'
    recording_id = 'recording_1'

    mocked_adb_fetch_response = ProcessResponse(
        stdout="some other log line",
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    response = await check_red_light_flashing_indicators(ip_addr, port, workspace_id, recording_id, timeout=100)
    assert response.result is False

async def test_get_neon_companion_app_task_id_success(monkeypatch):
    stdout = 'taskId=948: com.pupillabs.neoncomp/com.pupillabs.neoncomp.ui.main.MainActivity bounds=[0,0][1080,2400] userId=0 visible=true topActivity=ComponentInfo{com.pupillabs.neoncomp/com.pupillabs.neoncomp.ui.main.MainActivity}'
    mocked_adb_fetch_response = ProcessResponse(
        stdout=stdout,
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    response = await get_neon_companion_app_task_id(ip_addr, port)
    assert response.result == 948

async def test_get_neon_companion_app_task_id_not_running(monkeypatch):
    stdout = ''
    mocked_adb_fetch_response = ProcessResponse(
        stdout=stdout,
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    response = await get_neon_companion_app_task_id(ip_addr, port)
    assert response.result is None

async def test_stop_neon_companion_app_success(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='',
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=None  # Simulate that the app is no longer running
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_stopped = True

    response = await stop_neon_companion_app(ip_addr, port, wait_until_stopped)

    assert response.timeout_occurred is False
    assert response.result is True

async def test_stop_neon_companion_app_timeout_app_wont_stop(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='',
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=1  # Simulate that the app is still running and won't stop
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_stopped = True
    timeout = 1

    response = await stop_neon_companion_app(ip_addr, port, wait_until_stopped, timeout)

    assert response.timeout_occurred is True
    assert response.result is False

async def test_stop_neon_companion_app_dont_wait(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='',
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=1  # Simulate that the app is still running
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_stopped = False

    response = await stop_neon_companion_app(ip_addr, port, wait_until_stopped)

    assert response.timeout_occurred is False
    assert response.result is None

async def test_start_neon_companion_app_success(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='Starting: Intent { cmp=com.pupillabs.neoncomp/.ui.launch.MainInvisibleActivity }',
        stderr="",
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=123  # Simulate that the app has started and is running
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_started = True

    response = await start_neon_companion_app(ip_addr, port, wait_until_started)

    assert response.timeout_occurred is False
    assert response.result is True

async def test_start_neon_companion_app_app_doesnt_exist(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='',
        stderr='Error type 3\nError: Activity class {com.pupillabs.neoncomp/com.pupillabs.neoncomp.ui.launch.MainInvisibleActivity123} does not exist.',
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=None  # Simulate that the app is still running and won't stop
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_started = True
    timeout = 1

    response = await start_neon_companion_app(ip_addr, port, wait_until_started, timeout)

    assert len(response.error_messages) > 0
    assert response.timeout_occurred is False
    assert response.result is None

async def test_start_neon_companion_app_app_wont_start(monkeypatch):
    mocked_adb_fetch_response = ProcessResponse(
        stdout='',
        stderr='',
        return_code=0,
        timeout_occurred=False,
        error_messages=[],
    )
    mocked_fetch = AsyncMock(return_value=mocked_adb_fetch_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.fetch_adb_command_output",
        mocked_fetch,
    )

    mocked_get_neon_companion_app_task_id_response = SimpleClientResponse(
        timeout_occurred=False,
        error_messages=[],
        result=None  # Simulate that the app won't start
    )
    mocked_get_neon_companion_app_task_id = AsyncMock(return_value=mocked_get_neon_companion_app_task_id_response)
    monkeypatch.setattr(
        "glassesRecord.clients.neon_adb.get_neon_companion_app_task_id",
        mocked_get_neon_companion_app_task_id,
    )

    ip_addr = '192.168.2.123'
    port = 5555
    wait_until_started = True
    timeout = 1

    response = await start_neon_companion_app(ip_addr, port, wait_until_started, timeout)

    assert response.timeout_occurred is True
    assert response.result is None
