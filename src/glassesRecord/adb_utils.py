import subprocess

def subprocess_getoutput(cmd, *, encoding=None, errors=None, timeout=10):
    """
    Patched version of subprocess.getoutput(...), now incorporating a timeout (default: 10 seconds).

    Runs `cmd` and returns its output, ignoring errors.
    """
    try:
        data = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT,
                            encoding=encoding, errors=errors, timeout=timeout)
        exitcode = 0
    except subprocess.CalledProcessError as ex:
        data = ex.output
        exitcode = ex.returncode
    if data[-1:] == '\n':
        data = data[:-1]
    #return exitcode, data
    return data