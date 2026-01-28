#!/usr/bin/env python3
"""
quickstart.py

SocialEyes Environment Setup & Validation Tool

This script guides users through the setup process, detecting missing dependencies,
offering to download/install them, and validating the environment before allowing
the user to proceed with the demo.

Author: Alex
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


def run_command(cmd, capture=False, check=True, timeout=5):
    """Run a shell command safely."""
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        else:
            return subprocess.run(cmd, check=check, timeout=timeout).returncode == 0, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def check_python_version() -> bool:
    """Check if Python version is 3.10+."""
    print_step(1, "Checking Python version...")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major >= 3 and version.minor >= 10:
        print_ok(f"Python {version_str} ✓")
        return True
    else:
        print_error(f"Python {version_str} (requires 3.10+)")
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
        return False, docker_path


def download_adb() -> Optional[str]:
    """Download and extract ADB for the current platform."""
    system = platform.system()
    
    # Determine platform-specific URL and executable name
    if system == "Windows":
        adb_url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
        adb_name = "adb.exe"
        os_name = "Windows"
    elif system == "Darwin":
        adb_url = "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
        adb_name = "adb"
        os_name = "macOS"
    elif system == "Linux":
        adb_url = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
        adb_name = "adb"
        os_name = "Linux"
    else:
        print_warn(f"Unknown operating system: {system}")
        print_info("Visit: https://developer.android.com/tools/releases/platform-tools")
        return None

    print_info(f"Downloading Android SDK Platform Tools for {os_name}...")
    print_info("Source: https://developer.android.com/tools/releases/platform-tools")

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

        # Make adb executable on Unix-like systems
        adb_path = os.path.join(tools_dir, adb_name)
        if system != "Windows":
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

    # Check ANDROID_PLATFORM_TOOLS environment variable first
    if "ANDROID_PLATFORM_TOOLS" in os.environ:
        tools_dir = os.environ["ANDROID_PLATFORM_TOOLS"]
        adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
        adb_path = os.path.join(tools_dir, adb_name)
        if os.path.exists(adb_path):
            print_ok(f"ADB found via ANDROID_PLATFORM_TOOLS: {adb_path}")
            return True, adb_path

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
        adb_path = download_adb()
        if adb_path and os.path.exists(adb_path):
            return True, adb_path

    return False, None


def check_git_submodules():
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
        else:
            print_info("Start the Docker daemon and run this script again:")
            print_info("  • systemctl start docker")
        print()
        return False
    else:
        # Docker is not installed
        print_error("Docker is required for this setup")
        print_info("Install Docker from: https://www.docker.com/products/docker-desktop/")
        print()
        return False

    adb_ok, adb_path = check_adb(offer_download=True)
    if adb_ok:
        checks_passed += 1

    if check_git_submodules():
        checks_passed += 1

    print()
    print(f"Environment checks: {checks_passed}/{checks_total} passed")

    return checks_passed >= 4  # Need Python + Docker + ADB + Git submodules


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


def validate_docker_image() -> bool:
    """Check if Docker image is available, build if needed."""
    success, output = run_command(["docker", "image", "inspect", "socialeyes-img"], capture=True, check=False)

    if success:
        print_ok("Docker image already exists")
        return True
    else:
        print_info("Docker image not found. Building now...")
        return build_docker_image()


def setup_source_mode() -> bool:
    """Setup and validate source mode."""
    print_header("Setting Up Source Mode")

    if not install_requirements_source():
        return False

    if not validate_source_installation():
        return False

    return True


def setup_container_mode() -> bool:
    """Build and validate Docker image."""
    print_header("Docker Setup")
    return build_docker_image()


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


def print_next_steps() -> str:
    """Print next steps and action menu, return user's choice."""
    print_header("Setup Complete! 🎉")

    print("You're ready to use SocialEyes!\n")

    print(f"{Colors.BOLD}Quick commands:{Colors.ENDC}")
    print("  • Run the demo in Docker:")
    print(f"    {Colors.OKCYAN}python demo_docker.py{Colors.ENDC}")
    print("  • Connect phones via ADB:")
    print(f"    {Colors.OKCYAN}python adb_helper.py{Colors.ENDC}\n")

    print(f"{Colors.BOLD}For more information:{Colors.ENDC}")
    print("  - See README.md for detailed documentation")
    print("  - Visit: https://github.com/beatlab-mcmaster/SocialEyes\n")

    print(f"{Colors.BOLD}What would you like to do?{Colors.ENDC}\n")

    print("  [1] Run the demo in Docker")
    print("  [2] Connect phones via ADB")
    print("  [3] Exit")

    print()

    while True:
        choice = input("Enter your choice [1-3]: ").strip()
        if choice in ["1", "2", "3"]:
            return choice
        print_error("Invalid choice. Please enter 1, 2, or 3.")


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


def handle_user_action(choice: str):
    """Handle the user's chosen action."""
    actions = {
        "1": ("Start demo in Docker", lambda: launch_demo_container()),
        "2": ("Use ADB Helper", lambda: launch_connect_helper()),
    }

    if choice == "3":
        print("\n✓ Exiting SocialEyes quickstart")
        return False

    action_name, action_func = actions[choice]
    print(f"\n{Colors.BOLD}→ {action_name}{Colors.ENDC}")
    return action_func()


def main():
    """Main entry point."""
    try:
        # Step 1: Environment checks
        if not setup_environment_check():
            print_error("Environment validation failed. Please check the errors above.")
            sys.exit(1)

        # Step 2: Setup Docker (check/build image as needed)
        if not validate_docker_image():
            print_error("Docker image setup failed")
            sys.exit(1)

        # Step 3: Show action menu
        while True:
            choice = print_next_steps()
            handle_user_action(choice)
            
            if choice == "3":
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
                print("\n✓ Exiting SocialEyes quickstart")
                break

    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
