
from dataclasses import dataclass
from .core import ClientResponse

from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator

TIME_ECHO_PORT = 12321

@dataclass
class NeonTimeOffsetResponse(ClientResponse):
    mean_time_offset_ms: float | None
    mean_roundtrip_duration_ms: float | None
    

async def estimate_time_offset(ip_addr: str) -> NeonTimeOffsetResponse:
    response = NeonTimeOffsetResponse(
            timeout_occurred=False,
            error_messages=[],
            mean_time_offset_ms=None,
            mean_roundtrip_duration_ms=None,
        )
    try:
        estimator = TimeOffsetEstimator(ip_addr, port=TIME_ECHO_PORT)
        estimate = await estimator.estimate()
        if estimate is not None:
            response.mean_time_offset_ms = estimate.time_offset_ms.mean
            response.mean_roundtrip_duration_ms = estimate.roundtrip_duration_ms.mean
        else:
            response.error_messages.append(f"Failed to estimate offset for device {ip_addr}!")
    except Exception as e:
        response.error_messages.append(str(e))
    return response