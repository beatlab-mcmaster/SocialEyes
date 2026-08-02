import re
from dataclasses import dataclass
import json
import asyncio
import datetime

from .adb import ADB_PATH
from .http import fetch_http_get_response, fetch_http_post_response
from .core import ClientResponse, SimpleClientResponse, fetch_command_output, TIMEOUT_SECONDS

NEON_COMPANION_APP_PACKAGE_NAME = "com.pupillabs.neoncomp"
TASK_ID_PATTERN = re.compile(r"taskId=(\d+): com.pupillabs.neoncomp")

async def is_neon_api_accessible(ip_addr: str) -> SimpleClientResponse[bool]:
    neon_api_is_available = None
    
    response = await fetch_http_get_response(f'http://{ip_addr}:8080/api/status', timeout=10)
    neon_api_is_available = response.status_code == 200

    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=response.error_messages,
        result=neon_api_is_available
    )

@dataclass
class NeonHardwareIdsResponse(ClientResponse):
    device_name: str | None
    device_id: str | None
    frame_name: str | None
    module_serial: str | None

async def get_neon_hardware_ids(ip_addr: str) -> NeonHardwareIdsResponse:
    device_name = None
    device_id = None
    frame_name = None
    module_serial = None
    
    response = await fetch_http_get_response(f'http://{ip_addr}:8080/api/status', timeout=10)
    errors = response.error_messages.copy()
    if response.status_code == 200 and response.response_text is not None:
        try:
            res_json = json.loads(response.response_text)
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
                for e in res_json['result']:
                    e_model = e['model']
                    e_data  = e['data']
                    if e_model == 'Phone':
                        device_name = str(e_data['device_name'])
                        device_id = str(e_data['device_id'])
                    elif e_model == 'Hardware':
                        frame_name = str(e_data['frame_name'])
                        module_serial = str(e_data['module_serial'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {str(e)}")

    return NeonHardwareIdsResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        device_name=device_name,
        device_id=device_id,
        frame_name=frame_name,
        module_serial=module_serial
    )

async def check_red_light_flashing_indicators(ip_addr: str, port: int, workspace_id: str, recording_id: str) -> SimpleClientResponse[bool]:
    indicator_detected = None
        
    response = await fetch_command_output(
        f'{ADB_PATH} -s {ip_addr}:{port} shell grep -e "raw has not changed" /storage/self/primary/Documents/Neon/{workspace_id}/{recording_id}/android.log'
    )
    if response.stdout is not None and len(response.stdout) > 0:
        for line in response.stdout.splitlines():
            re_search = re.search(fr'(\d+-\d+ \d+:\d+:\d+.\d+).+({recording_id}.+)raw has not changed.+last size: (\d+)', line)
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
    response = await fetch_command_output(
        f'{ADB_PATH} -s {ip_addr}:{port} shell am stack list | grep {NEON_COMPANION_APP_PACKAGE_NAME}'
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

async def stop_neon_companion_app(ip_addr: str, port: int, wait_until_stopped=True) -> SimpleClientResponse[bool]:
    stopped = None # None = maybe
    response = await fetch_command_output(
        f'{ADB_PATH} -s {ip_addr}:{port} shell am force-stop {NEON_COMPANION_APP_PACKAGE_NAME}'
    )
    timeout_occurred = response.timeout_occurred
    if wait_until_stopped:
        neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
        now = datetime.datetime.now()
        while True:
            if (datetime.datetime.now() - now).total_seconds() > TIMEOUT_SECONDS:
                timeout_occurred = True
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

async def start_neon_companion_app(ip_addr: str, port: int, wait_until_started=True) -> SimpleClientResponse[bool]:
    started = None # None = maybe
    response = await fetch_command_output(
        f'{ADB_PATH} -s {ip_addr}:{port} shell am start -n {NEON_COMPANION_APP_PACKAGE_NAME}/com.pupillabs.neoncomp.ui.launch.MainInvisibleActivity'
    )
    timeout_occurred = response.timeout_occurred
    if wait_until_started:
        neon_task_id = (await get_neon_companion_app_task_id(ip_addr, port)).result
        now = datetime.datetime.now()
        while True:
            if (datetime.datetime.now() - now).total_seconds() > TIMEOUT_SECONDS:
                timeout_occurred = True
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

async def start_neon_recording(ip_addr: str) -> SimpleClientResponse[str | None]:
    recording_id = None
    response = await fetch_http_post_response(f'http://{ip_addr}:8080/api/recording:start', data_json={})
    errors = response.error_messages.copy()
    if response.status_code == 200 and response.response_text is not None:
        try:
            res_json = json.loads(response.response_text)
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
                recording_id = str(res_json['result']['recording_id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {str(e)}")
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        result=recording_id
    )

async def stop_and_save_neon_recording(ip_addr: str) -> SimpleClientResponse[str | None]:
    recording_id = None
    response = await fetch_http_post_response(f'http://{ip_addr}:8080/api/recording:stop_and_save', data_json={})
    errors = response.error_messages.copy()
    if response.status_code == 200 and response.response_text is not None:
        try:
            res_json = json.loads(response.response_text)
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
                recording_id = str(res_json['result']['recording_id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {str(e)}")
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        result=recording_id
    )

async def cancel_neon_recording(ip_addr: str) -> SimpleClientResponse[str | None]:
    recording_id = None
    response = await fetch_http_post_response(f'http://{ip_addr}:8080/api/recording:cancel', data_json={})
    errors = response.error_messages.copy()
    if response.status_code == 200 and response.response_text is not None:
        try:
            res_json = json.loads(response.response_text)
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json:
                recording_id = str(res_json['result']['recording_id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {str(e)}")
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        result=recording_id
    )