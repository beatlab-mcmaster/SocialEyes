import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from dataclasses import dataclass
from typing import Callable

from ..clients.ping import ping_device
from ..clients.adb import check_adb_connection, check_statistics_script_exists, push_statistics_script, fetch_socialeyes_statistics
from ..clients.neon_http import is_neon_api_accessible, get_neon_hardware_ids
from ..clients.neon_adb import check_red_light_flashing_indicators

@dataclass
class DeviceClients:
    # Define the clients as callable attributes
    ping_device: Callable = ping_device
    check_adb_connection: Callable = check_adb_connection
    check_statistics_script_exists: Callable = check_statistics_script_exists
    push_statistics_script: Callable = push_statistics_script
    fetch_socialeyes_statistics: Callable = fetch_socialeyes_statistics
    is_neon_api_accessible: Callable = is_neon_api_accessible
    get_neon_hardware_ids: Callable = get_neon_hardware_ids
    check_red_light_flashing_indicators: Callable = check_red_light_flashing_indicators
