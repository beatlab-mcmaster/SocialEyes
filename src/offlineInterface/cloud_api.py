"""
cloud_api.py

Author: Shreshth Saxena
Purpose: This file defines functions that are meant to pull all the glasses data (including footage and timestamps)
         from Pupil Cloud. Additionally, it has a function definition for sending events to Pupil Cloud.
"""

import requests
from tqdm import tqdm

def get_workspaces(base_url, headers):
    """
    Gets all the available workspaces from Pupil Cloud

    Parameters:
    - base_url (str): Base URL for Pupil Cloud to pull workspaces from
    - headers (list[str]): Headers to add to the URL (such as the API key)

    Returns:
    - dict[str, str]: Dictionary of all available workspaces (key is the name, value is ID)
    """
    try:
        response = requests.get(base_url+"/workspaces", params = headers)
        if response.status_code == 200:
            data = response.json()
            return {el["name"]: el["id"] for el in data["result"]}
        else:
            print(f"Error: {response.status_code}")
            return None
    except Exception as e:
        print("Exception :", e)
        return None
    
def get_all_recordings(base_url, workspace_id, headers):
    """
    Gets all recordings from the specified workspace

    Parameters:
    - base_url (str): Base URL for Pupil Cloud to pull workspaces from
    - workspace_id (str): ID of the workspace to get the recordings from
    - headers (list[str]): Headers to add to the URL (such as the API key)

    Returns:
    - dict[str, dict[str,...]]: Dictionary of all available workspaces (key is the ID, value are the recordings)
    """
    try:
        response = requests.get(f"{base_url}/workspaces/{workspace_id}/recordings", params = headers)
        if response.status_code == 200:
            data = response.json()
            return {el["id"]: el for el in data["result"]}
        else:
            print(f"Error: {response.status_code}")
            return None
    except Exception as e:
        print("Exception :", e)
        return None
    
def validate_ids(resp, all_recordings):
    """
    Validates that recording IDs specified exist in the workspace

    Parameters:
    - resp (list[str]): List of recording IDs provided by user
    - all_recordings (list[str]): List of all recording IDs in the workspace

    Returns:
    - dict[str, dict[str,...]]: Dictionary of all available workspaces (key is the ID, value are the recordings)
    """
    resp = eval(resp)
    if isinstance(resp, list) and set(resp).issubset(set(all_recordings)):
        return resp
    else:
        raise ValueError("Input is not valid.")
    
def add_events(base_url, workspace_id, recording_id, events, headers):
    """
    Adds events to Pupil Cloud to a specific recording specified

    Parameters:
    - base_url (str): Base URL for Pupil Cloud to pull workspaces from
    - workspace_id (str): ID of the workspace where the recording is located
    - recording_id (str): ID of the recording to add an event to
    - events (object): Event to add to the recording
    - headers (list[str]): Headers to add to the URL (such as the API key)

    Raises:
    - ValueError: If it's unable to send an event
    - Exception: For all other exceptions
    """
    for event in events:
        try:
            event_payload = {
                "name": event.name,
                "offset_s": event.time
            }
            response = requests.post(f"{base_url}/workspaces/{workspace_id}/recordings/{recording_id}/events", json=event_payload, headers=headers)
            if response.status_code == 200:
                return
            else:
                print("Error: ", response.status_code)
                raise ValueError("not able to send event")
        except Exception as e:
            raise e
        
def download_recordings(base_url, workspace_id, params, path):
    """
    Adds events to Pupil Cloud to a specific recording specified

    Parameters:
    - base_url (str): Base URL for Pupil Cloud to pull workspaces from
    - workspace_id (str): ID of the workspace where the recording is located
    - recording_id (str): ID of the recording to add an event to
    - events (object): Event to add to the recording
    - headers (list[str]): Headers to add to the URL (such as the API key)

    Raises:
    - ValueError: If it's unable to send an event
    - Exception: For all other exceptions
    """
    try:
        response = requests.get(f"{base_url}/workspaces/{workspace_id}/recordings:raw-data-export", params = params, stream=True)
        if response.status_code == 200:
            # Get the total file size from the Content-Length header
            total_size = int(response.headers.get('Content-Length', 0))

            with open(path, 'wb') as local_file, tqdm(
                desc="Downloading",
                total=total_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
            ) as pbar:
                # Iterate over the content in chunks and write to the local file
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        local_file.write(chunk)
                        pbar.update(len(chunk))
            print("Successfully downloaded")
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print("Exception :", e)
