import sys

from glassesRecord.clients.core import exists_as_path_or_command, fetch_command_output


async def test_fetch_command_output_success():
    """Test that fetch_command_output returns a successful ProcessResponse for a simple command."""
    sys_executable = sys.executable
    cmd = f'{sys_executable} -c "print(\'Hello, World!\')"'
    response = await fetch_command_output(cmd)

    assert response.return_code == 0
    assert response.stdout == "Hello, World!"
    assert response.stderr == ""

async def test_fetch_command_output_with_an_invalid_command():
    cmd = "not_existing_command_123qwerty"
    response = await fetch_command_output(cmd)

    assert response.return_code != 0
    assert response.stdout == ""
    assert response.stderr is not None and ("not found" in response.stderr.lower() or "is not recognized" in response.stderr.lower())

async def test_fetch_command_output_return_code():
    sys_executable = sys.executable
    cmd = f'{sys_executable} -c "import sys; sys.exit(123)"'
    response = await fetch_command_output(cmd)

    assert response.return_code == 123

async def test_fetch_command_output_timeout():
    sys_executable = sys.executable
    cmd = f'{sys_executable} -c "import time; time.sleep(5)"'
    response = await fetch_command_output(cmd, timeout=1)

    assert response.timeout_occurred is True
    assert response.return_code != 0
    assert response.stdout is None
    assert response.stderr is None

async def test_fetch_command_output_timeout_2():
    sys_executable = sys.executable
    cmd = f'{sys_executable} -c "import time; print(\'abc123\'); time.sleep(5)"'
    response = await fetch_command_output(cmd, timeout=1)

    assert response.timeout_occurred is True
    assert response.return_code != 0
    # TODO can we capture stdout/stderr even if the process is killed due to timeout? If so, we should update the test and the implementation accordingly.
    assert response.stdout is None
    assert response.stderr is None

def test_exists_as_path_or_command_success(tmp_path):
    # Create a temporary file to test the path check
    temp_file = tmp_path / "temp_file.txt"
    temp_file.write_text("Temporary file content")

    non_existing_path = str(tmp_path / "non_existing_file.txt")
    non_existing_command = "non_existing_command_123qwerty"

    # Test with an existing path
    assert exists_as_path_or_command(str(temp_file)) is True
    # Test with a non-existing path
    assert exists_as_path_or_command(non_existing_path) is False    

    # Test with a valid command (assuming 'python' is available in the environment)
    assert exists_as_path_or_command(sys.executable) is True
    # Test with a non-existing command
    assert exists_as_path_or_command(non_existing_command) is False
