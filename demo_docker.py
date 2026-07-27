#!/usr/bin/env python3
"""
demo_docker.py

Cross-platform starter script for SocialEyes demo with Docker.
Handles Docker startup, ADB server initialization, and demo execution.

Author: Alex (converted from PowerShell/Batch)
"""

import subprocess
import sys
import platform
import time
import shutil
import os


def find_executable(name):
    """Find executable in PATH (cross-platform)."""
    return shutil.which(name)


def is_docker_running():
    """Check if Docker daemon is running."""
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_docker():
    """Start Docker Desktop (platform-specific)."""
    system = platform.system()

    print("Starting Docker Desktop...")

    if system == "Darwin":  # macOS
        try:
            subprocess.Popen(["open", "-a", "Docker"])
        except FileNotFoundError:
            print("❌ Docker not found. Please install Docker Desktop for macOS.")
            return False

    elif system == "Windows":
        try:
            subprocess.Popen("docker desktop start -d", shell=True)
        except Exception as e:
            print(f"❌ Failed to start Docker: {e}")
            return False

    # Linux typically runs Docker as a service, not Docker Desktop
    elif system == "Linux":
        print("ℹ️  On Linux, please ensure Docker daemon is running (e.g., sudo systemctl start docker)")
        return False

    # Wait for Docker to start
    print("Waiting for Docker to start...", end="", flush=True)
    for i in range(60):  # 60 second timeout
        if is_docker_running():
            print(" ✓")
            return True
        print(".", end="", flush=True)
        time.sleep(1)

    print("\n❌ Docker failed to start within timeout.")
    return False


def find_adb():
    """Find ADB executable (cross-platform)."""
    # Check ANDROID_PLATFORM_TOOLS environment variable
    if "ANDROID_PLATFORM_TOOLS" in os.environ:
        adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
        adb_path = os.path.join(os.environ["ANDROID_PLATFORM_TOOLS"], adb_name)
        if os.path.exists(adb_path):
            return adb_path

    # Try PATH
    adb = shutil.which("adb")
    if adb:
        return adb

    # Check user directory (where quickstart.py downloads to)
    adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
    user_adb_path = os.path.expanduser(os.path.join("~", ".android", "platform-tools", adb_name))
    if os.path.exists(user_adb_path):
        return user_adb_path

    return None


def start_adb_server():
    """Start ADB server (cross-platform)."""
    print("2) Starting ADB server...")

    adb_path = find_adb()
    if not adb_path:
        print("❌  ADB not found!")
        return False

    try:
        subprocess.run([adb_path, "start-server"], check=True, capture_output=True, timeout=10)
        print(f"   ✓ ADB server started ({adb_path})")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌  Failed to start ADB server: {e}")
        return False
    except subprocess.TimeoutExpired:
        print("❌  ADB server startup timed out")
        return False
    except Exception as e:
        print(f"❌  Error starting ADB server: {e}")
        return False


def run_demo():
    """Run SocialEyes demo in Docker container."""
    print("\n3) Starting SocialEyes demo...")
    print("   (Press Ctrl+C to exit)\n")

    docker_cmd = [
        "docker",
        "run",
        '--init',
        '--name', 'socialeyes',
        "--rm",
        "-it",
        "--privileged",
        "-v",
        f"{os.getcwd()}:/SocialEyes",
        "--add-host=host.docker.internal:host-gateway",
        "-e",
        "ANDROID_ADB_SERVER_ADDRESS=host.docker.internal",
        "socialeyes-img",
        "python",
        "demo.py",
    ]

    try:
        subprocess.run(docker_cmd, check=True)
    except KeyboardInterrupt:
        print("\n\n   Demo interrupted by user - stopping container...")
        # Docker will clean up the container due to --rm flag
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Demo failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("❌ Docker executable not found")
        return False

    return True


def main():
    """Main entry point."""
    print("=" * 60)
    print("SocialEyes Demo Launcher")
    print("=" * 60)
    print()

    # Step 1: Check Docker
    print("1) Checking Docker...")
    if is_docker_running():
        print("   ✓ Docker is running")
    else:
        if not start_docker():
            print("\n❌ Demo failed to start. Please ensure Docker is installed and running.")
            sys.exit(1)

    # Step 2: Start ADB server (Windows only)
    if not start_adb_server():
        print("\n❌  Warning: ADB server may not be available")

    # Step 3: Run demo
    success = run_demo()
    
    if success:
        print("\n✓ Demo completed successfully")
    else:
        print("\n❌  Demo exited (check output above for details)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
