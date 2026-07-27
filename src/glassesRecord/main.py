"""
main.py

Author: Shreshth Saxena, Alexander Nguyen
Purpose: Implements the main interface to monitor and control multiple devices in the recording mode.
"""

import multiprocessing

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Label
from textual.widgets._data_table import ColumnKey
from textual.reactive import reactive
from rich.text import Text
from asyncio import sleep
import numbers
from adb_wrapper import AdbWrapper
import threading
import requests
import subprocess
import os, time, json
from datetime import datetime
from textual_utils import SelectableRowsDataTable
from OffsetLogger import OffsetLogger
from config import config
import logging
from typing import Any, Optional, Dict
from device_manager import DeviceManager
from device import DeviceState
from enum import Enum

class Fields(str, Enum):
    IP = 'ip'
    PING = 'ping'
    ADB = 'adb'
    BATTERY = 'battery'
    STORAGE = 'storage'
    USB = 'usb'
    WIFI = 'wifi'

    APP_ACTIVE = 'app_active'
    APP_API_STATUS = 'app_api_status'
    APP_RTSP_STATUS = 'app_rtsp_status'
    RECORDING_INFO = 'recording_info'

    DEVICE_NAME = 'device_name'
    FRAME_NAME = 'frame_name'
    MODULE_SERIAL = 'module_serial'

    VIBRATOR_EVENTS = 'vibrator_events'
    RED_LIGHT_INDICATORS = 'red_light_indicators'

    PL_REC = 'PL_Rec'
    LAST_UPDATED = 'last_updated'

class DeviceStateDict(Dict[Fields, Any]):
    def __init__(self, state: Optional[DeviceState]):
        super().__init__()
        if state is not None:
            self[Fields.IP] = state.ip_addr
            self[Fields.PING] = state.ping
            self[Fields.ADB] = state.adb_connection_is_established
            self[Fields.BATTERY] = state.latest_statistics.phone.battery_level if state.latest_statistics else None
            self[Fields.STORAGE] = state.latest_statistics.phone.storage.free_gb if state.latest_statistics else None
            self[Fields.USB] = any("Neon" in d.product_name if d.product_name else False for d in state.latest_statistics.phone.usb_devices) if state.latest_statistics else None
            self[Fields.WIFI] = state.latest_statistics.phone.wifi.ssid if state.latest_statistics else None
            self[Fields.APP_ACTIVE] = state.latest_statistics.neon.is_active if state.latest_statistics else None
            self[Fields.APP_API_STATUS] = state.neon_api_is_available
            self[Fields.APP_RTSP_STATUS] = state.neon_rtsp_is_available
            self[Fields.DEVICE_NAME] = state.neon_hardware_ids.device_name if state.neon_hardware_ids else None
            self[Fields.FRAME_NAME] = state.neon_hardware_ids.frame_name if state.neon_hardware_ids else None
            self[Fields.MODULE_SERIAL] = state.neon_hardware_ids.module_serial if state.neon_hardware_ids else None
            self[Fields.RECORDING_INFO] = state.active_recordings
            self[Fields.RED_LIGHT_INDICATORS] = any(ri.red_light_indicator_detected for ri in state.active_recordings.values()) if state.active_recordings else None

            active_recordings_count = len(state.active_recordings) if state.active_recordings else None
            active_recordings_by_start_time = None
            if state.active_recordings:
                active_recordings_by_start_time = dict(sorted(state.active_recordings.items(), key=lambda x: x[1].started_at if x[1].started_at else datetime.min, reverse=True))
            rec_status_str = ''
            if active_recordings_count and active_recordings_count > 0 and active_recordings_by_start_time:
                rec_status_str = ', '.join([f"{short_recording_id(rec_id)} since {format_date(rec.started_at)} ({rec.state.name})" for rec_id, rec in active_recordings_by_start_time.items()]) if active_recordings_by_start_time and len(active_recordings_by_start_time.keys()) > 0 else None
                rec_status_str = f'{active_recordings_count} recording{"s" if active_recordings_count > 1 else ""}: {rec_status_str}'
            self[Fields.PL_REC] = rec_status_str

            self[Fields.LAST_UPDATED] = state.latest_statistics.now if state.latest_statistics else state.now

        else:
            for field in Fields:
                self[field] = None

    def differing_fields(self, old: Optional['DeviceStateDict']) -> Dict[Fields, Any]:
        # Returns a dictionary with the fields that have changed between self and `old`.
        changed_fields = {}
        if old is None:
            return dict(self)
        for key in self.keys():
            if self[key] != old.get(key):
                changed_fields[key] = self[key]
        return changed_fields

#Define column fields
COLUMNS = {
    "Check": None,
    "Device": None,
    "IP": None,
    "PING": Fields.PING,
    "WIFI": Fields.WIFI,
    "ADB": Fields.ADB,
    "Battery": Fields.BATTERY,
    "Storage": Fields.STORAGE,
    "USB": Fields.USB,
    "RED_INDICATOR": Fields.RED_LIGHT_INDICATORS,
    "App": Fields.APP_ACTIVE,
    "API": Fields.APP_API_STATUS,
    "RTSP": Fields.APP_RTSP_STATUS,
    "PL_Rec": Fields.PL_REC,
    "Last updated": Fields.LAST_UPDATED
}

class TableApp(App):
    CSS_PATH = "TUI.tcss"
    #could set as reactive elements so we can "watch" it. Alternatively, update at a fixed time interval.
    #ping = reactive(list(range(N_DEVICES)))
    row_keys = []
    column_keys = []
    devices = []
    offset_logger = None
    logger: logging.Logger
    session_id = datetime.now().strftime('%y%m%dT%H%M%S') #Session ID created using timestamp; could also be created using UUID, user input, etc.
    session_dir = os.path.join(config["logs"]["path"], session_id)
    events_file = os.path.join(session_dir, "events.json")
    single_session_mode = config["single_session_mode"]
    status_widget = None
    status_messages = [f"   glassesRecord TUI started in {"single-session mode" if single_session_mode else "multi-session mode"}; Session ID: {session_id}"]
    status_len = config["logs"]["TUI_messages_len"] # Number of status messages to keep

    restart_app_in_progress = False

    _device_manager: DeviceManager

    device_states: reactive[Dict[str, DeviceState]] = reactive({}, recompose=False)
    _rendered_state: Dict[str, DeviceStateDict] = {}

    def __init__(self):
        super().__init__()

        ## Setup session directory and logging
        try:
            os.makedirs(self.session_dir)
        except FileExistsError:
            print("Session folder already exists, please try again.")
            self.app.exit()
        logging.basicConfig(
            filename=os.path.join(self.session_dir,'logs.txt'),
            encoding='utf-8',
            level=config["logs"]["level"], # change to DEBUG if required
            format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s')
        logging.getLogger('pupil_labs.realtime_api.time_echo').setLevel(logging.ERROR)
        self.logger = logging.getLogger('glassesRecord_TUI')

        #Generate ip addrs of devices using config parameters (looks for a host_id range by default)
        
        if "network_id" in config and "host_id" in config and config["network_id"] and (config["host_id"]["start"] <= config["host_id"]["end"]):
            network_id = config["network_id"]
            host_id_range = range(config["host_id"]["start"], config["host_id"]["end"]+1)
            ip_list = [f"{network_id}.{host_id}" for host_id in host_id_range]
        elif "ip_list" in config:
            ip_list = config["ip_list"]
        else:
            raise ValueError("Configuration must contain either 'network_id' and 'host_id' or 'ip_list'.")

        #Populate devices
        self._device_manager = DeviceManager()
        for ip_addr in ip_list:
            self._device_manager.register_device(str(ip_addr))

        #Init offset logger for all devices if not in single session mode
        if not self.single_session_mode:
            self.offset_logger = {dev: None for dev in ip_list}

    async def on_mount(self) -> None:
        """
        Initializes the app upon mounting.

        Sets up the device table, generates IP addresses for devices, and schedules
        periodic updates for various metrics related to the devices.
        """
        await self._device_manager.start_all()
        self.status_widget = self.query_one(Label)

        # Setup app theme and table
        self.theme = "textual-dark"
        table = self.query_one(SelectableRowsDataTable)
        table.cursor_type = "row"
        self.column_keys = table.add_columns(*list(COLUMNS.keys())) #is_valid_column_index(self, column_index) can be used to verify

        registered_ip_list = [self._device_manager.devices[ip]._ip_addr
                              for ip in self._device_manager.devices.keys()]
        data = [(None, ip_addr, None, None, None, None, None, None, None, None, None, None) for ip_addr in registered_ip_list]
        self.row_keys = table.add_rows(data)
        table.styles.scroll_x = "scroll_x"

        self.table_app_start_time = datetime.now()

        self.set_interval(1, self.query_device_states)

    def query_device_states(self) -> None:
        s = self._device_manager.get_all_device_states()
        self.device_states = s

    async def on_unmount(self) -> None:
        if self._device_manager:
            self._device_manager.stop_all()
        self.exit()

    async def watch_device_states(self, states: Dict[str, DeviceState]) -> None:
        table = self.query_one(SelectableRowsDataTable)

        # Get list of device IPs (in same order as table rows)
        ip_list = [self._device_manager.devices[ip]._ip_addr
                   for ip in self._device_manager.devices.keys()]

        # Diff-based updates: only update cells that actually changed
        updates: list[tuple[int, Fields, Any]] = []
        for row_idx, ip_addr in enumerate(ip_list):
            if ip_addr not in states: # Skip if device state is not available
                continue

            old_state_dict = self._rendered_state.get(ip_addr, None)
            new_state_dict = DeviceStateDict(states[ip_addr])

            changed_fields = new_state_dict.differing_fields(old_state_dict)

            self._rendered_state[ip_addr] = new_state_dict

            # Diff-based updates
            if Fields.PING in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.PING), thresh_low=500, thresh_high=500, reverse=True)
                updates.append((row_idx, Fields.PING, val))

            if Fields.DEVICE_NAME in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.DEVICE_NAME))
                updates.append((row_idx, Fields.DEVICE_NAME, val))

            if Fields.ADB in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.ADB))
                updates.append((row_idx, Fields.ADB, val))

            if Fields.BATTERY in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.BATTERY), thresh_low=25, thresh_high=50)
                updates.append((row_idx, Fields.BATTERY, val))

            if Fields.STORAGE in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.STORAGE), thresh_low=25, thresh_high=50)
                updates.append((row_idx, Fields.STORAGE, val))

            if Fields.USB in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.USB))
                updates.append((row_idx, Fields.USB, val))

            if Fields.WIFI in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.WIFI))
                updates.append((row_idx, Fields.WIFI, val))

            if Fields.APP_ACTIVE in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.APP_ACTIVE))
                updates.append((row_idx, Fields.APP_ACTIVE, val))

            if Fields.APP_API_STATUS in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.APP_API_STATUS))
                updates.append((row_idx, Fields.APP_API_STATUS, val))

            if Fields.APP_RTSP_STATUS in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.APP_RTSP_STATUS))
                updates.append((row_idx, Fields.APP_RTSP_STATUS, val))

            if Fields.DEVICE_NAME in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.DEVICE_NAME))
                updates.append((row_idx, Fields.DEVICE_NAME, val))

            if Fields.RED_LIGHT_INDICATORS in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.RED_LIGHT_INDICATORS), reverse=True)
                updates.append((row_idx, Fields.RED_LIGHT_INDICATORS, val))

            if Fields.PL_REC in changed_fields:
                val = as_colored_text(new_state_dict.get(Fields.PL_REC))
                updates.append((row_idx, Fields.PL_REC, val))

            # Always update last_updated field
            now = datetime.now()
            val = as_colored_text(time_ago(now, new_state_dict.get(Fields.LAST_UPDATED)))
            updates.append((row_idx, Fields.LAST_UPDATED, val))

            # Update rendered state tracker
            self._rendered_state[ip_addr].update(new_state_dict)

        # Apply updates to TUI
        with self.app.batch_update():
            for row_idx, field, val in updates:
                table.update_cell(self.row_keys[row_idx], self._field_to_column(field), val, update_width=True)

    def _field_to_val(self, field: str, val):
        if field == Fields.PING:
            return as_colored_text(val, reverse=True, thresh_low=100, thresh_high=500)
        elif field in [Fields.WIFI, Fields.ADB, Fields.APP_ACTIVE, Fields.APP_API_STATUS, Fields.APP_RTSP_STATUS]:
            return as_colored_text(val)
        elif field in [Fields.BATTERY, Fields.STORAGE]:
            return as_colored_text(val, thresh_low=25, thresh_high=50)
        elif field == Fields.USB:
            usb_connections = None
            if val is not None:
                product_names = sorted([p["product_name"] for p in val])
                usb_connections = set(['Neon Scene Camera v1', 'Neon Sensor Module v1']).issubset(set(product_names))
            return as_colored_text(usb_connections)
        else:
            return val

    def _field_to_column(self, field: Fields) -> ColumnKey:
        """Map device field to table column."""
        mapping = {
            Fields.DEVICE_NAME: self.column_keys[1],
            Fields.IP: self.column_keys[2],
            Fields.PING: self.column_keys[3],
            Fields.WIFI: self.column_keys[4],
            Fields.ADB: self.column_keys[5],
            Fields.BATTERY: self.column_keys[6],
            Fields.STORAGE: self.column_keys[7],
            Fields.USB: self.column_keys[8],
            Fields.RED_LIGHT_INDICATORS: self.column_keys[9],
            Fields.APP_ACTIVE: self.column_keys[10],
            Fields.APP_API_STATUS: self.column_keys[11],
            Fields.APP_RTSP_STATUS: self.column_keys[12],
            Fields.PL_REC: self.column_keys[13],
            Fields.LAST_UPDATED: self.column_keys[14]
        }
        if field not in mapping:
            raise ValueError(f"Field {field} does not have a corresponding column mapping.")
        return mapping.get(field) # type: ignore

    async def lock_phone(self, ip_addr: str) -> None:
        """Remotely lock the specified phone if it is currently unlocked.

        Args:
            ip_addr (str): The IP address of the target device.
        """
        await self._device_manager.devices[ip_addr].lock_display()

    async def start_recording(self, ip_addr):
        """Start recording on the specified device.

        This method unlocks the phone, sends a request to start recording and then locks the phone again.
        The unlocking ensures proper recording of audio and locking again ensures that the app is not accessed through the phone.

        Args:
            ip_addr (str): The IP address of the target device.

        Returns:
            dict: The JSON response from the recording API, if successful.
        """
        res = None

        try:
            self.logger.info(f'Start recording on {ip_addr}')
            res = requests.post(f"http://{ip_addr}:8080/api/recording:start", timeout=2).json()
            time.sleep(0.1)
            await self.lock_phone(ip_addr)
        except Exception as e:
            self.logger.error(f'{ip_addr}, {e}')
            pass

        return res

    def stop_and_save_recording(self, ip_addr):
        """Stop and save the recording on the specified device.

        Args:
            ip_addr (str): The IP address of the target device.

        Returns:
            dict: The JSON response from the recording API, if successful.
        """
        res = None
        try:
            res = requests.post(f"http://{ip_addr}:8080/api/recording:stop_and_save", timeout=2).json()
        except Exception as e:
            self.logger.error(f'{ip_addr}, {e}')
            pass
        return res

    def stop_and_discard_recording(self, ip_addr):
        """Stop and discard the recording on the specified device.

        Args:
            ip_addr (str): The IP address of the target device.

        Returns:
            dict: The JSON response from the recording API, if successful.
        """
        res = None
        try:
            res = requests.post(f"http://{ip_addr}:8080/api/recording:cancel", timeout=2).json()
        except Exception as e:
            self.logger.error(f'{ip_addr}, {e}')
            print(e)
            pass
        return res

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Log event to JSON when input is submitted."""
        input_box = self.query_one(Input)
        event_text = input_box.value.strip()
        if not event_text:
            event_text = "NA"

        try:
            with open(self.events_file, "r") as f:
                events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            events = []

        events.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_text
        })

        with open(self.events_file, "w") as f:
            json.dump(events, f, indent=2)
        # Clear box
        input_box.value = ""

    def stop_recording_offsets(self, device_list):
        """
        Stop logging offsets for the specified devices.
        Args:
            devices (list): List of device IP addresses to stop logging offsets for.
        """
        try:
            if self.single_session_mode:
                if self.offset_logger:
                    self.offset_logger.stop_logging()
                    self.offset_logger = None
                    self.logger.info("Stopped offset logging for all devices.")
            else:
                for dev in device_list:
                    if self.offset_logger[dev]:
                        self.offset_logger[dev].stop_logging()
                        self.offset_logger[dev] = None
                self.logger.info("Stopped offset logging for devices: {}".format(device_list))
        except Exception as e:
            self.logger.error(f'Error stopping offset logging: {e}')
            print(e)
            pass

    def update_status_widget(self, new_msg):
        """Update the status widget with the provided message.

        Args:
            message (str): The message to display in the status widget.
        """
        self.status_messages.append(new_msg)
        self.status_messages = self.status_messages[-self.status_len:]

        if self.status_widget:
            self.status_widget.update('\n'.join(self.status_messages))

    #Defining actions
    @work(exclusive=True, thread=True)
    async def action_recording_start(self) -> None:
        """Start recording on selected devices.

        This method retrieves the selected devices from the UI and starts
        recording on each one, logging the offsets if required.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        self.logger.info("Selected devices ({}): {}".format(len(selected_devices), selected_devices))
        self.update_status_widget(f"    Starting recording on {len(selected_devices)} device(s)...")
        # print("STARTING REC on selected devices")

        if self.single_session_mode:
            if not self.offset_logger:
                self.offset_logger = OffsetLogger(selected_devices, log_dir=self.session_dir, log_interval=config["logs"]["interval"])
                self.logger.info(f"Starting Offset logger at {self.offset_logger.log_file}")
                self.offset_logger.log_offsets()
        else:
            for dev in selected_devices:
                if not self.offset_logger[dev]:
                    self.offset_logger[dev] = OffsetLogger([dev], log_dir=os.path.join(self.session_dir, str(dev)), log_interval=config["logs"]["interval"])
                    self.logger.info(f"Starting Offset logger at {self.offset_logger[dev].log_file} for device: {dev}")
                    self.offset_logger[dev].log_offsets()

        #Start recording on all devices independently
        for d in selected_devices:
            t = threading.Thread(target=self.start_recording, args=(d,), daemon=True)
            t.start()

        self.update_status_widget(f"    Start recordings action completed!")

    ## Implementing action keys below to control the execution of certain operations manually by the operator.

    @work(exclusive=True, thread=True)
    async def action_recording_stop_and_save(self) -> None:
        """Stop and save recording on selected devices.

        This method retrieves the selected devices from the UI and stops
        recording on each one, logging the offsets if they were started.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        self.update_status_widget(f"    Saving recording on {len(selected_devices)} device(s)...")
        # print("STOPPING REC on selected device(s): ", selected_devices)
        self.logger.info(f"Stopping recording on {len(selected_devices)} device(s): {selected_devices}")
        # Stop offset logging if it was started
        self.stop_recording_offsets(selected_devices)
        for d in selected_devices:
            t = threading.Thread(target=self.stop_and_save_recording, args=(d,), daemon=True)
            t.start()
        self.update_status_widget(f"    Save recordings action completed!")

    @work(exclusive=True, thread=True)
    async def action_recording_stop_and_discard(self) -> None:
        """Stop and discard recording on selected devices.

        This method retrieves the selected devices from the UI and stops
        recording on each one, logging the offsets if they were started.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        self.update_status_widget(f"    Discarding recordings on {len(selected_devices)} device(s)...")
        # print("DISCARDING REC on selected devices")
        # Stop offset logging if it was started
        self.logger.info(f"Discarding recording on {len(selected_devices)} device(s): {selected_devices}")
        self.stop_recording_offsets(selected_devices)
        for d in selected_devices:
            t = threading.Thread(target=self.stop_and_discard_recording, args=(d,), daemon=True)
            t.start()
        self.update_status_widget(f"    Discard recordings action completed!")

    @work(exclusive=True, thread=True)
    async def action_restart_app_on_devices(self) -> None:
        """Restart the app on selected devices.

        This method retrieves the selected devices from the UI and restarts
        the Neon Companion application on each one.
        """
        self.logger.info('action_restart_app_on_devices triggered!')
        if self.restart_app_in_progress:
            self.logger.info('Another restart progress is already in progress, nothing to do...')
            return
        print("RESTARTING APP on selected devices")

        try:
            self.restart_app_in_progress = True

            table = self.query_one(SelectableRowsDataTable)
            selected_device_ip_addrs = [row.data[1] for row in table.selected_rows]
            self.update_status_widget(f"    Restarting app on {len(selected_device_ip_addrs)} devices...")
            self.logger.info("Selected devices ({}): {}".format(len(selected_device_ip_addrs), selected_device_ip_addrs))

            def f(ip_addr):
                self.logger.info(f'Restarting app on {ip_addr}...')
                adb_wrapper = AdbWrapper(ip_addr)
                adb_wrapper.stop_neon_companion_app()
                adb_wrapper.start_neon_companion_app(wait_until_started=False)
                self.logger.info(f'Restarting app on {ip_addr} has finished!')

            tasks = []
            for ip_addr in selected_device_ip_addrs:
                t = threading.Thread(target=f, args=[ip_addr])
                tasks.append(t)
                t.start()

            for t in tasks:
                t.join()
            self.logger.info(f'Restarting apps has finished!')
            self.update_status_widget(f"    App restart action completed!")
        finally:
            self.restart_app_in_progress = False
            self.logger.info(f'self.restart_app_in_progress = False')

    @work(exclusive=True, thread=True)
    async def action_reconnect_adb(self) -> None:
        """
        Attempts to reconnect to an Android Debug Bridge (ADB) device at the specified IP address(es).
        """

        print("RESTARTING ADB on selected devices!")
        table = self.query_one(SelectableRowsDataTable)
        selected_device_ip_addrs = [row.data[1] for row in table.selected_rows]
        self.update_status_widget(f"    Restarting adb on {len(selected_device_ip_addrs)} devices...")
        self.logger.info("Selected devices ({}): {}".format(len(selected_device_ip_addrs), selected_device_ip_addrs))

        def run_adb_cmd(ip_addr):
            """Runs the adb connect command for a single device."""
            self.logger.info(f"Restarting adb on {ip_addr}...")
            res = subprocess.run(f"adb connect {ip_addr}:5555", shell=True, capture_output=True, text=True)
            self.logger.info(res.stdout.strip())

        for ip_addr in selected_device_ip_addrs:
            t = threading.Thread(target=run_adb_cmd, args=(ip_addr,), daemon=True)
            t.start()

        print('FINISHED dispatching adb restart threads!')
        self.update_status_widget(f"    adb restart action completed!")

    @work(exclusive=True, thread=True)
    def action_stop_all_offsets(self) -> None:
        """
        Stops all ongoing offset logging activities.
        """
        self.stop_recording_offsets(self.devices)

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "solarized-light" if self.theme == "textual-dark" else "textual-dark"
        )

    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(key="r", action="recording_start",
            description="Start Recording"),
        Binding(key="s", action="recording_stop_and_save",
            description="Save Recording"),
        Binding(key="u", action="recording_stop_and_discard",
           description="Cancel Recording"),
        *([Binding(key="o", action="stop_all_offsets", description="Stop offsets logging on all devices")] if config["single_session_mode"] else []),
        Binding(key="t", action="restart_app_on_devices", description="Restart App"),
        Binding(key="a", action="reconnect_adb", description="Reconnect adb"),
        Binding(key="d", action="toggle_dark", description="Toggle dark mode"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the Textual TUI.

        Returns:
            ComposeResult: The composed result containing UI elements.
        """
        yield SelectableRowsDataTable()
        yield Input(id = "event_tag", placeholder="Enter event tag/desc. here and press enter to log the event.", tooltip = "Use Tab to change focus")
        yield Label(self.status_messages[0])
        yield Footer(id = "footer")

def as_colored_text(val, **kwargs):
    """Convert a value into a Rich colored text representation.

    Args:
        val: The value to convert.
        **kwargs: Additional arguments for color styling.

    Returns:
        Text: A styled Text object based on the value.
    """
    if val is None:
        return '-'
    elif isinstance(val, bool):
        return Text(str(val), style=get_style_bool(val))
    elif isinstance(val, numbers.Number):
        if 'reverse' in kwargs and kwargs['reverse']:
            return Text(str(val), style=get_style_num(-val, -kwargs['thresh_low'], -kwargs['thresh_high']))
        else:
            return Text(str(val), style=get_style_num(val, kwargs['thresh_low'], kwargs['thresh_high']))
    else:
        return Text(str(val))

def get_style_num(val, thresh_low, thresh_high):
    """Determine the style for numeric values based on thresholds.

    Args:
        val (float): The numeric value.
        thresh_low (float): The lower threshold.
        thresh_high (float): The upper threshold.

    Returns:
        str: The style to apply based on the value.
    """
    if val == None:
        return ""
    elif val <= thresh_low:
        return "red"
    elif thresh_high > val > thresh_low:
        return "yellow"
    elif val >= thresh_high:
        return "green"

def get_style_bool(val):
    """Determine the style for boolean values.

    Args:
        val (bool or None): The boolean value to evaluate.

    Returns:
        str: The style to apply based on the value:
             - "green" if True
             - "red" if False
             - "" (empty string) if None
    """
    if val == None:
        return ""
    elif val:
        return "green"
    else:
        return "red"

def time_ago(now: datetime, past: Optional[datetime]) -> str:
    if not past:
        return "Never"
    delta = now - past
    seconds = delta.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds // 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"

def short_recording_id(recording_id: str) -> str:
    return f"{recording_id[:9]}..." if recording_id else "N/A"

def format_date(date: Optional[datetime]) -> str:
    if not date:
        return "N/A"
    date = date.astimezone()  # Convert to local timezone
    now = datetime.now().astimezone()  # Current time in local timezone
    if (now - date).days < 1:
        return date.strftime("%H:%M:%S")
    return date.strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    app = TableApp()
    app.run()
