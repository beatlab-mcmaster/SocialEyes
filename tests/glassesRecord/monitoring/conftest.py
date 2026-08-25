from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from glassesRecord.clients.core import SimpleClientResponse
from glassesRecord.clients.neon_http import NeonHardwareIdsResponse
from glassesRecord.monitoring.device_clients import DeviceClients


@pytest.fixture
def fake_device_clients() -> Callable[..., DeviceClients]:
    def create_fake_device_clients(
        ping_device_result: int = 110,
        check_adb_connection_result: bool = True,
        push_statistics_script_result: bool = False,
        fetch_socialeyes_statistics_result: None = None,
        is_neon_api_accessible_result: bool = True,
        get_neon_hardware_ids_result: NeonHardwareIdsResponse | None = None,
        check_red_light_flashing_indicators_result: bool = False,
    ) -> DeviceClients:
        return DeviceClients(
            ping_device=AsyncMock(
                return_value=SimpleClientResponse(
                    result=ping_device_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            check_adb_connection=AsyncMock(
                return_value=SimpleClientResponse(
                    result=check_adb_connection_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            push_statistics_script=AsyncMock(
                return_value=SimpleClientResponse(
                    result=push_statistics_script_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            fetch_socialeyes_statistics=AsyncMock(
                return_value=SimpleClientResponse(
                    result=fetch_socialeyes_statistics_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            is_neon_api_accessible=AsyncMock(
                return_value=SimpleClientResponse(
                    result=is_neon_api_accessible_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            get_neon_hardware_ids=AsyncMock(
                return_value=get_neon_hardware_ids_result or NeonHardwareIdsResponse(
                    device_name="Neon Companion",
                    device_id="device-id",
                    frame_name="Frame",
                    module_serial="serial",
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
            check_red_light_flashing_indicators=AsyncMock(
                return_value=SimpleClientResponse(
                    result=check_red_light_flashing_indicators_result,
                    timeout_occurred=False,
                    error_messages=[],
                )
            ),
        )
    return create_fake_device_clients