import json
import os

import pydantic

from ..monitoring.scripts.statistics_schema import DeviceStatistics
from .core import (
    TIMEOUT_SECONDS,
    ProcessResponse,
    SimpleClientResponse,
    fetch_command_output,
)


def get_default_adb_path() -> str:
    return os.environ.get('ADB_PATH', 'adb')

async def fetch_adb_command_output(cmd, timeout=TIMEOUT_SECONDS) -> ProcessResponse:
    """
    Fetches the output of an ADB command.

    Parameters
    ----------
    cmd : str
        The ADB command to execute. Omit the 'adb' prefix; it will be added automatically.
    timeout : int
        The maximum time to wait for the command to complete, in seconds.

    Returns
    -------
    ProcessResponse
        The result of executing the command, including stdout, stderr, and return code.
    """
    return await fetch_command_output(f'{get_default_adb_path()} {cmd}', timeout=timeout)

async def check_adb_connection(ip_addr: str, port: int = 5555) -> SimpleClientResponse[bool]:
    """
    Checks if an ADB connection to the specified IP address and port is established.
    
    Returns
    -------
    SimpleClientResponse[bool]
        A response object containing:
        - timeout_occurred: True if the command timed out, False otherwise.
        - error_messages: A list of error messages encountered during the check operation.
        - result: True if the connection is established, False otherwise.
    """
    connection_established = None
    timeout_occurred = False
    errors = []
    
    try:
        response = await fetch_adb_command_output('devices')
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
    """
    Fetches the SocialEyes statistics from the device at the specified IP address and port.
    
    Returns
    -------
    SimpleClientResponse[DeviceStatistics | None]
        A response object containing:
        - timeout_occurred: True if the command timed out, False otherwise.
        - error_messages: A list of error messages encountered during the fetch operation.
        - result: A DeviceStatistics object if the fetch was successful, None otherwise.
    """
    statistics = None
    response = await fetch_adb_command_output(f'-s {ip_addr}:{port} shell sh /storage/self/primary/Documents/SocialEyes/statistics.sh')
    timeout_occurred = response.timeout_occurred
    errors = response.error_messages.copy()
    if response.return_code == 0 and not timeout_occurred:
        try:
            if response.stdout is None or len(response.stdout) == 0:
                errors.append('Received empty output from statistics.sh script')
                
            else:
                statistics = DeviceStatistics.model_validate_json(response.stdout)
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            errors.append(str(e))
    else:
        errors.append(f'Failed to execute statistics.sh script: rc={response.return_code}, res={response.stdout}, err={response.stderr}')

    return SimpleClientResponse(
        timeout_occurred=timeout_occurred,
        error_messages=errors,
        result=statistics
    )

async def check_statistics_script_exists(ip_addr: str, script_path: str, port: int = 5555) -> SimpleClientResponse[bool]:
    response = await fetch_adb_command_output(f'-s {ip_addr}:{port} shell ls {script_path}')
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages.copy(),
        result=response.return_code == 0
    )

async def push_statistics_script(ip_addr: str, source_path: str, dest_path: str, port: int = 5555) -> SimpleClientResponse[bool]:
    """
    Pushes the SocialEyes statistics script to the device at the specified IP address and port.

    Returns
    -------
    SimpleClientResponse[bool]
        A response object containing:
        - timeout_occurred: True if the command timed out, False otherwise.
        - error_messages: A list of error messages encountered during the push operation.
        - result: True if the push was successful, False otherwise.
    """
    response = await fetch_adb_command_output(f'-s {ip_addr}:{port} push {source_path} {dest_path}')
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages.copy(),
        result=response.return_code == 0
    )

async def connect_adb(ip_addr: str, port: int = 5555) -> SimpleClientResponse[bool]:
    """
    Connects to the specified IP address and port using ADB.
    
    Returns
    -------
    SimpleClientResponse[bool]
        A response object containing:
        - timeout_occurred: True if the command timed out, False otherwise.
        - error_messages: A list of error messages encountered during the connection attempt.
        - result: True if the connection was successful, False otherwise.
    """
    response = await fetch_adb_command_output(f'connect {ip_addr}:{port}')
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