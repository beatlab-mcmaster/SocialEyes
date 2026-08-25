from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..clients.adb import (
    check_adb_connection,
    fetch_socialeyes_statistics,
    push_statistics_script,
)
from ..clients.core import SimpleClientResponse
from ..clients.neon_adb import check_red_light_flashing_indicators
from ..clients.neon_http import (
    NeonHardwareIdsResponse,
    get_neon_hardware_ids,
    is_neon_api_accessible,
)
from ..clients.ping import ping_device
from .scripts.statistics_schema import DeviceStatistics

PingDevice = Callable[[str], Awaitable[SimpleClientResponse[int]]]
CheckAdbConnection = Callable[[str, int], Awaitable[SimpleClientResponse[bool]]]
PushScript = Callable[[str, str, str, int], Awaitable[SimpleClientResponse[bool]]]
CheckScript = Callable[[str, str, int], Awaitable[SimpleClientResponse[bool]]]
FetchStatistics = Callable[
    [str, int],
    Awaitable[SimpleClientResponse[DeviceStatistics | None]],
]
CheckApi = Callable[[str], Awaitable[SimpleClientResponse[bool]]]
GetHardwareIds = Callable[[str], Awaitable[NeonHardwareIdsResponse]]
CheckIndicators = Callable[
    [str, int, str, str],
    Awaitable[SimpleClientResponse[bool]],
]

@dataclass
class DeviceClients:
    # Define the clients as callable attributes
    ping_device: PingDevice = ping_device
    check_adb_connection: CheckAdbConnection = check_adb_connection
    push_statistics_script: PushScript = push_statistics_script
    fetch_socialeyes_statistics: FetchStatistics = fetch_socialeyes_statistics
    is_neon_api_accessible: CheckApi = is_neon_api_accessible
    get_neon_hardware_ids: GetHardwareIds = get_neon_hardware_ids
    check_red_light_flashing_indicators: CheckIndicators = check_red_light_flashing_indicators
