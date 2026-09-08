#!/usr/bin/env python3
"""
adb_helper.py

Cross-platform helper script to monitor USB-connected Android devices
and automatically convert them to TCP/IP adb connections.

Notes:
- ANDROID_PLATFORM_TOOLS environment variable can be set to specify the location of adb.
- If adb is not found, the script will provide instructions to install it.

Author: Alex
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import time


def find_adb() -> str | None:
    """
    Find ADB executable (cross-platform).

    Returns
    -------
    str | None
        Path to adb executable if found, otherwise None.
    """
    # Check ANDROID_PLATFORM_TOOLS environment variable first
    if "ANDROID_PLATFORM_TOOLS" in os.environ:
        tools_dir = os.environ["ANDROID_PLATFORM_TOOLS"]
        adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
        adb_path = os.path.join(tools_dir, adb_name)
        if os.path.exists(adb_path):
            return adb_path
    
    # Try PATH
    adb = shutil.which("adb")
    if adb:
        return adb

    # Check user directory regardless of OS (where quickstart.py downloads to)
    adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
    user_tools_dir = os.path.expanduser(os.path.join("~", ".android", "platform-tools"))
    user_adb_path = os.path.join(user_tools_dir, adb_name)
    if os.path.exists(user_adb_path):
        return user_adb_path

    return None


def run_adb_command(adb_path: str, args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """
    Run an ADB command and return success status and output.
    
    Args:
        adb_path: Path to adb executable
        args: List of arguments to pass to adb
        timeout: Command timeout in seconds
        
    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            [adb_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except Exception as e:
        return False, str(e)

def check_and_handle_unauthorized(adb_path: str, device_id: str) -> bool:
    """
    Check if device is unauthorized and prompt user to allow USB debugging.
    
    Returns True if device becomes authorized, False otherwise.
    """
    success, output = run_adb_command(adb_path, ["devices"], timeout=5)
    
    if "unauthorized" in output.lower() and device_id in output:
        print(f"\nDevice is UNAUTHORIZED")
        print("- ACTION REQUIRED on your phone:")
        print("  1. Look for USB debugging authorization dialog")
        print("  2. CHECK the box 'Always allow from this computer'")
        print("  3. Tap 'Allow' to permit debugging")
        
        # Wait for user to authorize (with timeout)
        print("- Waiting for authorization (timeout: 30 seconds)...", end="", flush=True)
        for attempt in range(30):
            time.sleep(1)
            success, check_output = run_adb_command(adb_path, ["devices"], timeout=5)
            if "device" in check_output and device_id in check_output and "unauthorized" not in check_output:
                print()
                print("  - OK Device authorized!")
                return True
            print(".", end="", flush=True)
        print()
        print("  - ERROR Device authorization timed out")
        return False
    
    return True


def get_connected_devices(adb_path: str):
    """Get list of USB-connected device IDs."""
    success, output = run_adb_command(adb_path, ["devices"])

    if not success:
        print(f"ERROR Failed to query ADB devices: {output}")
        return []

    devices = []
    unauthorized_devices = []
    
    for line in output.split("\n"):
        line = line.strip()

        # Skip headers and empty lines
        if line.startswith("List of") or not line:
            continue

        # Parse device line: "DEVICE_ID    device" or "DEVICE_ID    unauthorized"
        if line.endswith("device"):
            parts = line.split()
            if parts:
                device_id = parts[0]
                # Skip if connected via TCP/IP (has IP address format)
                if re.match(r"^\d+\.\d+\.\d+\.\d+", device_id):
                    continue
                devices.append(device_id)
        
        elif line.endswith("unauthorized"):
            parts = line.split()
            if parts:
                device_id = parts[0]
                unauthorized_devices.append(device_id)

    return devices, unauthorized_devices


def enable_tcpip_on_device(adb_path: str, device_id: str) -> tuple[bool, str]:
    """Enable TCP/IP on a USB-connected device."""
    print(f"- Enabling ADB TCP/IP port on phone...")
    success, output = run_adb_command(adb_path, ["-s", device_id, "tcpip", "5555"])

    if success:
        print(f"  OK ADB TCP/IP port on phone enabled!")
        return True, ""
    else:
        print(f"  ERROR Failed to enable TCP/IP port: {output}")
        return False, output


def get_device_ip(adb_path: str, device_id: str, max_retries: int = 5) -> str | None:
    """Get the IP address of the Wi-Fi interface of a device."""
    for attempt in range(max_retries):
        success, output = run_adb_command(
            adb_path,
            ["-s", device_id, "shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        )

        if success:
            # Parse IP from output like "inet 192.168.1.100/24"
            match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)

        if attempt < max_retries - 1:
            print(f"   Waiting for IP address... (attempt {attempt + 1}/{max_retries})")
            time.sleep(1)

    return None


def connect_device_via_ip(adb_path: str, ip_address: str) -> tuple[bool, str]:
    """Connect to device via TCP/IP."""
    endpoint = f"{ip_address}:5555"
    print(f"  - Connecting to {endpoint}...")

    success, output = run_adb_command(adb_path, ["connect", endpoint])

    if success or "connected to" in output.lower():
        print(f"    - OK")
        return True, ip_address
    else:
        print(f"    - ERROR Failed to connect: {output}")
        return False, ""


def monitor_devices(adb_path: str):
    """Monitor for new USB-connected devices and convert to TCP/IP."""
    print("=" * 60)
    print("SocialEyes ADB Connection Helper")
    print("=" * 60)
    print()
    print("After each phone restart, ADB TCP/IP must be re-enabled.")
    print("Instructions: Make sure \"USB debugging\" is enabled, then connect the phone via USB and unlock the display.")
    print()
    print("Monitoring for USB-connected devices...")
    print("Press Ctrl+C to exit\n")

    processed_devices = set()
    unauthorized_devices_notified = set()
    poll_interval = 0.5  # seconds

    try:
        while True:
            devices, unauthorized_devices = get_connected_devices(adb_path)

            # Handle unauthorized devices
            for device_id in unauthorized_devices:
                if device_id not in unauthorized_devices_notified:
                    print(f"\nNew device detected (UNAUTHORIZED): {device_id}")
                    unauthorized_devices_notified.add(device_id)
                    
                    if check_and_handle_unauthorized(adb_path, device_id):
                        # Device is now authorized, process it normally
                        devices.append(device_id)
                        unauthorized_devices_notified.discard(device_id)

            # Handle authorized devices
            for device_id in devices:
                # Skip if already processed
                if device_id in processed_devices:
                    continue

                print(f"\nNew device detected: {device_id}")
                processed_devices.add(device_id)

                # Step 1: Enable TCP/IP
                if not enable_tcpip_on_device(adb_path, device_id):
                    continue

                # Step 2: Wait for device to restart and get IP
                print("- Initializing TCP/IP connection...")
                time.sleep(2.5)  # Give device time to restart

                ip_address = get_device_ip(adb_path, device_id)
                if not ip_address:
                    print("  - ERROR Could not retrieve device IP address")
                    processed_devices.discard(device_id)  # Retry on next detection
                    continue

                # Step 3: Connect via TCP/IP
                success, _ = connect_device_via_ip(adb_path, ip_address)
                if success:
                    print(f"- OK Successfully connected to {device_id} at {ip_address}")
                else:
                    processed_devices.discard(device_id)  # Retry on next detection

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped")


def main():
    """Main entry point."""
    adb_path = find_adb()

    if not adb_path:
        print("ERROR: ADB executable not found")
        print()
        print("Tried the following locations:")
        print("  1. ANDROID_PLATFORM_TOOLS environment variable")
        print("  2. System PATH")
        print("  3. ~/.android/platform-tools/adb")
        print()
        print("To fix this:")
        print("- Option A: Run quickstart.py to auto-download ADB and")
        print("    unzip it to ~/.android/platform-tools/")
        print("- Option B: Download/install Android SDK Platform Tools and")
        print("    ensure adb is in your PATH or set ANDROID_PLATFORM_TOOLS environment variable")
        print("    https://developer.android.com/tools/releases/platform-tools#downloads")
        
        sys.exit(1)

    print(f"Found ADB: {adb_path}\n")

    monitor_devices(adb_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
