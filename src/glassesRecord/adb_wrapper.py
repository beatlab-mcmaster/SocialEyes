"""
adb_wrapper.py

Author: Alexander Nguyen, Shreshth Saxena
Purpose: AdbWrapper uses adb (android debug bridge) to remotely execute commands on Android phones. It provides functionality to force-stop and start the Neon Companion App.
"""

import subprocess
import re
from datetime import datetime, timedelta
import time

class AdbWrapper:
    def __init__(self, ip_addr: str, port: int=5555) -> None:
        """
        Initializes the AdbWrapper with the given IP address and port.

        Args:
            ip_addr (str): The IP address of the ADB device.
            port (int, optional): The port number of the ADB device. Defaults to 5555.

        """
        # ip_addr: ipv4
        self.ip_addr = ip_addr
        self.port    = port
        
        self._assert_parameters_are_valid()
        self._assert_target_is_available()

    def _assert_target_is_available(self):
        """
        Checks if the ADB device is available by running a simple echo command.
        """
        res = self._run_adb_shell_command("echo 123", assert_target_is_available=False)
        if res != "123":
            raise Exception("Adb device {}:{} is not available!".format(self.ip_addr, self.port))
        
    def _assert_parameters_are_valid(self):
        """
        Validates the provided IP address and port number.
        """
        if re.search("\d{3}\.\d{3}\.\d{3}\.\d{3}", self.ip_addr) is not None:
            raise Exception("Adb ip_addr must be an IPv4 address!")
        if not isinstance(self.port, int) and self.port > 0:
            raise Exception("Adb port must be a positve integer!")

    def _adb_shell_command(self, cmd: str) -> str:
        """
        Constructs the ADB shell command string.

        Args:
            cmd (str): The command to be executed on the ADB device.
        
        Returns:
            str: The constructed ADB shell command string.
        """
        return "adb -s {}:{} shell {}".format(self.ip_addr, self.port, cmd)
    
    def _run_adb_shell_command(self, cmd: str, strip_stdout=True, assert_target_is_available=True) -> str:
        """
        Executes the ADB shell command and returns the output.

        Args:
            cmd (str): The command to be executed on the ADB device.
            strip_stdout (bool, optional): Whether to strip leading and trailing whitespace from the command output. Defaults to True.
            assert_target_is_available (bool, optional): Whether to check if the ADB device is available before running the command. Defaults to True.

        Returns:
            str: The output from the command execution.
        """
        if assert_target_is_available:
            self._assert_target_is_available()
        res = subprocess.run(self._adb_shell_command(cmd), shell=True, capture_output=True, text=True).stdout
        if strip_stdout:
            res = res.strip()
        return res

    
    
    def stop_neon_companion_app(self, wait_until_stopped=True, timeout_ms=6000):
        """Force-stop Neon Companion app. 

        Parameters
        ----------
        wait_until_stopped : bool, optional
            If True, this function will block until the app disappears from the tasks list (using ADB's "am stack list" command), by default True
        timeout_ms : int, optional
            If wait_until_stopped is True, this function will block no more than the time specified by this value, by default 6000

        Raises
        ------
        Exception
            If target device is not available
        """              
        self._run_adb_shell_command("am force-stop com.pupillabs.neoncomp")
        start_time = datetime.now()
        if wait_until_stopped:
            neon_task_id = self._get_neon_companion_task_id()
            while neon_task_id is not None and (datetime.now() - start_time) < timedelta(milliseconds=timeout_ms):
                neon_task_id = self._get_neon_companion_task_id()
                time.sleep(0.1)

    def start_neon_companion_app(self, wait_until_started=True, timeout_ms=6000):
        """Start Neon Companion app. If it was already running on the device, nothing will happen.

        Parameters
        ----------
        wait_until_started : bool, optional
            If True, this function will block until the app appears on the tasks list (using ADB's "am stack list" command), by default True
        timeout_ms : int, optional
            If wait_until_started is True, this function will block no more than the time specified by this value, by default 6000

        Raises
        ------
        Exception
            If target device is not available
        """        
        self._run_adb_shell_command("am start -n com.pupillabs.neoncomp/com.pupillabs.neoncomp.ui.launch.MainInvisibleActivity")
        start_time = datetime.now()
        if wait_until_started:
            neon_task_id = self._get_neon_companion_task_id()
            while neon_task_id is not None and (datetime.now() - start_time) < timedelta(milliseconds=timeout_ms):
                neon_task_id = self._get_neon_companion_task_id()
                time.sleep(0.1)

    def _get_neon_companion_task_id(self, timeout_ms=6000) -> str | None:
        """
        Retrieves the task ID for the Neon Companion application.

        Args:
            timeout_ms (int, optional): The maximum amount of time to wait for the task ID, in milliseconds. 
                                        Defaults to 6000 milliseconds (6 seconds).

        Returns:
            str | None: The task ID of the Neon Companion application if found within the timeout period; 
                        otherwise, returns None.
        """
        res = None
        start_time = datetime.now()
        while res is None and (datetime.now() - start_time) < timedelta(milliseconds=timeout_ms):
            _res = self._run_adb_shell_command("am stack list")
            _res = re.search("taskId=(\d+): com.pupillabs.neoncomp", _res)
            if _res is None:
                time.sleep(0.1)
            else: 
                res = _res.groups()[0]
        return res
        