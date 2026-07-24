import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.dirname(__file__))
from adb_utils import get_output

@pytest.mark.asyncio
async def test_get_output_returns_rc_stdout_and_stderr(monkeypatch):
    stdout_data = 'test-stdout'.encode()
    stderr_data = 'test-stderr'.encode()
    returncode  = 123
    
    async def fake_communicate(self, input=None):
        return (stdout_data, stderr_data)
    
    fake_returncode = returncode

    monkeypatch.setattr(asyncio.subprocess.Process, 'communicate', fake_communicate)
    monkeypatch.setattr(asyncio.subprocess.Process, 'returncode', fake_returncode)

    res = await get_output("some command")
    rc, stdout, stderr = res

    assert rc == returncode
    assert stdout == stdout_data.decode()
    assert stderr == stderr_data.decode()

@pytest.mark.asyncio
async def test_get_output_implements_timeout(monkeypatch):
    stdout_data = 'test-stdout'.encode()
    stderr_data = 'test-stderr'.encode()
    timeout = 1
    
    async def fake_communicate(self, input=None):
        await asyncio.sleep(timeout * 2) # Trigger timeout
        return (stdout_data, stderr_data)
    
    monkeypatch.setattr(asyncio.subprocess.Process, 'communicate', fake_communicate)

    res = await get_output("some command", timeout=timeout)
    rc, stdout, stderr = res
    assert rc == 127 # killed
