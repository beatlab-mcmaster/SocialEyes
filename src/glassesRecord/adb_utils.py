import asyncio
from contextlib import asynccontextmanager
import aiohttp
import logging

import os
import shutil

def verify_path_or_command(user_input: str) -> bool:
    """Checks if the input is an existing path, a system command, or invalid."""
    if os.path.exists(user_input):
        return True    
    command_path = shutil.which(user_input)
    if command_path:
        return True
    return False


async def get_output(cmd, timeout=10) -> tuple[int | None, str | None, str | None]:
    """
    Executes `cmd`. If execution exceeds `timeout` (seconds), kill process.

    Returns
    -------
    tuple
        (return code, stdout, stderr)
    """
    stdout = stderr = None
    rc = None

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
        await process.communicate()
        rc = process.returncode
        
    return rc, stdout, stderr

@asynccontextmanager
async def cmd_wrapper(cmd, ignore_rc=False, timeout=10):
    rc, res, err = await get_output(cmd, timeout=timeout)
    if (err is not None and len(err) > 0) or (not ignore_rc and rc != 0):
        logging.error(f'Executing command `{cmd}` failed: rc={rc}, err={err}')
    else:
        yield(res, rc)

async def get_http(url, timeout=10):
    status_code = None
    res = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                status_code = response.status
                res = await response.text()
    except:
        pass
    return status_code, res