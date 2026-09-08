from unittest.mock import Mock

from glassesRecord.monitoring.device import Device, DeviceState, NeonHardwareIDs
from glassesRecord.monitoring.recording_state import RecordingState


def test_device_initialization_succeeds():
    ip_addr = "192.168.2.123"
    device = Device(ip_addr=ip_addr)

    assert device is not None
    assert device.latest_state is None
    assert device.previous_state is None
    assert device.active_recordings is None
    assert device._statistics_script_pushed is False

async def test_device_poll_once(fake_device_clients):
    ip_addr = "192.168.2.123"
    neon_hardware_ids = NeonHardwareIDs(
        device_name="Neon Companion",
        device_id="device-id",
        frame_name="Frame",
        module_serial="serial",
    )
    ping_device_result = 110
    check_adb_connection_result = True
    push_statistics_script_result = True
    fetch_socialeyes_statistics_result = None
    is_neon_api_accessible_result = True
    get_neon_hardware_ids_result = neon_hardware_ids
    fdc = fake_device_clients(
        ping_device_result=ping_device_result,
        check_adb_connection_result=check_adb_connection_result,
        push_statistics_script_result=push_statistics_script_result,
        fetch_socialeyes_statistics_result=fetch_socialeyes_statistics_result,
        is_neon_api_accessible_result=is_neon_api_accessible_result,
        get_neon_hardware_ids_result=get_neon_hardware_ids_result,
        check_red_light_flashing_indicators_result=False,
    )
    device = Device(ip_addr=ip_addr, clients=fdc)

    state = await device._poll_once()

    assert state.ip_addr == ip_addr
    assert state.now.tzinfo is not None
    assert state.ping == ping_device_result
    assert state.adb_connection_is_established == check_adb_connection_result
    assert state.neon_api_is_available == is_neon_api_accessible_result
    assert state.neon_hardware_ids == get_neon_hardware_ids_result
    assert state.active_recordings is None
    assert state.latest_statistics is None

def test_record_state_updates_history():
    device = Device(ip_addr="192.168.2.123")
    first = DeviceState(ip_addr="192.168.2.123", ping=100)
    second = DeviceState(ip_addr="192.168.2.123", ping=123)

    device._record_state(first)
    device._record_state(second)

    assert device.latest_state is second
    assert device.previous_state is first

def test_state_history_keeps_only_specified_number_of_states():
    history_max_length = 5
    device = Device(ip_addr="192.168.2.123", history_max_length=history_max_length)
    states = [
        DeviceState(ip_addr="192.168.2.123", ping=i * 100)
        for i in range(history_max_length + 1) # one more than the max length to test the history limit
    ]

    for state in states:
        device._record_state(state)

    assert len(device._state_history) == history_max_length
    assert device.latest_state is states[history_max_length]
    assert device.previous_state is states[history_max_length - 1]

def test_record_state_notifies_observer():
    observer = Mock()
    device = Device(ip_addr="192.168.2.123", on_change=observer)
    
    state = DeviceState(ip_addr="192.168.2.123")
    device._record_state(state)

    observer.assert_called_once_with(state)

async def test_poll_once_does_not_push_script_when_device_is_unreachable(
    fake_device_clients,
):
    clients = fake_device_clients(
        ping_device_result=None,
        check_adb_connection_result=False,
    )
    device = Device("192.168.2.123", clients=clients)

    await device._poll_once()

    clients.push_statistics_script.assert_not_awaited()

async def test_poll_once_pushes_script_for_connected_device(fake_device_clients):
    clients = fake_device_clients(
        ping_device_result=100,
        check_adb_connection_result=True,
        push_statistics_script_result=True,
    )
    device = Device("192.168.2.123", clients=clients)

    await device._poll_once()

    clients.push_statistics_script.assert_awaited_once()
    assert device._statistics_script_pushed is True

async def test_poll_once_pushes_script_only_once(fake_device_clients):
    clients = fake_device_clients(
        ping_device_result=100,
        check_adb_connection_result=True,
        push_statistics_script_result=True,
    )
    device = Device("192.168.2.123", clients=clients)

    await device._poll_once()
    await device._poll_once()

    clients.push_statistics_script.assert_awaited_once()

async def test_failed_script_push_is_retried(fake_device_clients):
    clients = fake_device_clients(
        ping_device_result=100,
        check_adb_connection_result=True,
        push_statistics_script_result=False,
    )
    device = Device("192.168.2.123", clients=clients)

    await device._poll_once()
    await device._poll_once()

    assert device._statistics_script_pushed is False
    assert clients.push_statistics_script.await_count == 2

async def test_start_creates_background_task(fake_device_clients):
    device = Device("192.168.2.123", clients=fake_device_clients())

    await device.start()

    assert device._background_task is not None
    assert device._background_task.done() is False

    await device.stop()

async def test_stop_completes_background_task(fake_device_clients):
    device = Device("192.168.2.123", clients=fake_device_clients())

    await device.start()
    task = device._background_task

    await device.stop()

    assert task is not None
    assert task.done() is True
