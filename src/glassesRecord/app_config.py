from dataclasses import dataclass


@dataclass
class TableAppConfig:
    log_level: str # INFO, DEBUG, ...
    log_dir: str # Directory to store logs

    device_ips: list[str] # List of device IP addresses to monitor

    is_single_session_mode: bool
    status_log_max_len: int

    offset_logger_interval: int