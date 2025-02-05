"""
OffsetLogger.py

Author: Areez Vizram, Alexander Nguyen, Shreshth Saxena
Purpose: Implemets the OffsetLogger class to log the time offset of each device to a log file
"""


import time
import csv
from typing import List
from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator
import asyncio
from threading import Thread
from datetime import datetime
import os

class OffsetLogger:
    """This class logs the time offset of each device to a log file"""

    def __init__(self, device_ips: List, log_file: str = None, log_interval: int = 10):
        """Initializes the OffsetLogger instance.

        Args:
            device_ips (List[str]): List of device IP addresses to log offsets for.
            log_file (str, optional): Path to a custom log file. If not provided, a timestamped log file will be created.
            log_interval (int, optional): Time in seconds between logging offsets. Default is 10 seconds.
        """
        
        os.makedirs("logs", exist_ok=True)
        self.log_file = f"logs/{datetime.now().strftime('%y%m%dT%H%M%S')}_offsets.csv" if log_file is None else log_file
        print(os.path.abspath(self.log_file))
        self.log_interval = log_interval
        self.devices = device_ips
        self._stop_requested = False
        
    def estimate_offsets(self, time_echo_server_info):
        """Estimates the time offsets for each device from the server running this script.
        This method logs the mean time offset and roundtrip duration for each device.

        Args:
            time_echo_server_info (List[dict]): Information containing device IPs and ports.

        """
        for entry in time_echo_server_info:
            ip = entry["phone_ip"]
            port = entry["port"]
            estimator = TimeOffsetEstimator(ip, port)
            try:
                estimate = asyncio.run(estimator.estimate())
                self.log_to_file(ip, estimate.time_offset_ms.mean,
                                estimate.roundtrip_duration_ms.mean)
            except Exception as e:
                print(f"Failed to log offset for device {ip.split('.')[-1]}", e)
    
    def call_offsets(self, time_echo_server_info):
        """Continuously calls estimate_offsets until a stop is requested.
        This method runs in a loop, estimating offsets every 10 seconds.

        Args:
            time_echo_server_info (List[dict]): Information containing device IPs and ports.
        """
        while True and not self._stop_requested:
            self.estimate_offsets(time_echo_server_info)
            time.sleep(self.log_interval)


    def log_offsets(self):
        """Starts the logging process for time offsets.

        This method initializes the time echo server information and starts a background thread
        that continuously logs offsets for the specified devices.
        """

        time_echo_server_info = []
        for device in self.devices:
            try:
                time_echo_server_info.append({'phone_ip': device, 'port': 12321})
            except Exception as e:
                print(f"Failed to get device status in OffsetLogger for device {device}", e)
        t = Thread(target=self.call_offsets, args=(time_echo_server_info, ), daemon=True)
        t.start()

    def log_to_file(self, device_name, mean_offset, mean_duration):
        """Logs the time offset and roundtrip duration to the log file.

        Args:
            device_name (str): The name of the device being logged.
            mean_offset (float): The mean time offset in milliseconds.
            mean_duration (float): The mean roundtrip duration in milliseconds.
        """
        
        timestamp = int(time.time_ns())
        with open(self.log_file, 'a', newline='', encoding='utf-8') as csvfile:
            field_names = ['device', 'timestamp [ns]',
                           'mean time offset [ms]', 'mean roundtrip duration [ms]']
            writer = csv.DictWriter(csvfile, fieldnames=field_names)

            if csvfile.tell() == 0:
                writer.writeheader()

            writer.writerow(
                {'device': device_name, 'timestamp [ns]': timestamp, 'mean time offset [ms]': mean_offset, 'mean roundtrip duration [ms]': mean_duration})

    def stop_logging(self):
        """Stops the time offset logging process.

        This method sets the stop flag, which causes the logging thread to exit.
        """
        self._stop_requested = True