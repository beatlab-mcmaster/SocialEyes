import logging
from typing import Any, Callable, Coroutine, Dict, Optional
from dataclasses import dataclass

from .tui.table_view import Column, DeviceStateField
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Input, Label

from .app_utils import configure_logging, create_session_controller, Theme
from .session_controller import SessionController
from .monitoring.device import DeviceState
from .tui.widgets import SelectableRowsDataTable
from .tui.table_controller import DeviceTableController
from .tui.status_log import StatusLogController

@dataclass
class TableAppConfig:
    log_level: str # INFO, DEBUG, ...
    log_dir: str # Directory to store logs

    device_ips: list[str] # List of device IP addresses to monitor

    is_single_session_mode: bool
    status_log_max_len: int

    offset_logger_interval: int

class TableApp(App):

    CSS_PATH = "TUI.tcss"

    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(key="r", action="recording_start",
            description="Start Recording"),
        Binding(key="s", action="recording_stop_and_save",
            description="Save Recording"),
        Binding(key="u", action="recording_stop_and_discard",
            description="Cancel Recording"),
        Binding(key="t", action="restart_app_on_devices", description="Restart App"),
        Binding(key="a", action="reconnect_adb", description="Reconnect adb"),
        Binding(key="d", action="toggle_dark", description="Toggle dark mode"),
    ]

    TABLE_COLUMN_LAYOUT = [
        Column(name="Selected", field=None),
        Column(name="Last upd.", field=DeviceStateField.LAST_UPDATED),
        Column(name="IP address", field=DeviceStateField.IP),
        Column(name="PING", field=DeviceStateField.PING),
        Column(name="ADB", field=DeviceStateField.ADB),
        Column(name="USB", field=DeviceStateField.USB),
        Column(name="App", field=DeviceStateField.APP_ACTIVE),
        Column(name="API", field=DeviceStateField.APP_API_STATUS),
        Column(name="Device", field=DeviceStateField.DEVICE_NAME),
        Column(name="Frame", field=DeviceStateField.FRAME_NAME),
        Column(name="Battery", field=DeviceStateField.BATTERY),
        Column(name="Storage", field=DeviceStateField.STORAGE),
        Column(name="Recording state", field=DeviceStateField.PL_REC),
        Column(name="Red light indic.", field=DeviceStateField.RED_LIGHT_INDICATORS),
    ]

    _config: TableAppConfig
    _session_controller: SessionController
    _logger: logging.Logger

    # Device table widget
    _table_widget: Optional[SelectableRowsDataTable]
    _table_controller: Optional[DeviceTableController]
    _device_states: reactive[Dict[str, DeviceState]] = reactive({}, recompose=False)

    # Status log widget
    _status_log_widget: Optional[Label]
    _status_log_controller: StatusLogController

    # Events logging input widget
    _events_input_widget: Optional[Input]

    def __init__(self, config: TableAppConfig):
        super().__init__()
        try:
            session_controller = create_session_controller(config)
        except OSError as e:
            print(f"Error creating session directory: {e}")
            self.exit(return_code=1)
            return
        self._session_controller = session_controller
        self._logger = configure_logging(session_controller, config)
        self._status_log_controller = StatusLogController(max_len=config.status_log_max_len)
        self._config = config

    # -------------------------------------------------------
    # Textual lifecycle
    # -------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the Textual TUI.

        Returns:
            ComposeResult: The composed result containing UI elements.
        """
        yield SelectableRowsDataTable()
        yield Input(id = "event_tag", 
                    placeholder="Enter event tag/desc. here and press enter to log the event.", 
                    tooltip = "Use Tab to change focus")
        yield Label(self._status_log_controller.text)
        yield Footer(id = "footer")

    async def on_mount(self) -> None:
        """
        Initializes the app upon mounting.

        Sets up the device table and schedules periodic updates for various metrics related to the devices.
        """
        self.theme = Theme.DARK

        self._table_widget = self.query_one(SelectableRowsDataTable)
        self._table_widget.cursor_type = "row"

        self._table_controller = DeviceTableController(
            table_widget=self._table_widget,
            ip_addrs=self._session_controller.device_ip_addrs,
            column_layout=self.TABLE_COLUMN_LAYOUT
        )

        self._status_log_widget = self.query_one(Label)
        self._events_input_widget = self.query_one(Input)

        # Schedule periodic updates
        await self._session_controller.start_device_monitoring()
        self.set_interval(1, self._update_device_states)

        session_mode_str = "single-session mode" if self._config.is_single_session_mode else "multi-session mode"
        self._status_widget_push_message(
            f"   glassesRecord TUI started in {session_mode_str}; Session ID: {self._session_controller.session_id}"
        )

    def on_unmount(self) -> None:
        self._session_controller.stop_device_monitoring()
        self.exit()

    # -------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------

    def on_input_submitted(self, _: Input.Submitted) -> None:
        """Log event to JSON when input is submitted."""
        assert self._events_input_widget is not None, "Event input widget is not initialized."

        event_text = self._events_input_widget.value.strip()
        if not event_text:
            event_text = "NA"

        self._session_controller.log_event(event_text)

        # Clear box
        self._events_input_widget.value = ""

    async def watch_device_states(self, states: Dict[str, DeviceState]) -> None:
        assert self._table_controller is not None, "Device table controller is not initialized."

        # Apply updates to TUI
        with self.app.batch_update():
            self._table_controller.update_table(states)

    # -------------------------------------------------------
    # Actions (= `BINDINGS`)
    # -------------------------------------------------------

    async def action_recording_start(self) -> None:
        """Start recording on selected devices.

        This method retrieves the selected devices from the UI and starts
        recording on each one, logging the offsets if required.
        """
        await self._run_with_all_selected_devices("Starting recording", self._session_controller.start_recording)

    async def action_recording_stop_and_save(self) -> None:
        """Stop and save recording on selected devices.

        This method retrieves the selected devices from the UI and stops
        recording on each one, logging the offsets if they were started.
        """
        await self._run_with_all_selected_devices("Saving recording", self._session_controller.stop_and_save_recording)

    async def action_recording_stop_and_discard(self) -> None:
        """Stop and discard recording on selected devices.

        This method retrieves the selected devices from the UI and stops
        recording on each one, logging the offsets if they were started.
        """
        await self._run_with_all_selected_devices("Stopping recording", self._session_controller.stop_and_discard_recording)

    async def action_restart_app_on_devices(self) -> None:
        """Restart the app on selected devices.

        This method retrieves the selected devices from the UI and restarts
        the Neon Companion application on each one.
        """
        if self._session_controller.is_restart_app_in_progress:
            self._status_widget_push_message("    Another restart progress is already in progress, nothing to do...")
            return
        await self._run_with_all_selected_devices("Restarting app", self._session_controller.restart_app_on_devices)

    async def action_reconnect_adb(self) -> None:
        """
        Attempts to reconnect to an Android Debug Bridge (ADB) device at the specified IP address(es).
        """
        await self._run_with_all_selected_devices("Reconnecting ADB", self._session_controller.reconnect_adb)

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            Theme.LIGHT if self.theme == Theme.DARK else Theme.DARK
        )

    # -------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------

    def _status_widget_push_message(self, new_msg):
        """Update the status widget with the provided message.

        Args:
            new_msg (str): The message to display in the status widget.
        """
        if self._status_log_widget is not None:
            self._status_log_widget.update(self._status_log_controller.push(new_msg))

    async def _run_with_all_selected_devices(self, verb: str, coroutine_fn: Callable[[list[str]], Coroutine[Any, Any, None]]) -> None:
        assert self._table_controller is not None, "Device table controller is not initialized."

        selected_device_ip_addrs = self._table_controller.selected_ip_addrs()
        self._status_widget_push_message(f"    {verb} on {len(selected_device_ip_addrs)} device(s)...")
        try:
            await coroutine_fn(selected_device_ip_addrs)
            self._status_widget_push_message(f"    {verb} action completed!")
        except Exception as e:
            self._logger.exception(f"{verb} action failed")
            self._status_widget_push_message(f"    {verb} action failed: {str(e)}")

    def _update_device_states(self) -> None:
        self._device_states = self._session_controller.get_all_device_states()
