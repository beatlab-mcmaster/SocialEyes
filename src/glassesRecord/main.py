"""
main.py

Author: Shreshth Saxena, Alexander Nguyen
Purpose: Implements the main interface to monitor and control multiple devices in the recording mode.
"""

import multiprocessing

from .app import TableApp, TableAppConfig
from .config import config


def build_ip_addresses_from_config(config: dict) -> list[str]: 
    """
    Resolves the list of IP addresses for devices based on the provided configuration (either 'network_id' and 'host_id' or 'ip_list').

    Parameters
    ----------
    config : dict
        Configuration dictionary containing network parameters or a predefined list of IP addresses.

    Returns
    -------
    list[str]
        A list of resolved IP addresses for the devices.
    Raises
    ------
    ValueError
        If the configuration does not contain either 'network_id' and 'host_id' or 'ip_list'."""
    if "network_id" in config and "host_id" in config and config["network_id"] and (config["host_id"]["start"] <= config["host_id"]["end"]):
        network_id = config["network_id"]
        host_id_range = range(config["host_id"]["start"], config["host_id"]["end"]+1)
        ip_list = [f"{network_id}.{host_id}" for host_id in host_id_range]
    elif "ip_list" in config:
        ip_list = config["ip_list"]
    else:
        raise ValueError("Configuration must contain either 'network_id' and 'host_id' or 'ip_list'.")
    return ip_list

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)

    table_app_config = TableAppConfig(
        log_level=config["logs"]["level"],
        log_dir=config["logs"]["path"],
        device_ips=build_ip_addresses_from_config(config),
        is_single_session_mode=config.get("single_session_mode", False),
        status_log_max_len=config["logs"]["TUI_messages_len"],
        offset_logger_interval=config["logs"]["interval"],
        device_state_logger_interval=config["logs"]["device_state_logger_interval"]
    )
    app = TableApp(table_app_config)
    app.run()
