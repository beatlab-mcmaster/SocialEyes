import asyncio
import aiohttp
import logging
    
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
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        rc = process.returncode
    except asyncio.TimeoutError:
        logging.error(f"Command '{cmd}' timed out.")
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.communicate()
        rc = process.returncode
        
    return rc, stdout, stderr

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