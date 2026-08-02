import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from .core import exists_as_path_or_command, SimpleClientResponse, fetch_command_output
from ..neon.scripts.statistics_schema import DeviceStatistics
import json

ADB_PATH = os.environ.get('ADB_PATH', 'adb')
assert exists_as_path_or_command(ADB_PATH), f"ADB_PATH '{ADB_PATH}' is not a valid path or command"

async def check_adb_connection(ip_addr: str, port: int = 5555) -> SimpleClientResponse[bool]:
    connection_established = None
    timeout_occurred = False
    errors = []
    
    try:
        response = await fetch_command_output(f'{ADB_PATH} devices')
        timeout_occurred = response.timeout_occurred
        errors.extend(response.error_messages)
        connection_established = False
        if response.stdout is not None and len(response.stdout) > 0:
            lines = response.stdout.splitlines()
            connection_established = any(f'{ip_addr}:{port}' in line and 'device' in line for line in lines)
    except Exception as e:
        errors.append(str(e))

    return SimpleClientResponse(
        timeout_occurred=timeout_occurred,
        error_messages=errors,
        result=connection_established
    )

async def fetch_socialeyes_statistics(ip_addr: str, port: int = 5555) -> SimpleClientResponse[DeviceStatistics | None]:
    statistics = None
    response = await fetch_command_output(f'{ADB_PATH} -s {ip_addr}:{port} shell sh /storage/self/primary/Documents/SocialEyes/statistics.sh')
    timeout_occurred = response.timeout_occurred
    errors = response.error_messages.copy()
    if response.return_code == 0:
        try:
            if response.stdout is None or len(response.stdout) == 0:
                errors.append('Received empty output from statistics.sh script')
                
            else:
                statistics = DeviceStatistics.model_validate_json(response.stdout)
        except json.JSONDecodeError as e:
            errors.append(str(e))
    else:
        errors.append(f'Failed to execute statistics.sh script: rc={response.return_code}, res={response.stdout}, err={response.stderr}')

    return SimpleClientResponse(
        timeout_occurred=timeout_occurred,
        error_messages=errors,
        result=statistics
    )

async def check_statistics_script_exists(ip_addr: str, script_path: str, port: int = 5555,) -> SimpleClientResponse[bool]:
    response = await fetch_command_output(f'{ADB_PATH} -s {ip_addr}:{port} shell ls {script_path}')
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages.copy(),
        result=response.return_code == 0
    )

async def push_statistics_script(ip_addr: str, source_path: str, dest_path: str, port: int = 5555) -> SimpleClientResponse[bool]:
    response = await fetch_command_output(f'{ADB_PATH} -s {ip_addr}:{port} push {source_path} {dest_path}')
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages.copy(),
        result=response.return_code == 0
    )

async def connect_adb(ip_addr: str, port: int = 5555) -> SimpleClientResponse[bool]:
    response = await fetch_command_output(f'{ADB_PATH} connect {ip_addr}:{port}')
    timeout_occurred = response.timeout_occurred
    errors = response.error_messages.copy()
    connection_successful = False
    if response.return_code == 0:
        if response.stdout is not None and len(response.stdout) > 0:
            connection_successful = 'connected to' in response.stdout.lower()
        else:
            errors.append('Received empty output from adb connect command')
    else:
        errors.append(f'Failed to execute adb connect command: rc={response.return_code}, res={response.stdout}, err={response.stderr}')

    return SimpleClientResponse(
        timeout_occurred=timeout_occurred,
        error_messages=errors,
        result=connection_successful
    )