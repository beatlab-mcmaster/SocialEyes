import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
from adb_utils import subprocess_getoutput

def test_subprocess_getoutput_returns_stdout_without_trailing_newline(monkeypatch):
    expected_output = 'hello world\n'

    def fake_check_output(cmd, shell, text, stderr, encoding, errors, timeout):
        assert cmd == 'echo hello world'
        assert shell is True
        assert text is True
        assert stderr == subprocess.STDOUT
        assert timeout == 10
        return expected_output

    monkeypatch.setattr(subprocess, 'check_output', fake_check_output)

    assert subprocess_getoutput('echo hello world') == 'hello world'


def test_subprocess_getoutput_returns_calledprocesserror_output(monkeypatch):
    expected_output = 'command failed'

    class FakeCalledProcessError(subprocess.CalledProcessError):
        pass

    def fake_check_output(cmd, shell, text, stderr, encoding, errors, timeout):
        raise FakeCalledProcessError(returncode=1, cmd=cmd, output=expected_output)

    monkeypatch.setattr(subprocess, 'check_output', fake_check_output)

    assert subprocess_getoutput('somecommand') == expected_output


def test_subprocess_getoutput_forwards_timeout(monkeypatch):
    recorded = {}

    def fake_check_output(cmd, shell, text, stderr, encoding, errors, timeout):
        recorded['timeout'] = timeout
        return 'ok\n'

    monkeypatch.setattr(subprocess, 'check_output', fake_check_output)

    assert subprocess_getoutput('echo ok', timeout=123) == 'ok'
    assert recorded['timeout'] == 123
