import asyncio
from dataclasses import dataclass

import aiohttp

from .core import TIMEOUT_SECONDS, ClientResponse


@dataclass
class HttpResponse(ClientResponse):
    status_code: int | None
    response_text: str | None

async def fetch_http_get_response(url, timeout: float=TIMEOUT_SECONDS) -> HttpResponse:
    """
    Creates a GET request using `url`. If execution exceeds `timeout` (seconds), cancels the request.

    Returns
    -------
    HttpResponse
        - timeout_occurred: True if the request timed out, False otherwise.
        - status_code: The HTTP status code of the response. None if the request failed or timed out.
        - response_text: The text content of the response. None if the request failed or timed out.
    """
    status_code = None
    res = None
    timeout_occurred = False
    errors = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                status_code = response.status
                res = await response.text()
                timeout_occurred = False
    except asyncio.TimeoutError:
        timeout_occurred = True
    except Exception as e:
        errors.append(str(e))

    return HttpResponse(
        status_code=status_code,
        response_text=res,
        timeout_occurred=timeout_occurred,
        error_messages=errors
    )

async def fetch_http_post_response(url, data_json=None, timeout: float=TIMEOUT_SECONDS) -> HttpResponse:
    """
    Creates a POST request using `url` and `data_json`. If execution exceeds `timeout` (seconds), cancels the request.

    Returns
    -------
    HttpResponse
        - timeout_occurred: True if the request timed out, False otherwise.
        - status_code: The HTTP status code of the response. None if the request failed or timed out.
        - response_text: The text content of the response. None if the request failed or timed out.
    """
    status_code = None
    res = None
    timeout_occurred = False
    errors = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, json=data_json) as response:
                status_code = response.status
                res = await response.text()
    except asyncio.TimeoutError:
        timeout_occurred = True
    except Exception as e:
        errors.append(str(e))

    return HttpResponse(
        status_code=status_code,
        response_text=res,
        timeout_occurred=timeout_occurred,
        error_messages=errors
    )