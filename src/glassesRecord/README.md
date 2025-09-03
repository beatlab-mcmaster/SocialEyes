# GlassesRecord Module
This module is used to remotely operate the Pupil Labs Neon eye-tracking glasses and record data on multiple devices along with offsets for time-synchronisation.
The module provides a Terminal User Interface for easy interaction. 

## Prerequisites

- Connect all NEON eye-trackers to the same local network as the server. Ensure that Neon Companion app is running on all devices.

### Android Debug Bridge

To gain access to all status metrics in the TUI, you'll need to install ADB on the server and setup a WiFi ADB pairing of the server with each device.<br>
Please find detailed instructions about ADB on the [official documentation](https://developer.android.com/tools/adb). <br>
To summarize the important steps:

1. Install ADB
    - **Windows**: [Install ADB on Windows](https://developer.android.com/studio#downloads) (download and extract the ADB platform tools).
    - **macOS**: [Install ADB on macOS using Homebrew](https://brew.sh/) (run `brew install android-platform-tools` in Terminal).
    - **Linux**: [Install ADB on Linux](https://www.android.com/studio) (run `sudo apt install android-tools-adb` on Ubuntu/Debian or use your package manager for other distributions).


2. Initialize ADB TCP/IP Connection on each device
    - Connect the device via USB (make sure USB debugging is enabled on the device).
    - Open the terminal or command prompt and run:

            ```
            adb tcpip 5555
            adb connect <device_ip>:5555
            ```
        Replace <device_ip> with the IP address of your device. You can find the device's IP address in the device's Wi-Fi settings.
    - Disconnect the device and verify the connection by running:
            ```
            adb devices
            ```


## Usage

1. Install the requirements with `pip install -r requirements.txt` 

2. Check the network config parameters in `config.json` so the devices could be found on network.

3. Configure other parameters in `config.json`. See the next section for parameter descriptions.

4. Run the module with `python3 main.py` 

## Config

The following parameters can be set in config.json to configure your recording session:

    - By default, SocialEyes will look for a range of IP addresses provided using the following config parameters:

        ```
        {
            "network_id": "192.168.50",  // The base IP address for the network. This defines the subnet in which devices will be located.
            
            "host_id": {
                "start": 101,             // The starting host ID for devices on this network. This will be appended to the network ID to form the complete IP address (e.g., 192.168.50.101).
                "end": 129                // The ending host ID for devices on this network. This defines the range of IP addresses available (e.g., from 192.168.50.101 to 192.168.50.129).
            }
        }

        ```

    Alternatively, you can specify individual device IP addresses using the `ip_list` parameter. This is helpful when you have less number of devices and/or non-sequential IP addresses. Remember to set `"network_id"` to an empty string (`""`) in this case:


        ```
        {
            "ip_list": [
                "192.168.50.101",
                "192.168.50.105",
                "192.168.50.110"
            ]
        }
        ``` 

    - The `"logs"` section lets you set:
        - `"path"`: Directory where log files will be stored.
        - `"level"`: Logging verbosity (e.g., `"INFO"`, `"DEBUG"`).
        - `"interval"`: Time interval (in seconds) for periodic logging or updates.

    - The `"single_session_mode"` option controls whether the recording session will involve a single recording start (and stop) for all releavant devices (`true`) OR it requires multiple concurrent recording starts with different batches of devices (`false`). 

    - The `"update_times"` section allows you to specify custom update intervals for different batches of device metrics. 

        ```
        **Batch 1 Metrics**

        PING (Device network latency)
        WIFI (WiFi networks)
        ADB (ADB connection status)
        USB (USB connections)
        RED_INDICATOR (Red light indicator events)
        Storage (Free disk space)
        Battery (Battery level)
        App (Active app status)
        
        **Batch 2 Metrics**
        
        API (App API status)
        RTSP (RTSP streaming status)
        PL_Rec (Recording state)
        PL_Rec_ID (Recording ID)
        PL_Rec_Duration (Recording duration)
        Device (App device name/identifier)
        ```

### Debugging and Logs
- Run the following command to start the application in development mode: `textual run --dev main.py`
- In a separate terminal, run `textual console -x WORKER -x EVENT -x SYSTEM`. The -x tags are used to decrease verbosity by excluding log messages to specific groups (SYSTEM, PRINT, ERROR, WARNING, EVENT, DEBUG, INFO, LOGGING, and WORKER). Use the tags as needed.     