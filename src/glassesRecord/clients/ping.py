import os
import re

from .core import TIMEOUT_SECONDS, SimpleClientResponse, fetch_command_output

PING_PATTERN_WINDOWS = re.compile(r'time=([0-9.]+)ms TTL=\d+')
PING_PATTERN = re.compile(r'ttl=\d+\s+time=([0-9.]+)\s+ms')

def is_windows() -> bool:
    return os.name == 'nt'

async def ping_device(ip_addr: str, timeout=TIMEOUT_SECONDS) -> SimpleClientResponse[int]:
    """
    Determines if a device is reachable by pinging it.

    Returns
    -------
    SimpleClientResponse[int]: Contains the average ping time in milliseconds if successful, or None if not reachable.
    """
    ping = None
    
    ping_command = f'ping /n 1 {ip_addr}' if is_windows() else f'ping -c 1 {ip_addr}'
    ping_pattern = PING_PATTERN_WINDOWS if is_windows() else PING_PATTERN
    
    response = await fetch_command_output(ping_command, timeout=timeout)
    errors = response.error_messages
    if response.return_code == 0 and response.stdout is not None and len(response.stdout) > 0:
        re_search = ping_pattern.findall(response.stdout)
        if re_search is not None and len(re_search) > 0:
            times = [float(e) for e in re_search]
            ping = int(sum(times) / len(times))
        else:
            errors.append(f'Ping command executed but no valid time found in output: {response.stdout}')

    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        result=ping
    )