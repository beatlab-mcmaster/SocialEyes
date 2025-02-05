"""
main.py

Author: Shreshth Saxena, Alexander Nguyen
Purpose: Implements the main interface to monitor and control multiple devices in the recording mode.
"""

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer
from rich.text import Text
import numbers
from adb_wrapper import AdbWrapper
import threading
import requests
import subprocess
import time
from datetime import datetime, timedelta
from textual_utils import SelectableRowsDataTable
from device import Device
from OffsetLogger import OffsetLogger
from config import config

import logging
logging.getLogger('pupil_labs.realtime_api.time_echo').setLevel(logging.ERROR)
logger = logging.getLogger('main_device_monitor')

#Define column fields
COLUMNS = ("Check", "Device", "IP", "PING", "WIFI", "ADB", "Battery", "Storage", "USB", "RED_INDICATOR", 
        "App", "API", "RTSP", 
        "PL_Rec" , "PL_Rec_ID", "PL_Rec_Duration"
        #"Vibration", "White_LED"
        )

class TableApp(App):
    #could set as reactive elements so we can "watch" it. Alternatively, update at a fixed time interval.
    #ping = reactive(list(range(N_DEVICES))) 
    row_keys = []
    column_keys = []
    devices = []
    offset_logger: OffsetLogger = None

    restart_app_in_progress = False

    def on_mount(self) -> None:
        """
        Initializes the app upon mounting.

        Sets up the device table, generates IP addresses for devices, and schedules
        periodic updates for various metrics related to the devices.
        """
        table = self.query_one(SelectableRowsDataTable)
        table.cursor_type = "row"
        self.column_keys = table.add_columns(*COLUMNS) #is_valid_column_index(self, column_index) can be used to verify

        self.devices = []
        
        #Generate ip addrs of devices using config parameters
        network_id = config["network_id"]
        host_id_range = range(config["host_id"]["start"], config["host_id"]["end"]+1)
        
        for host_id in host_id_range:
            d = Device(f'{network_id}.{host_id}', '5555')
            self.devices.append(d)

        data = [(None, d.ip_addr, None, None, None, None, None, None, None, None, None, None, None, None, None) for d in self.devices]
        self.row_keys = table.add_rows(data)
        table.styles.scroll_x = "scroll_x"

        #Splitting columns into two batches with different update timers. This setting could be configured further with more batches or a single batch.
        self.set_interval(3, self.batch_col_update1)
        self.set_interval(5, self.batch_col_update2)

        self.table_app_start_time = datetime.now()

    def batch_col_update1(self):
        """
        Updates the first batch of columns.
        """
        self.update_ping()
        self.update_wifi()
        self.update_adb_status()
        self.update_usb_connections()
        #self.update_vibrator_events()
        self.update_red_light_indicators()
        self.update_storage()
        self.update_battery()
        self.update_app_active()

    def batch_col_update2(self):
        """
        Updates the second batch of columns.
        """
        self.update_app_api_status()
        self.update_app_rtsp_status()
        self.update_app_recording_status()
        self.update_app_identifiers()

    def update_cell_if_changed(self, row_key, column_key, val, update_width=False):
        """Update a specific cell in the data table if its value has changed.

        Args:
            row_key: The key identifying the row to be updated.
            column_key: The key identifying the column to be updated.
            val: The new value to set in the cell.
            update_width (bool): Optional; if True, adjust the column width to fit all values.
        """
        table = self.query_one(SelectableRowsDataTable)

        current_val = table.get_cell(row_key, column_key)
        if current_val != val:
            #table._data[row_key][column_key] = val
            table.update_cell(row_key, column_key, val, update_width=update_width)

    @work(thread=True)
    async def update_ping(self) -> None:
        """Update the ping status for each device.

        This method retrieves the ping value from each device and updates the 
        corresponding cell in the data table with a colored representation 
        based on thresholds.
        """
        def task(r_idx, d):
            val = d.ping
            val = as_colored_text(val, reverse=True, thresh_low=100, thresh_high=500)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[3], val)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_wifi(self) -> None:
        """Update the WiFi networks for each device.

        This method retrieves the WiFi networks from each device and updates 
        the corresponding cell in the data table, applying a colored format.
        """
        def task(r_idx, d):
            val = d.wifi_networks
            val = as_colored_text(val)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[4], val, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()
        
    @work(thread=True)
    async def update_battery(self) -> None:
        """Update the battery level for each device.

        This method retrieves the battery level from each device and updates 
        the corresponding cell in the data table with a colored representation 
        based on defined thresholds.
        """

        def task(r_idx, d):
            val = d.battery_level
            val = as_colored_text(val, thresh_low=25, thresh_high=50)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[6], val)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()
    @work(thread=True)
    async def update_adb_status(self) -> None:
        """Update the ADB status for each device.

        This method retrieves the ADB status from each device and updates 
        the corresponding cell in the data table, applying a colored format.
        """
        def task(r_idx, d):
            val = d.adb_status
            val = as_colored_text(val)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[5], val, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()    

    @work(thread=True)
    async def update_storage(self) -> None:
        """Update the free disk space for each device.

        This method retrieves the available disk space from each device and 
        updates the corresponding cell in the data table with a colored 
        representation based on defined thresholds.
        """
        def task(r_idx, d):
            val = d.free_disk_space
            val = as_colored_text(val, thresh_low=25, thresh_high=50)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[7], val)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_usb_connections(self) -> None:
        """Update the USB connections status for each device.

        This method checks connected USB devices for each device and updates 
        the corresponding cell in the data table, indicating if certain devices 
        are connected.
        """
        def task(r_idx, d):
            val = d.connected_usb_devices
            usb_connections = None
            if val is not None:
                product_names = sorted([p["product_name"] for p in d.connected_usb_devices])
                usb_connections = set(['Neon Scene Camera v1', 'Neon Sensor Module v1']).issubset(set(product_names))
            usb_connections = as_colored_text(usb_connections)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[8], usb_connections, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_vibrator_events(self) -> None:
        """Update the vibrator events for each device.

        This method was implemented to detect Pupil Neon App crashes or errors marked by recent vibrator events.
        It was used for remote troubleshooting during tests since these app crashes were frequent and are not handled by pupil-labs-realtime-api
        """
        def task(r_idx, d):
            val = d.vibrator_events
            vibrator_status = None
            if val is not None:
                for e in val:
                    if e['create_time'].astimezone() > (self.table_app_start_time.astimezone()):
                        since_time_locale = e["create_time"].astimezone().strftime("%m-%d %H:%M:%S")
                        vibrator_status = f'PROBABLY_RED_FLASHING (at {since_time_locale})'
            
            #self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[9], vibrator_status, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_red_light_indicators(self) -> None:
        """Update the red light indicators for each device.

        Similar to vibrator events, Pupil Neon App crashes/errors were also marked by accompanying red-light on the glasses in certain cases.
        This method was used to remotely troubleshoot those cases during tests since they are not handled by or signalled on the pupil-labs-realtime-api
        """
        def task(r_idx, d):
            val = d.red_light_indicators
            red_light_indicators = None
            recordings = d.app_recordings
            if val is not None and recordings is not None and len(recordings) > 0:
                red_light_indicators = []
                for recording_id,recording_obj in recordings.items():
                    if recording_id not in val:
                        continue
                    indicators = val[recording_id]
                    for e in indicators:
                        time_locale = e['time'].astimezone().strftime("%m-%d %H:%M:%S")
                        vibrator_status = time_locale
                        red_light_indicators.append(vibrator_status)
            if red_light_indicators is not None:
                red_light_indicators = ', '.join(red_light_indicators)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[9], red_light_indicators, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_app_active(self) -> None:
        """Update the active app status for each device.

        This method retrieves the app status property from each device and updates 
        the corresponding cell in the data table with a colored representation.
        """
        def task(r_idx, d):
            val = d.app_status
            val = as_colored_text(val)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[10], val, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_app_api_status(self) -> None:
        """Update the API status for each device.

        This method retrieves the app API status property from each device and updates 
        the corresponding cell in the data table with a colored representation.
        """
        def task(r_idx, d):
            val = d.app_api_status
            val = as_colored_text(val)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[11], val, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_app_rtsp_status(self) -> None:
        """Update the RTSP status for each device.

        This method retrieves the RTSP status from each device and updates 
        the corresponding cell in the data table with a colored representation.
        """
        def task(r_idx, d):
            val = d.app_rtsp_status
            val = as_colored_text(val)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[12], val, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()
    
    @work(thread=True)
    async def update_app_recording_status(self) -> None:
        """Update the recording status for each device.

        This method checks the app recording state and updates multiple 
        cells in the data table with the recording state, ID, and duration.
        """
        def task(r_idx, d):
            val = d.app_recordings
            
            rec = len(val) > 0
            rec_id = rec_duration = None
            rec_state = None
            rec_duration = None

            if rec:
                rec_id = list(val.keys())[0] # most recent recording obj

                recording_obj = val[rec_id]
                rec_id = None if not rec else ", ".join([uuid.split('-')[0] + '-...' for uuid in val.keys()])
                rec_duration = recording_obj['rec_duration']
                rec_state = recording_obj['rec_state'].name
                
                rec = Text(str(rec), style='red on red') if rec else Text(str(rec), style='')

            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[13], rec_state, update_width=True)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[14], rec_id, update_width=True)
            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[15], rec_duration, update_width=True)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()

    @work(thread=True)
    async def update_app_identifiers(self) -> None:
        """Update the app identifiers for each device.

        This method retrieves the app device name and updates the 
        corresponding cell in the data table.
        """
        def task(r_idx, d):
            device_name = d.app_device_name
            #frame_name = d.app_frame_name
            #module_serial = d.app_frame_name

            self.update_cell_if_changed(self.row_keys[r_idx], self.column_keys[1], device_name)

        for r_idx,d in enumerate(self.devices):
            task(r_idx, d)
            #t = threading.Thread(target=task, args=(r_idx, d), daemon=True)
            #t.start()


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
        self.unlock_phone(ip_addr)
        time.sleep(3)

        try:
            logger.info(f'Start recording on {ip_addr}')
            res = requests.post(f"http://{ip_addr}:8080/api/recording:start", timeout=2).json()
            time.sleep(0.1)
            self.lock_phone(ip_addr)
        except Exception as e:
            logger.error(f'{ip_addr}, {e}')
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
            logger.info(f'Stop and save recording on {ip_addr}')
            res = requests.post(f"http://{ip_addr}:8080/api/recording:stop_and_save", timeout=2).json()
        except Exception as e:
            logger.error(f'{ip_addr}, {e}')
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
            logger.info(f'Stop and discard recording on {ip_addr}')
            res = requests.post(f"http://{ip_addr}:8080/api/recording:cancel", timeout=2).json()
        except Exception as e:
            logger.error(f'{ip_addr}, {e}')
            print(e)
            pass
        return res   

    #Defining actions
    @work(exclusive=True, thread=True)
    async def action_recording_start(self) -> None:
        """Start recording on selected devices.

        This method retrieves the selected devices from the UI and starts 
        recording on each one, logging the offsets if required.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        logger.info("Selected devices ({}): {}".format(len(selected_devices), selected_devices))
        print("STARTING REC on selected devices")
        
        if not self.offset_logger:
            self.offset_logger = OffsetLogger(selected_devices)
            logger.info(f"Starting Offset logger at {self.offset_logger.log_file}")
            self.offset_logger.log_offsets()
        for d in selected_devices:
            t = threading.Thread(target=self.start_recording, args=(d,), daemon=True)
            t.start()
    

    ## Implementing action keys below to control the execution of certain operations manually by the operator.
    
    @work(exclusive=True, thread=True)
    async def action_recording_stop_and_save(self) -> None:
        """Stop and save recording on selected devices.

        This method retrieves the selected devices from the UI and stops 
        recording on each one, logging the offsets if they were started.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        logger.info("Selected devices ({}): {}".format(len(selected_devices), selected_devices))
        print("STOPPING REC on selected devices")

        if self.offset_logger:    
            logger.info("Stopping Offset logger")
            self.offset_logger.stop_logging()
            self.offset_logger = None
        logger.info("Stopping recording on devices")
        for d in selected_devices:
            t = threading.Thread(target=self.stop_and_save_recording, args=(d,), daemon=True)
            t.start()

    @work(exclusive=True, thread=True)
    async def action_recording_stop_and_discard(self) -> None:
        """Stop and discard recording on selected devices.

        This method retrieves the selected devices from the UI and stops 
        recording on each one, logging the offsets if they were started.
        """
        table = self.query_one(SelectableRowsDataTable)
        selected_devices = [row.data[1] for row in table.selected_rows]
        logger.info("Selected devices ({}): {}".format(len(selected_devices), selected_devices))
        print("DISCARDING REC on selected devices")

        if self.offset_logger:
            logger.info("Stopping Offset logger")
            self.offset_logger.stop_logging()
            self.offset_logger = None
        logger.info("Stopping recording on devices")
        for d in selected_devices:
            t = threading.Thread(target=self.stop_and_discard_recording, args=(d,), daemon=True)
            t.start()

    @work(exclusive=True, thread=True)
    async def action_restart_app_on_devices(self) -> None:
        """Restart the app on selected devices.

        This method retrieves the selected devices from the UI and restarts 
        the Neon Companion application on each one.
        """
        logger.info('action_restart_app_on_devices triggered!')
        if self.restart_app_in_progress:
            logger.info('Another restart progress is already in progress, nothing to do...')
            return
        print("RESTARTING APP on selected devices")
        
        try:
            self.restart_app_in_progress = True

            table = self.query_one(SelectableRowsDataTable)
            selected_device_ip_addrs = [row.data[1] for row in table.selected_rows]
            logger.info("Selected devices ({}): {}".format(len(selected_device_ip_addrs), selected_device_ip_addrs))

            def f(ip_addr):
                logger.info(f'Restarting app on {ip_addr}...')
                adb_wrapper = AdbWrapper(ip_addr)
                adb_wrapper.stop_neon_companion_app()
                adb_wrapper.start_neon_companion_app()
                logger.info(f'Restarting app on {ip_addr} has finished!')
            
            tasks = []
            for ip_addr in selected_device_ip_addrs:
                t = threading.Thread(target=f, args=[ip_addr])
                tasks.append(t)
                t.start()
            
            for t in tasks:
                t.join()
            logger.info(f'Restarting apps has finished!')
        finally:
            self.restart_app_in_progress = False
            logger.info(f'self.restart_app_in_progress = False')

    @work
    async def action_reconnect_adb(self) -> None:
        """
        Attempts to reconnect to an Android Debug Bridge (ADB) device at the specified IP address(es).
        """

        print("RESTARTING ADB on selected devices!")
        table = self.query_one(SelectableRowsDataTable)
        selected_device_ip_addrs = [row.data[1] for row in table.selected_rows]
        logger.info("Selected devices ({}): {}".format(len(selected_device_ip_addrs), selected_device_ip_addrs))          

        for ip_addr in selected_device_ip_addrs:
            logger.info(f'Restarting adb on {ip_addr}...')
            res = subprocess.run("adb connect {}:5555".format(ip_addr), shell=True, capture_output=True, text=True).stdout
            logger.info(res.strip())
        
        print('FINISHED restarting adb on all devices!')


    BINDINGS = [
        Binding(key="q", action="quit", description="Quit the app"),
        Binding(key="r", action="recording_start", 
            description="Start Recording"), 
        Binding(key="s", action="recording_stop_and_save", 
            description="Save Recording"), 
        Binding(key="u", action="recording_stop_and_discard", 
           description="Cancel Recording"), 
        Binding(key="o", action="restart_app_on_devices", description="Restart App"),
        Binding(key="a", action="reconnect_adb", description="Reconnect adb"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the Textual TUI.

        Returns:
            ComposeResult: The composed result containing UI elements.
        """
        yield SelectableRowsDataTable()
        yield Footer()

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


