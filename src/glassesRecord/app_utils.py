import logging
import os
from datetime import datetime
from enum import Enum

from .app_config import TableAppConfig
from .clients.adb import get_default_adb_path
from .clients.core import exists_as_path_or_command
from .session_controller import SessionController, SessionControllerConfig


def create_session_controller(config: "TableAppConfig") -> SessionController:
    """
    Creates a new session directory and returns a SessionController object.
    
    Returns
    -------
    SessionController
        A SessionController object containing the session ID, session directory, and other relevant information.

    Raises
    ------
    OSError
        If the session directory cannot be created.
    """
    adb_path = get_default_adb_path()
    if not exists_as_path_or_command(adb_path):
        raise RuntimeError(f"ADB_PATH '{adb_path}' is not a valid path or command")

    session_id = datetime.now().strftime('%y%m%dT%H%M%S') # Session ID created using timestamp; could also be created using UUID, user input, etc.
    session_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), config.log_dir, session_id)
    os.makedirs(session_dir)

    session_controller_config = SessionControllerConfig(
        log_level=config.log_level,
        session_id=session_id,
        session_dir=session_dir,
        is_single_session_mode=config.is_single_session_mode,
        device_ips=config.device_ips,
        offset_logger_interval=config.offset_logger_interval
    )
    return SessionController(session_controller_config)

def configure_logging(session: SessionController, config: "TableAppConfig") -> logging.Logger:
    """
    Configures logging for the TUI, including logging to a file in the session directory and suppressing verbose logging from the PL Realtime API.
    
    Parameters
    ----------
    session : SessionController
        The SessionController object.
    config : TableAppConfig
        The TableAppConfig object containing the raw configuration.

    Returns
    -------
    logging.Logger
        A logger configured for the TUI.
    """

    # Suppress verbose logging from the PL Realtime API
    logging.getLogger('pupil_labs.realtime_api.time_echo').setLevel(logging.ERROR)

    # Set up logger for the TUI
    logger = logging.getLogger('glassesRecord_TUI')
    return logger

class Theme(str, Enum):
    DARK = "textual-dark"
    LIGHT = "solarized-light"

    def __str__(self) -> str:
        return self.value
