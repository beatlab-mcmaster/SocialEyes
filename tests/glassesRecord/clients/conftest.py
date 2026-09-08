import pytest


@pytest.fixture
def adb_devices_response():
    """
    Fixture that returns a mock response for the 'adb devices' command.
    The mock response simulates the output of the command, indicating that the specified devices are connected.
    
    Returns
    -------
    function
        A function that takes a list of connected devices (e.g., "192.168.2.123:5555") and returns a mock response object.
    """
    def create_response(connected_ip_addr_ports: list[str]):
        class MockResponse:
            def __init__(self, connected_ip_addr_ports: list[str]):
                devices = [f"{d}\t device\n" for d in connected_ip_addr_ports]
                self.stdout = "List of devices attached\n{}\n".format("".join(devices))
                self.stderr = ""
                self.return_code = 0
                self.timeout_occurred = False
                self.error_messages = []

        return MockResponse(connected_ip_addr_ports)
    return create_response

@pytest.fixture
def adb_run_socialeyes_statistics_script_response():
    """
    Fixture that returns a mock response for running the SocialEyes statistics script on the device.
    The mock response simulates the output of the script, returning a JSON string representing device statistics.
    
    Returns
    -------
    function
        A function that takes a JSON string representing device statistics and returns a mock response object.
    """
    def create_response(statistics_json: str, timeout_occurred: bool = False):
        class MockResponse:
            def __init__(self, statistics_json: str):
                self.stdout = statistics_json
                self.stderr = ""
                self.return_code = 0
                self.timeout_occurred = timeout_occurred
                self.error_messages = []

        return MockResponse(statistics_json)
    return create_response
