"""
config.py

Authors: Areez Vizram, Shreshth Saxena
Purpose: Reads the JSON configuration and exposes it to the SocialEyes modules.
"""

import json
import os

current_dir = os.path.dirname(__file__)

def read_config():
    """
    This function loads a configuration from `config.json`, located in the same directory as the script.

    Returns:
        dict: The configuration data as a dictionary.
    """
    with open(current_dir + os.sep + 'config.json') as json_file:
        return json.load(json_file)

config = read_config()