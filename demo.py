"""
demo.py

Author: Shreshth Saxena
Purpose: Quick demo interaction tool.
"""

import questionary
import subprocess
import os
import sys
# sys.path.append("./src/")


if __name__ == "__main__":

    #Clear terminal 
    os.system('cls' if os.name == 'nt' else 'clear')

    #Print message
    questionary.print("""Welcome! This is a reference implementation of SocialEyes built for operation in the recording mode and tested for our Utility Study. \n SocialEyes is built as a collection of modules which could be executed independently from their corresponding paths. \n This demo utility provides an interface for easy interaction with the modules. \n""")
    
    action = questionary.select("Please select an action", qmark = ":",
                        choices = ["Collect eye-tracking data (Opens the Terminal User Interface (TUI) to remotely operate eye-tracking devices)",
                                    "Collect central-camera data (Executes the CentralCam module)",
                                   "Analyse data (Opens the Offline Interface to analyse and visualise collected data)"]).ask()
    
    #There are three main interfaces for SocialEyes: GlassesRecord TUI, CentralCam and Offline interface for analysis/visualisation. All these interfaces can be demoed through this tool below. 
    if action.startswith("Collect eye-tracking data"):
        try:
            result = subprocess.run([sys.executable, "main.py"], check=True, cwd="src/glassesRecord/")
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while running the script")
            print("Please make sure that the src/glassesRecord/config.json file is correctly updated. You can also try executing the main.py script from src/glassesRecord")
    elif action.startswith("Collect central-camera data"):
        try:
            result = subprocess.run([sys.executable, "main.py"], check=True, cwd="src/centralCam/")
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while running the script")
            print("Please make sure that the src/centralCam/config.json file is correctly updated. You can also try executing the main script from src/centralCam")
        except KeyboardInterrupt:
            pass
    else:
        try:
            result = subprocess.run([sys.executable, "main.py"], check=True, cwd="src/offlineInterface")
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while running the script")
            print("You can try executing the main.py script directly from src/offlineInterface")
