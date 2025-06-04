"""
config.py

Author: Neil Lobo
Purpose: Reads configurations from a config.json file
"""

import json
import os

def read_config():
    """
    Reads configuration JSON file and loads it into a dictionary
    Returns:
    - dict[str, dict[str, ...]]: Dictionary containing the contents of the config.json file
    """
    with open(os.path.join(os.path.dirname(__file__), 'config.json')) as json_file:
        return json.load(json_file)

config = read_config()