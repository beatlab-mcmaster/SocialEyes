import asyncio
import datetime
import re

from ..clients.adb import fetch_adb_command_output
from .core import TIMEOUT_SECONDS, SimpleClientResponse

NEON_COMPANION_APP_PACKAGE_NAME = "com.pupillabs.neoncomp"
TASK_ID_PATTERN = re.compile(r"taskId=(\d+): com.pupillabs.neoncomp")

async def check_red_light_flashing_indicators(ip_addr: str, port: int, workspace_id: str, recording_id: str) -> SimpleClientResponse[bool]:
    """
    Check if the red light flashing indicator is present in the logs of the Neon recording.
    
    Returns
    -------
    SimpleClientResponse[bool]
        - result: True if the indicator is present, False if not.
    """
    indicator_detected = False
        
    response = await fetch_adb_command_output(
        f'-s {ip_addr}:{port} shell grep -e "raw has not changed" /storage/self/primary/Documents/Neon/{workspace_id}/{recording_id}/android.log'
    )
    if response.stdout is not None and len(response.stdout) > 0:
        for line in response.stdout.splitlines():
            re_search = re.search(r'\.raw has not changed.+last size: (\d+)', line)
            if re_search is not None:
                indicator_detected = True
                break

    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=[],
        result=indicator_detected
    )

async def get_neon_companion_app_task_id(ip_addr: str, port: int) -> SimpleClientResponse[int | None]:
    task_id = None
    response = await fetch_adb_command_output(
        f'-s {ip_addr}:{port} shell am stack list | grep {NEON_COMPANION_APP_PACKAGE_NAME}'
    )
    if response.stdout is not None and len(response.stdout) > 0:
        matches = TASK_ID_PATTERN.search(response.stdout)
        if matches is not None and len(matches.groups()) > 0:
            task_id = int(matches.group(1))
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages,
        result=task_id
    )

async def stop_neon_companion_app(ip_addr: str, port: int, wait_until_stopped=True, timeout=TIMEOUT_SECONDS) -> SimpleClientResponse[bool]:
    """
    Stop the Neon Companion App on the device.
    
    Returns
    -------
    SimpleClientResponse[bool]
        - result: True if the app was stopped, False if not (within `timeout` seconds), None if maybe (wait_until_stopped=False)"""
    stopped = None # None = maybe
    response = await fetch_adb_command_output(
        f'-s {ip_addr}:{port} shell am force-stop {NEON_COMPANION_APP_PACKAGE_NAME}'
    )
    timeout_occurred = response.timeout_occurred
    if wait_until_stopped:
        neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
        now = datetime.datetime.now()
        while True:
            if (datetime.datetime.now() - now).total_seconds() > timeout:
                timeout_occurred = True
                stopped = False
                break
            neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
            if neon_task_id is None:
                stopped = True
                break
            await asyncio.sleep(0.5)
        
    return SimpleClientResponse(
        timeout_occurred=timeout_occurred,
        error_messages=response.error_messages,
        result=stopped if wait_until_stopped else None
    )

async def start_neon_companion_app(ip_addr: str, port: int, wait_until_started=True, timeout=TIMEOUT_SECONDS) -> SimpleClientResponse[bool]:
    """
    Start the Neon Companion App on the device.
    
    Returns
    -------
    SimpleClientResponse[bool]
        - result: True if the app was started, False if not (within `timeout` seconds), None if maybe (wait_until_started=False)
    """
    started = None # None = maybe
    response = await fetch_adb_command_output(
        f'-s {ip_addr}:{port} shell am start -n {NEON_COMPANION_APP_PACKAGE_NAME}/com.pupillabs.neoncomp.ui.launch.MainInvisibleActivity'
    )
    if response.stderr is not None and len(response.stderr) > 0:
        return SimpleClientResponse(
            timeout_occurred=response.timeout_occurred,
            error_messages=[response.stderr],
            result=None
        )
    else:
        timeout_occurred = response.timeout_occurred
        if wait_until_started:
            neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
            now = datetime.datetime.now()
            while True:
                if (datetime.datetime.now() - now).total_seconds() > timeout:
                    timeout_occurred = True
                    started = None
                    break
                neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
                if neon_task_id is not None:
                    started = True
                    break
                await asyncio.sleep(0.5)
            
        return SimpleClientResponse(
            timeout_occurred=timeout_occurred,
            error_messages=response.error_messages,
            result=started
        )
