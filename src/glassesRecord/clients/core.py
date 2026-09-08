import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import Generic, TypeVar

TIMEOUT_SECONDS = 5

@dataclass
class ClientResponse:
    timeout_occurred: bool
    error_messages: list[str]

P = TypeVar('P')
@dataclass
class SimpleClientResponse(ClientResponse, Generic[P]):
    """A simple client response that includes a result of type P or None."""
    result: P | None

@dataclass
class ProcessResponse(ClientResponse):
    """Represents the result of executing a command in a subprocess, including the return code, stdout, and stderr."""
    return_code: int | None
    stdout: str | None
    stderr: str | None

async def fetch_command_output(cmd, timeout: float=TIMEOUT_SECONDS) -> ProcessResponse:
    """
    Executes `cmd`. If execution exceeds `timeout` (seconds), kill process.
    If the process is killed due to timeout, the return code will be None, and stdout/stderr will be None.

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
    return bool(command_path)
