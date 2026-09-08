
import asyncio
import logging
from dataclasses import dataclass

from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator

# Suppress verbose logging from the PL Realtime API
logging.getLogger('pupil_labs.realtime_api.time_echo').setLevel(logging.ERROR)

from .core import TIMEOUT_SECONDS, ClientResponse

TIME_ECHO_PORT = 12321

@dataclass
class NeonTimeOffsetResponse(ClientResponse):
    mean_time_offset_ms: float | None
    mean_roundtrip_duration_ms: float | None
    

async def estimate_time_offset(ip_addr: str, port: int = TIME_ECHO_PORT, timeout=TIMEOUT_SECONDS) -> NeonTimeOffsetResponse:
    """
    Estimate the time offset between the local system and a Neon device using the Pupil Labs' TimeOffsetEstimator.

    Returns
    -------
    NeonTimeOffsetResponse
        A response object containing the mean time offset and mean roundtrip duration in milliseconds, along with any error messages.
        - mean_time_offset_ms: The estimated mean time offset in milliseconds, or None if the estimation failed.
        - mean_roundtrip_duration_ms: The estimated mean roundtrip duration in milliseconds, or None if the estimation failed.
        - error_messages: A list of error messages encountered during the estimation process
    """
    response = NeonTimeOffsetResponse(
        timeout_occurred=False,
        error_messages=[],
        mean_time_offset_ms=None,
        mean_roundtrip_duration_ms=None,
    )
    try:
        estimator = TimeOffsetEstimator(ip_addr, port=port)
        estimate = await asyncio.wait_for(estimator.estimate(), timeout=timeout)
        if estimate is not None:
            response.mean_time_offset_ms = estimate.time_offset_ms.mean
            response.mean_roundtrip_duration_ms = estimate.roundtrip_duration_ms.mean
        else:
            response.error_messages.append(f"Failed to estimate offset for device {ip_addr}!")
    except asyncio.TimeoutError:
        response.timeout_occurred = True
    except Exception as e:
        response.error_messages.append(f"Error estimating offset for device {ip_addr}: {e!s}")
    return response