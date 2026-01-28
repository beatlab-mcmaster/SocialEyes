#!/usr/bin/env python3
"""
quickstart.py

SocialEyes Environment Setup & Validation Tool

This script guides users through the setup process, detecting missing dependencies,
offering to download/install them, and validating the environment before allowing
the user to proceed with the demo.

Features:
- Python version check
- Docker detection and build
- ADB auto-download (if missing)
- Virtual environment setup
- Dependency installation
- Environment validation
"""

import subprocess
import sys
import platform
import os
import shutil
import urllib.request
import tempfile
import zipfile
import stat
from pathlib import Path
from typing import Tuple, Optional


# Color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text:^70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 70}{Colors.ENDC}\n")


def print_step(step: int, text: str):
    """Print a numbered step."""
    print(f"{Colors.BOLD}{Colors.OKCYAN}[Step {step}]{Colors.ENDC} {text}")


def print_ok(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_warn(text: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def run_command(cmd, capture=False, check=True):
    """Run a shell command safely."""
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            return result.returncode == 0, result.stdout + result.stderr
        else:
            return subprocess.run(cmd, check=check).returncode == 0, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def check_python_version() -> bool:
    """Check if Python version is 3.9+."""
    print_step(1, "Checking Python version...")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major >= 3 and version.minor >= 9:
        print_ok(f"Python {version_str} ✓")
        return True
    else:
        print_error(f"Python {version_str} (requires 3.9+)")
        return False


def find_executable(name: str) -> Optional[str]:
    """Find executable in PATH."""
    return shutil.which(name)


def check_docker() -> Tuple[bool, Optional[str]]:
    """Check if Docker is installed and running."""
    print_step(2, "Checking Docker...")
    docker_path = find_executable("docker")

    if not docker_path:
        print_warn("Docker not found")
        print_info("Install Docker from: https://www.docker.com/products/docker-desktop/")
        return False, None

    print_ok(f"Docker found: {docker_path}")

    # Check if Docker daemon is running
    success, _ = run_command(["docker", "info"], capture=True, check=False)
    if success:
        print_ok("Docker daemon is running")
        return True, docker_path
    else:
        print_warn("Docker daemon is not running")
        system = platform.system()
        if system == "Darwin":
            print_info("Start Docker Desktop and run this script again")
        elif system == "Windows":
            print_info("Start Docker Desktop and run this script again")
        return False, docker_path


def download_adb_windows() -> Optional[str]:
    """Download ADB for Windows and extract it."""
    print_info("Downloading Android SDK Platform Tools for Windows...")
    print_info("Source: https://developer.android.com/tools/releases/platform-tools")

    adb_url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, "platform-tools.zip")

    try:
        urllib.request.urlretrieve(adb_url, zip_path)
        print_ok("Downloaded platform-tools.zip")

        # Extract to user's home directory
        tools_dir = os.path.expanduser("~/.android/platform-tools")
        os.makedirs(tools_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Extract and flatten: platform-tools/* -> ~/.android/platform-tools/
            for member in zip_ref.namelist():
                if member.startswith("platform-tools/"):
                    # Remove 'platform-tools/' prefix
                    target_path = os.path.join(
                        tools_dir, member.replace("platform-tools/", "", 1)
                    )
                    if member.endswith("/"):
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zip_ref.open(member) as source, open(target_path, "wb") as target:
                            target.write(source.read())

        adb_exe = os.path.join(tools_dir, "adb.exe")
        os.remove(zip_path)
        print_ok(f"ADB installed to: {tools_dir}")
        return adb_exe

    except Exception as e:
        print_error(f"Failed to download ADB: {e}")
        return None


def download_adb_macos() -> Optional[str]:
    """Download ADB for macOS and extract it."""
    print_info("Downloading Android SDK Platform Tools for macOS...")
    print_info("Source: https://developer.android.com/tools/releases/platform-tools")

    adb_url = "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, "platform-tools.zip")

    try:
        urllib.request.urlretrieve(adb_url, zip_path)
        print_ok("Downloaded platform-tools.zip")

        # Extract to user's home directory
        tools_dir = os.path.expanduser("~/.android/platform-tools")
        os.makedirs(tools_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                if member.startswith("platform-tools/"):
                    target_path = os.path.join(
                        tools_dir, member.replace("platform-tools/", "", 1)
                    )
                    if member.endswith("/"):
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zip_ref.open(member) as source, open(target_path, "wb") as target:
                            target.write(source.read())

        # Make adb executable
        adb_path = os.path.join(tools_dir, "adb")
        os.chmod(adb_path, os.stat(adb_path).st_mode | stat.S_IEXEC)

        os.remove(zip_path)
        print_ok(f"ADB installed to: {tools_dir}")
        return adb_path

    except Exception as e:
        print_error(f"Failed to download ADB: {e}")
        return None


def download_adb_linux() -> Optional[str]:
    """Download ADB for Linux and extract it."""
    print_info("Downloading Android SDK Platform Tools for Linux...")
    print_info("Source: https://developer.android.com/tools/releases/platform-tools")

    adb_url = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, "platform-tools.zip")

    try:
        urllib.request.urlretrieve(adb_url, zip_path)
        print_ok("Downloaded platform-tools.zip")

        # Extract to user's home directory
        tools_dir = os.path.expanduser("~/.android/platform-tools")
        os.makedirs(tools_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                if member.startswith("platform-tools/"):
                    target_path = os.path.join(
                        tools_dir, member.replace("platform-tools/", "", 1)
                    )
                    if member.endswith("/"):
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zip_ref.open(member) as source, open(target_path, "wb") as target:
                            target.write(source.read())

        # Make adb executable
        adb_path = os.path.join(tools_dir, "adb")
        os.chmod(adb_path, os.stat(adb_path).st_mode | stat.S_IEXEC)

        os.remove(zip_path)
        print_ok(f"ADB installed to: {tools_dir}")
        return adb_path

    except Exception as e:
        print_error(f"Failed to download ADB: {e}")
        return None


def check_adb(offer_download=True) -> Tuple[bool, Optional[str]]:
    """Check if ADB is available or offer to download it."""
    print_step(3, "Checking ADB (Android SDK Platform Tools)...")

    adb_path = find_executable("adb")
    if adb_path:
        print_ok(f"ADB found: {adb_path}")
        return True, adb_path

    if not offer_download:
        return False, None

    # Check common installation paths
    system = platform.system()
    if system == "Windows":
        common_path = os.path.expanduser("~\\.android\\platform-tools\\adb.exe")
    else:
        common_path = os.path.expanduser("~/.android/platform-tools/adb")

    if os.path.exists(common_path):
        print_ok(f"ADB found at: {common_path}")
        return True, common_path

    # Offer to download
    print_info("ADB is needed for device connection over USB->TCP/IP conversion")
    response = input(
        f"{Colors.BOLD}Would you like to download and install ADB? (y/n): {Colors.ENDC}"
    ).strip().lower()

    if response == "y":
        if system == "Windows":
            adb_path = download_adb_windows()
        elif system == "Darwin":
            adb_path = download_adb_macos()
        elif system == "Linux":
            adb_path = download_adb_linux()
        else:
            print_warn(f"Unknown operating system: {system}")
            print_info("Visit: https://developer.android.com/tools/releases/platform-tools")
            return False, None

        if adb_path and os.path.exists(adb_path):
            return True, adb_path

    return False, None


def check_git_submodules() -> bool:
    """Check if git submodules are initialized."""
    print_step(4, "Checking Git submodules...")

    # Check if .gitmodules exists and submodules are initialized
    gitmodules_path = Path(".gitmodules")
    if not gitmodules_path.exists():
        print_ok("No submodules required")
        return True

    # Check if submodules are populated
    try:
        result = subprocess.run(
            ["git", "config", "--file", ".gitmodules", "--name-only", "--get-regexp", "path"],
            capture_output=True,
            text=True,
            check=True,
        )
        submodules = [line.split(".")[-2] for line in result.stdout.strip().split("\n") if line]

        if submodules:
            all_initialized = all(Path(sm).exists() for sm in submodules)
            if all_initialized:
                print_ok(f"Git submodules initialized: {', '.join(submodules)}")
                return True
            else:
                print_warn("Git submodules not fully initialized")
                print_info("Initializing git submodules...")
                run_command(["git", "submodule", "update", "--init", "--recursive"])
                print_ok("Git submodules initialized")
                return True
    except Exception as e:
        print_warn(f"Could not check git submodules: {e}")
        return True  # Don't fail if we can't check


def setup_environment_check() -> bool:
    """Perform all environment checks."""
    print_header("SocialEyes Environment Setup & Validation")

    # Verify we're in the repo root directory
    if not os.path.exists("demo.py") and not os.path.exists("Dockerfile"):
        print_error("This script must be run from the SocialEyes repository root directory")
        print_info("Expected to find: demo.py, Dockerfile, requirements.txt")
        return False

    checks_passed = 0
    checks_total = 4

    if check_python_version():
        checks_passed += 1
    else:
        return False

    docker_ok, docker_path = check_docker()
    if docker_ok:
        checks_passed += 1
    elif docker_path:
        # Docker is installed but daemon is not running
        print_error("Docker daemon is not running")
        system = platform.system()
        if system == "Darwin":
            print_info("Start Docker Desktop on macOS and run this script again:")
            print_info("  • Click the Docker icon in Spotlight (Cmd+Space, type 'Docker')")
            print_info("  • Or open: /Applications/Docker.app")
        elif system == "Windows":
            print_info("Start Docker Desktop on Windows and run this script again:")
            print_info("  • Click Start menu and search for 'Docker Desktop'")
            print_info("  • Or use: Start-Process 'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe'")
        else:
            print_info("Start the Docker daemon and run this script again:")
            print_info("  • systemctl start docker")
            print_info("  • sudo service docker start")
        print()
        return False

    adb_ok, adb_path = check_adb(offer_download=True)
    if adb_ok:
        checks_passed += 1

    if check_git_submodules():
        checks_passed += 1

    print()
    print(f"Environment checks: {checks_passed}/{checks_total} passed")

    return checks_passed >= 2  # Need at least Python + (Docker OR ADB)


def choose_setup_mode() -> str:
    """Let user choose between container or source setup."""
    print_header("Setup Mode")

    print("Choose how you want to run SocialEyes:\n")
    print("  [1] Container (Docker) - Recommended for Windows/macOS")
    print("      - Complete isolated environment")
    print("      - Easier dependency management")
    print("      - No local installation needed")
    print()
    print("  [2] Source - Recommended for Linux developers")
    print("      - Direct Python execution")
    print("      - Easier to debug and modify")
    print("      - Requires local dependencies")
    print()

    while True:
        choice = input("Enter your choice [1 or 2]: ").strip()
        if choice in ["1", "2"]:
            return "container" if choice == "1" else "source"
        print_error("Invalid choice. Please enter 1 or 2.")


def install_requirements_source() -> bool:
    """Install Python requirements for source setup."""
    print_step(5, "Installing Python requirements...")

    if not os.path.exists("requirements.txt"):
        print_error("requirements.txt not found")
        return False

    success, output = run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], capture=True)

    if success:
        print_ok("Python dependencies installed")
        return True
    else:
        print_error("Failed to install dependencies")
        print(output)
        return False


def build_docker_image() -> bool:
    """Build the Docker image."""
    print_step(6, "Building Docker image...")

    if not os.path.exists("Dockerfile"):
        print_error("Dockerfile not found")
        return False

    print_info("Building image (this may take 5-15 minutes on first build)...\n")

    success, output = run_command(["docker", "build", "-t", "socialeyes-img", "."], capture=True)

    if success:
        print_ok("Docker image built successfully")
        return True
    else:
        print_error("Failed to build Docker image")
        print_info("Last error output:")
        print(output[-500:] if len(output) > 500 else output)
        return False


def validate_source_installation() -> bool:
    """Validate that source installation is ready."""
    print_step(7, "Validating source installation...")

    # Check if demo.py exists
    if not os.path.exists("demo.py"):
        print_error("demo.py not found")
        return False

    # Try importing questionary
    try:
        import questionary
        print_ok("Core dependencies validated")
        return True
    except ImportError:
        print_error("Missing required package: questionary")
        return False


def validate_container_installation() -> bool:
    """Validate that Docker image is available."""
    print_step(7, "Validating Docker image...")

    success, output = run_command(["docker", "image", "inspect", "socialeyes-img"], capture=True, check=False)

    if success:
        print_ok("Docker image is ready")
        return True
    else:
        print_error("Docker image not found")
        return False


def setup_source_mode() -> bool:
    """Setup and validate source mode."""
    print_header("Setting Up Source Mode")

    if not install_requirements_source():
        return False

    if not validate_source_installation():
        return False

    return True


def setup_container_mode() -> bool:
    """Setup and validate container mode."""
    print_header("Setting Up Container Mode")

    if not build_docker_image():
        return False

    if not validate_container_installation():
        return False

    return True


def launch_demo_source() -> bool:
    """Launch demo in source mode."""
    print_header("Launching Demo (Source Mode)")
    print("Starting demo.py...\n")

    if not os.path.exists("demo.py"):
        print_error("demo.py not found")
        return False

    try:
        subprocess.run([sys.executable, "demo.py"], check=False)
        return True
    except KeyboardInterrupt:
        print("\n\nDemo stopped by user")
        return True
    except Exception as e:
        print_error(f"Failed to launch demo: {e}")
        return False


def launch_demo_container() -> bool:
    """Launch demo in container mode by invoking demo_docker.py."""
    print_header("Launching Demo (Docker Mode)")
    print("Starting demo in Docker container...\n")

    if not os.path.exists("demo_docker.py"):
        print_error("demo_docker.py not found")
        return False

    try:
        subprocess.run([sys.executable, "demo_docker.py"], check=False)
        return True
    except KeyboardInterrupt:
        print("\n\nDemo stopped by user")
        return True
    except Exception as e:
        print_error(f"Failed to launch demo: {e}")
        return False


def print_next_steps(mode: str) -> str:
    """Print next steps and action menu, return user's choice."""
    print_header("Setup Complete! 🎉")

    print("You're ready to use SocialEyes!\n")

    print(f"{Colors.BOLD}Quick commands:{Colors.ENDC}")

    if mode == "source":
        print("  • Run the demo locally:")
        print(f"    {Colors.OKCYAN}python demo.py{Colors.ENDC}")
        print("  • Run the demo in Docker:")
        print(f"    {Colors.OKCYAN}python demo_docker.py{Colors.ENDC}")
        print("  • Connect phones for TCP/IP mode:")
        print(f"    {Colors.OKCYAN}python adb_helper.py{Colors.ENDC}\n")

    else:  # container
        print("  • Run the demo in Docker:")
        print(f"    {Colors.OKCYAN}python demo_docker.py{Colors.ENDC}")
        print("  • Run the demo locally:")
        print(f"    {Colors.OKCYAN}python demo.py{Colors.ENDC}")
        print("  • Connect phones for TCP/IP mode:")
        print(f"    {Colors.OKCYAN}python adb_helper.py{Colors.ENDC}\n")

    print(f"{Colors.BOLD}For more information:{Colors.ENDC}")
    print("  - See README.md for detailed documentation")
    print("  - Visit: https://github.com/beatlab-mcmaster/SocialEyes\n")

    print(f"{Colors.BOLD}What would you like to do?{Colors.ENDC}\n")

    if mode == "container":
        print("  [1] Start demo in Docker")
        print("  [2] Start demo locally (source mode)")
        print("  [3] Use ADB Helper (USB→TCP/IP)")
        print("  [4] Exit")
    else:
        print("  [1] Start demo locally (source mode)")
        print("  [2] Start demo in Docker")
        print("  [3] Use ADB Helper (USB→TCP/IP)")
        print("  [4] Exit")

    print()

    while True:
        choice = input("Enter your choice [1-4]: ").strip()
        if choice in ["1", "2", "3", "4"]:
            return choice
        print_error("Invalid choice. Please enter 1, 2, 3, or 4.")


def launch_connect_helper() -> bool:
    """Launch the ADB connect helper."""
    print_header("Starting ADB Helper")
    print("Monitoring for USB-connected devices...\n")

    if not os.path.exists("adb_helper.py"):
        print_error("adb_helper.py not found")
        return False

    try:
        subprocess.run([sys.executable, "adb_helper.py"], check=False)
        return True
    except KeyboardInterrupt:
        print("\n\nConnect helper stopped by user")
        return True
    except Exception as e:
        print_error(f"Failed to launch connect helper: {e}")
        return False


def handle_user_action(choice: str, setup_mode: str):
    """Handle the user's chosen action."""
    actions = {
        "container": {
            "1": ("Start demo in Docker", lambda: launch_demo_container()),
            "2": ("Start demo locally", lambda: launch_demo_source()),
            "3": ("Start ADB Connect Helper", lambda: launch_connect_helper()),
        },
        "source": {
            "1": ("Start demo locally", lambda: launch_demo_source()),
            "2": ("Start demo in Docker", lambda: launch_demo_container()),
            "3": ("Start ADB Connect Helper", lambda: launch_connect_helper()),
        },
    }

    if choice == "4":
        print("\n✓ Exiting SocialEyes quickstart")
        return False

    action_name, action_func = actions[setup_mode][choice]
    print(f"\n{Colors.BOLD}→ {action_name}{Colors.ENDC}")
    return action_func()


def main():
    """Main entry point."""
    try:
        # Step 1: Environment checks
        if not setup_environment_check():
            print_error("Environment validation failed. Please check the errors above.")
            sys.exit(1)

        # Step 2: Choose setup mode
        mode = choose_setup_mode()

        # Step 3: Setup based on mode
        if mode == "container":
            if not setup_container_mode():
                print_error("Container setup failed")
                sys.exit(1)
        else:
            if not setup_source_mode():
                print_error("Source setup failed")
                sys.exit(1)

        # Step 4: Print next steps and get user action
        while True:
            choice = print_next_steps(mode)
            handle_user_action(choice, mode)
            
            if choice == "4":
                break
            
            # Ask if user wants to do something else
            print()
            response = (
                input(
                    f"{Colors.BOLD}Do something else? (y/n): {Colors.ENDC}"
                )
                .strip()
                .lower()
            )
            if response != "y":
                print("\n✓ Thank you for using SocialEyes!")
                break

    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
