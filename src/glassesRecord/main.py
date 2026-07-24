"""
main.py

Author: Shreshth Saxena, Alexander Nguyen
Purpose: Implements the main interface to monitor and control multiple devices in the recording mode.
"""

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Label
from textual.reactive import reactive
from rich.text import Text
from asyncio import sleep
import numbers
from adb_wrapper import AdbWrapper
import threading
import requests
import subprocess
import os, time, json
from datetime import datetime, timedelta
from textual_utils import SelectableRowsDataTable
from device import Device, Fields
from OffsetLogger import OffsetLogger
from config import config
import logging
import asyncio
from typing import Optional, Dict
from device_manager import DeviceManager, DeviceState

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
    "PL_Rec": None,
    "PL_Rec_ID": None,
    "PL_Rec_Duration": None
    #"Vibration", "White_LED"
}

class TableApp(App):
    CSS_PATH = "TUI.tcss"
    #could set as reactive elements so we can "watch" it. Alternatively, update at a fixed time interval.
    #ping = reactive(list(range(N_DEVICES)))
    row_keys = []
    column_keys = []
    devices = []
    offset_logger = None
    logger = None
    session_id = datetime.now().strftime('%y%m%dT%H%M%S') #Session ID created using timestamp; could also be created using UUID, user input, etc.
    session_dir = os.path.join(config["logs"]["path"], session_id)
    events_file = os.path.join(session_dir, "events.json")
    single_session_mode = config["single_session_mode"]
    status_widget = None
    status_messages = [f"   glassesRecord TUI started in {"single-session mode" if single_session_mode else "multi-session mode"}; Session ID: {session_id}"]
    status_len = config["logs"]["TUI_messages_len"] # Number of status messages to keep

    restart_app_in_progress = False

    device_states: reactive[Dict[str, DeviceState]] = reactive({}, recompose=False)
    device_manager: Optional[DeviceManager] = None
    _rendered_state: Dict[str, dict] = {}

    async def on_mount(self) -> None:
        """
        Initializes the app upon mounting.

        Sets up the device table, generates IP addresses for devices, and schedules
        periodic updates for various metrics related to the devices.
        """

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
        self.status_widget = self.query_one(Label)

        # Setup app theme and table
        self.theme = "textual-dark"
        table = self.query_one(SelectableRowsDataTable)
        table.cursor_type = "row"
        self.column_keys = table.add_columns(*list(COLUMNS.keys())) #is_valid_column_index(self, column_index) can be used to verify

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
        self.device_manager = DeviceManager()

        for ip_addr in ip_list:
            self.device_manager.register_device(str(ip_addr), '5555')

        self.device_manager.start_all()

        #Init offset logger for all devices if not in single session mode
        if not self.single_session_mode:
            self.offset_logger = {dev: None for dev in ip_list}

        registered_ip_list = [self.device_manager.devices[ip].ip_addr
                              for ip in self.device_manager.devices.keys()]
        data = [(None, ip_addr, None, None, None, None, None, None, None, None, None, None, None, None, None) for ip_addr in registered_ip_list]
        self.row_keys = table.add_rows(data)
        table.styles.scroll_x = "scroll_x"

        self.table_app_start_time = datetime.now()

        self.set_interval(0.5, self.query_device_states)

    def query_device_states(self) -> None:
        s = self.device_manager.get_all_states()
        self.device_states = s


    async def on_unmount(self) -> None:
        if self.device_manager:
            self.device_manager.stop_all()
        self.exit()

    async def watch_device_states(self, states: Dict[str, DeviceState]) -> None:
        """
        Textual watcher: automatically invoked when device_states reactive property changes.

        This runs in the UI thread and should be FAST:
        - Only update cells that actually changed
        - Use diff-based updates
        - Never do I/O or long-running operations

        Args:
            states: New dict of {ip_addr: DeviceState}
        """
        table = self.query_one(SelectableRowsDataTable)

        # Get list of device IPs (in same order as table rows)
        ip_list = [self.device_manager.devices[ip].ip_addr
                   for ip in self.device_manager.devices.keys()]

        # Diff-based updates: only update cells that actually changed
        updates = []
        for idx, ip_addr in enumerate(ip_list):
            if ip_addr not in states:
                continue

            new_state = states[ip_addr]
            old_state = self._rendered_state.get(ip_addr, {})

            changed_fields = new_state.diff_fields(DeviceState(ip_addr=ip_addr, **old_state))

            # Diff-based updates
            if Fields.PING in changed_fields:
                val = as_colored_text(new_state.ping, thresh_low=500, thresh_high=1000)
                updates.append((idx, Fields.PING, val))

            if Fields.DEVICE_NAME in changed_fields:
                val = as_colored_text(new_state.device_name)
                updates.append((idx, Fields.DEVICE_NAME, val))

            if Fields.ADB in changed_fields:
                val = as_colored_text(new_state.adb)
                updates.append((idx, Fields.ADB, val))

            if Fields.BATTERY in changed_fields:
                val = as_colored_text(new_state.battery, thresh_low=25, thresh_high=50)
                updates.append((idx, Fields.BATTERY, val))

            if Fields.STORAGE in changed_fields:
                val = as_colored_text(new_state.storage, thresh_low=25, thresh_high=50)
                updates.append((idx, Fields.STORAGE, val))

            if Fields.USB in changed_fields:
                usb_connections = None
                if new_state.usb is not None:
                    product_names = sorted([p["product_name"] for p in new_state.usb])
                    usb_connections = {'Neon Scene Camera v1', 'Neon Sensor Module v1'}.issubset(set(product_names))
                val = as_colored_text(usb_connections)
                updates.append((idx, Fields.USB, val))

            if Fields.WIFI in changed_fields:
                val = as_colored_text(','.join(new_state.wifi if new_state.wifi else []))
                updates.append((idx, Fields.WIFI, val))

            if Fields.APP_ACTIVE in changed_fields:
                val = as_colored_text(new_state.app_active)
                updates.append((idx, Fields.APP_ACTIVE, val))

            if Fields.APP_API_STATUS in changed_fields:
                val = as_colored_text(new_state.app_api_status)
                updates.append((idx, Fields.APP_API_STATUS, val))

            if Fields.APP_RTSP_STATUS in changed_fields:
                val = as_colored_text(new_state.app_rtsp_status)
                updates.append((idx, Fields.APP_RTSP_STATUS, val))

            if Fields.DEVICE_NAME in changed_fields:
                val = as_colored_text(new_state.device_name)
                updates.append((idx, Fields.DEVICE_NAME, val))

            if Fields.RED_LIGHT_INDICATORS in changed_fields:
                val = as_colored_text(new_state.red_light_indicators)
                updates.append((idx, Fields.RED_LIGHT_INDICATORS, val))

            if Fields.RECORDING_INFO in changed_fields:
                val_id = None
                val_duration = None
                val_state = None
                if new_state.recording_info and len(new_state.recording_info) > 0:
                    latest_recording_id, latest_recording = sorted(new_state.recording_info.items(), key=lambda x: x[1].started_at, reverse=True)[0]
                    val_id = as_colored_text(latest_recording_id)
                    val_duration = as_colored_text(str(timedelta(seconds=latest_recording.duration)) if latest_recording.duration is not None else None)
                    val_state = as_colored_text(str(latest_recording.state.name)) if latest_recording.state is not None else None
                updates.append((idx, "PL_Rec", val_state))
                updates.append((idx, "PL_Rec_ID", val_id))
                updates.append((idx, "PL_Rec_Duration", val_duration))
                

            # Update rendered state tracker
            if ip_addr not in self._rendered_state:
                self._rendered_state[ip_addr] = {}
            self._rendered_state[ip_addr].update(changed_fields)

        # Apply updates to TUI
        with self.app.batch_update():
            for idx, field, val in updates:
                table.update_cell(self.row_keys[idx], self._field_to_column(field), val, update_width=True)


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

    def _field_to_column(self, field: str) -> Optional[str]:
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
            "PL_Rec": self.column_keys[13],
            "PL_Rec_ID": self.column_keys[14],
            "PL_Rec_Duration": self.column_keys[15],
        }
        return mapping.get(field)

    def _action_key(self, target, key_code):
        """Remotely perform an action-key press on the specified device via ADB.

        Args:
            target (str): The target device identifier.
            key_code (int): The key event code to be sent.
        """
        subprocess.getoutput(f'adb -s {target} shell input keyevent {str(key_code)}')

    def unlock_phone(self, target):
        """Remotely unlock the specified phone using ADB key events.
        This functionality was required as the recordings triggered with a locked phone would not record with audio.
        Ideally, this behaviour should be identified and corrected in properitary vendor apps (Neon companion in this case)

        Args:
            target (str): The target device identifier.
        """
        self._action_key(target, 26)
        time.sleep(1)
        # self._action_key(target, 26)
        # time.sleep(0.4)
        self._action_key(target, 82)
        time.sleep(1)
        # self._action_key(target, 82)
        # time.sleep(0.)
        subprocess.getoutput(f"adb -s {target} shell input text 2023")
        time.sleep(0.5)
        self._action_key(target, 66)

    def lock_phone(self, target):
        """Remotely lock the specified phone if it is currently unlocked.

        Args:
            target (str): The target device identifier.
        """
        screen_on = subprocess.getoutput(f'adb -s {target} shell dumpsys input_method | grep screenOn')
        screen_on = 'true' in screen_on

        if screen_on:
            self._action_key(target, 26)

    def start_recording(self, ip_addr):
        """Start recording on the specified device.

        This method unlocks the phone, sends a request to start recording and then locks the phone again.
        The unlocking ensures proper recording of audio and locking again ensures that the app is not accessed through the phone.

        Args:
            ip_addr (str): The IP address of the target device.

        Returns:
            dict: The JSON response from the recording API, if successful.
        """
        res = None
        # self.unlock_phone(ip_addr); time.sleep(3) ## PL Neon can now record audio on locked devices so this is not required anymore

        try:
            self.logger.info(f'Start recording on {ip_addr}')
            res = requests.post(f"http://{ip_addr}:8080/api/recording:start", timeout=2).json()
            time.sleep(0.1)
            self.lock_phone(ip_addr)
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



if __name__ == "__main__":
    app = TableApp()
    app.run()
