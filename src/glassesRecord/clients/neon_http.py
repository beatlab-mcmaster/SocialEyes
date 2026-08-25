import json
from dataclasses import dataclass

from .core import ClientResponse, SimpleClientResponse
from .http import fetch_http_get_response, fetch_http_post_response


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
    """
    Get the hardware IDs of the Neon device.

    Returns
    -------
    NeonHardwareIdsResponse
        A NeonHardwareIdsResponse object containing the device and hardware IDs.
        - device_name: The name of the device (e.g., "Neon Companion").
        - device_id: The unique identifier of the device.
        - frame_name: The name of the frame (if available).
        - module_serial: The serial number of the module (if available).
    """
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
            errors.append(f"JSON decode error: {e!s}")

    return NeonHardwareIdsResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        device_name=device_name,
        device_id=device_id,
        frame_name=frame_name,
        module_serial=module_serial
    )

async def start_neon_recording(ip_addr: str) -> SimpleClientResponse[str | None]:
    """
    Start a recording on the Neon device.
    
    Returns
    -------
    SimpleClientResponse[str | None]
        A SimpleClientResponse object containing the recording ID if successful, or None if not.
    """
    recording_id = None
    response = await fetch_http_post_response(f'http://{ip_addr}:8080/api/recording:start', data_json={})
    errors = response.error_messages.copy()
    if response.status_code == 200 and response.response_text is not None:
        try:
            res_json = json.loads(response.response_text)
            if 'message' in res_json and res_json['message'] == 'Started recording' and 'result' in res_json:
                recording_id = str(res_json['result']['id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {e!s}")
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
            if 'message' in res_json and res_json['message'] == 'Stopped recording' and 'result' in res_json and res_json['result'] is not None and 'id' in res_json['result']:
                # At least in v2.9.31: result = null, so we cannot get the recording ID from the response.
                recording_id = str(res_json['result']['id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {e!s}")
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
            if 'message' in res_json and res_json['message'] == 'Success' and 'result' in res_json and res_json['result'] is not None and 'id' in res_json['result']:
                recording_id = str(res_json['result']['id'])
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {e!s}")
    return SimpleClientResponse(
        timeout_occurred=response.timeout_occurred,
        error_messages=errors,
        result=recording_id
    )
