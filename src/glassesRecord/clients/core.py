from dataclasses import dataclass
from typing import TypeVar, Generic
import os
import shutil
import asyncio

TIMEOUT_SECONDS = 5

@dataclass
class ClientResponse:
    timeout_occurred: bool
    error_messages: list[str]

    @property
    def success(self) -> bool:
        """Returns True if the operation was successful (no timeout and no errors)."""
        return not self.timeout_occurred and len(self.error_messages) == 0

P = TypeVar('P')
@dataclass
class SimpleClientResponse(Generic[P], ClientResponse):
    result: P | None

@dataclass
class ProcessResponse(ClientResponse):
    return_code: int | None
    stdout: str | None
    stderr: str | None

async def fetch_command_output(cmd, timeout=TIMEOUT_SECONDS) -> ProcessResponse:
    """
    Executes `cmd`. If execution exceeds `timeout` (seconds), kill process.

    Returns
    -------
    ProcessResponse
    """
    stdout = stderr = None
    rc = None
    timeout_occurred = False

    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        start_new_session=True
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        rc = process.returncode
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        rc = process.returncode
        timeout_occurred = True

    return ProcessResponse(
        return_code=rc,
        stdout=stdout,
        stderr=stderr,
        timeout_occurred=timeout_occurred,
        error_messages=[]
    )

def exists_as_path_or_command(user_input: str) -> bool:
    """Checks if the input is an existing path, a system command, or invalid."""
    if os.path.exists(user_input):
        return True
    command_path = shutil.which(user_input)
    if command_path:
        return True
    return False
