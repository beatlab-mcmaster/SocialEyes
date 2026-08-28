import asyncio

from aioresponses import aioresponses

from glassesRecord.clients.http import fetch_http_get_response, fetch_http_post_response


async def test_fetch_http_get_response_success():
    url = "http://192.168.2.101:8080/api/status"
    body = '{"message":"Success","result":[{"data":{"battery_level":100,"battery_state":"OK","device_id":"0123456789abcdef","device_name":"Neon Companion","ip":"192.168.2.101","memory":123456789000,"memory_state":"OK","time_echo_port":12321},"model":"Phone"}]}'
    with aioresponses() as mocked:
        mocked.get(url, 
                   status=200, 
                   body=body
        )
        response = await fetch_http_get_response(url)
    assert response.status_code == 200
    assert response.response_text == body

async def test_fetch_http_get_response_timeout():
    url = "http://192.168.2.101:8080/api/status"
    with aioresponses() as mocked:
        mocked.get(url,
                   exception=asyncio.TimeoutError()
        )
        response = await fetch_http_get_response(url)
    assert response.timeout_occurred is True
    assert response.status_code is None
    assert response.response_text is None

async def test_fetch_http_get_response_server_500():
    url = "http://192.168.2.101:8080/api/status"
    with aioresponses() as mocked:
        mocked.get(url,
                   status=500,
                   body=''
        )
        response = await fetch_http_get_response(url)
    assert response.timeout_occurred is False
    assert response.status_code == 500
    assert response.response_text == ''

async def test_fetch_http_post_response_success():
    url = "http://192.168.2.101:8080/api/recording:start"
    body = '{"message": "Started recording", "result": {"id": "7d75d98e-3198-476b-b27e-0df9a0744aea"}'
    with aioresponses() as mocked:
        mocked.post(url, 
                    status=200, 
                    body=body
        )
        response = await fetch_http_post_response(url, "{}")
    assert response.status_code == 200
    assert response.response_text == body
