import logging
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Footer, Input, Label

from .app_config import TableAppConfig
from .app_utils import Theme, create_session_controller
from .monitoring.device import DeviceState
from .session_controller import SessionController
from .tui.status_log import StatusLogController
from .tui.table_controller import DeviceTableController
from .tui.table_view import Column, DeviceStateField
from .tui.widgets import SelectableRowsDataTable


class MonitoringInterval(Enum):
    FAST = 2
    MEDIUM = 5
    SLOW = 20

class TableApp(App):

    CSS_PATH = "TUI.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(key="r", action="recording_start",
            description="Start Recording"),
        Binding(key="s", action="recording_stop_and_save",
            description="Save Recording"),
        Binding(key="u", action="recording_stop_and_discard",
            description="Cancel Recording"),
        Binding(key="t", action="restart_app_on_devices", description="Restart App"),
        Binding(key="a", action="reconnect_adb", description="Reconnect adb"),
        Binding(key="1", action="monitoring_interval_fast", description=f"Monitor @ {MonitoringInterval.FAST.value}s"),
        Binding(key="2", action="monitoring_interval_medium", description=f"Monitor @ {MonitoringInterval.MEDIUM.value}s"),
        Binding(key="3", action="monitoring_interval_slow", description=f"Monitor @ {MonitoringInterval.SLOW.value}s"),
        Binding(key="d", action="toggle_dark", description="Toggle dark mode"),
    ]

    TABLE_COLUMN_LAYOUT: ClassVar[list[Column]] = [
        Column(name="■", field=None),
        Column(name="IP address", field=DeviceStateField.IP),
        Column(name="ADB", field=DeviceStateField.ADB),
        Column(name="Last upd.", field=DeviceStateField.LAST_UPDATED),
        Column(name="Ping", field=DeviceStateField.PING),
        Column(name="USB", field=DeviceStateField.USB),
        Column(name="App", field=DeviceStateField.APP_ACTIVE),
        Column(name="API", field=DeviceStateField.APP_API_STATUS),
        Column(name="Rec. state", field=DeviceStateField.RECORDING_STATE),
        Column(name="Red light ind.", field=DeviceStateField.RED_LIGHT_INDICATORS),
        Column(name="Battery", field=DeviceStateField.BATTERY),
        Column(name="Storage", field=DeviceStateField.STORAGE),
        Column(name="Device", field=DeviceStateField.DEVICE_NAME),
        Column(name="Frame", field=DeviceStateField.FRAME_NAME),
        Column(name="Locked", field=DeviceStateField.PHONE_LOCKED),
        Column(name="App version", field=DeviceStateField.APP_VERSION),
    ]

    _config: TableAppConfig 
    _session_controller: SessionController
    _table_app_logger: logging.Logger # _logger is already used by textual.App

    # Device table widget
    _table_widget: SelectableRowsDataTable | None
    _table_controller: DeviceTableController | None
    _device_states: dict[str, DeviceState]
    _monitoring_interval: MonitoringInterval | None

    # Status log widget
    _status_log_widget: Label | None
    _status_log_controller: StatusLogController

    # Events logging input widget
    _events_input_widget: Input | None

    def __init__(self, config: TableAppConfig):
        super().__init__()
        self._table_app_logger = logging.getLogger('glassesRecord_TUI')
        try:
            session_controller = create_session_controller(config)
        except OSError:
            self._table_app_logger.exception("Error creating session directory")
            self.exit(return_code=1)
            return
        self._session_controller = session_controller
        self._status_log_controller = StatusLogController(max_len=config.status_log_max_len)
        self._config = config
        self._device_states = {}

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
        self._monitoring_interval = MonitoringInterval.FAST
        await self._session_controller.start_device_monitoring(self._monitoring_interval.value)
        self._table_controller.time_ago_threshold(self._monitoring_interval.value)
        self.set_interval(1, self._update_device_states)

        session_mode_str = "single-session mode" if self._config.is_single_session_mode else "multi-session mode"
        self._status_widget_push_message(
            f"   glassesRecord TUI started in {session_mode_str}; Session ID: {self._session_controller.session_id}"
        )

    async def on_unmount(self) -> None:
        await self._session_controller.stop_device_monitoring()

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

    async def action_monitoring_interval_fast(self) -> None:
        """Set the device monitoring interval to 1 second."""
        await self._set_monitoring_interval(MonitoringInterval.FAST)

    async def action_monitoring_interval_medium(self) -> None:
        """Set the device monitoring interval to 5 seconds."""
        await self._set_monitoring_interval(MonitoringInterval.MEDIUM)

    async def action_monitoring_interval_slow(self) -> None:
        """Set the device monitoring interval to 20 seconds."""
        await self._set_monitoring_interval(MonitoringInterval.SLOW)

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
            self._table_app_logger.exception(f"{verb} action failed")
            self._status_widget_push_message(f"    {verb} action failed: {e!s}")

    def _update_device_states(self) -> None:
        assert self._table_controller is not None, "Device table controller is not initialized."
        self._device_states = self._session_controller.get_all_device_states()
        # Apply updates to TUI
        with self.app.batch_update():
            self._table_controller.update_table(self._device_states)

    async def _set_monitoring_interval(self, interval: MonitoringInterval) -> None:
        """Update the monitoring interval for all devices.

        Args:
            interval: The new monitoring interval.
        """
        async def f(device_ips: list[str]) -> None:
            assert self._table_controller is not None, "Device table controller is not initialized."
            await self._session_controller.set_monitoring_interval(interval.value, device_ips)
            self._table_controller.time_ago_threshold(interval.value, device_ips)
            self._monitoring_interval = interval

        await self._run_with_all_selected_devices(f"Setting monitoring interval to {interval.value}s", f)        
