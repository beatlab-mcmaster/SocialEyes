"""
config.py

Authors:  Zahid Mirza, Shreshth Saxena
Purpose: Reads the JSON configuration and exposes it to the SocialEyes modules.
"""

import json
import os

current_dir = os.path.dirname(__file__)

def read_config():
    """
    This function loads a configuration from `config.json`, located in the same directory as the script.
    It also updates the `output_dir` path under the `central` JSON object to be an absolute path based on the current directory.

    Returns:
        dict: The configuration data with updated paths.
    """
    with open(current_dir + os.sep + 'config.json') as json_file:
        json_ = json.load(json_file)
        json_["output_dir"] = os.path.join(current_dir, json_["output_dir"])
        return json_

config = read_config()