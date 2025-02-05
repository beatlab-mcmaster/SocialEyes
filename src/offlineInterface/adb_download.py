##TODOs: add docstrings, improve suprocess spawn and exit, tqdm for loading?

import subprocess
import os
import questionary
import pickle


class AdbDownload:
    def __init__(self, root_dir, device_ips = []):
        self.root_dir = root_dir
        self.device_ips = device_ips

        self.local_checksum_cache_path = os.path.join(self.root_dir, 'local_checksum_cache.pkl')
        self.remote_checksum_cache_path = os.path.join(self.root_dir, 'remote_checksum_cache.pkl')

        self.local_checksum_cache = dict()
        if os.path.exists(self.local_checksum_cache_path):
            with open(self.local_checksum_cache_path, 'rb') as f:
                self.local_checksum_cache = pickle.load(f)
        # print(self.local_checksum_cache)

        self.remote_checksum_cache = dict()
        if os.path.exists(self.remote_checksum_cache_path):
            with open(self.remote_checksum_cache_path, 'rb') as f:
                self.remote_checksum_cache = pickle.load(f)

    def _escape_path_with_whitespace(self, raw):
        return raw.replace(' ', '\\\\ ')

    def list_workspaces(self, device_ip):
        """Returns sorted list of workspaces using ls -t"""
        workspaces = subprocess.getoutput(f'adb -s {device_ip}:5555 shell ls -t /storage/self/primary/Documents/Neon/')
        workspaces = [e for e in workspaces.splitlines() if not 'app_android.log' in e]
        return workspaces

    def list_recordings(self,device_ip):
        result = dict()
        workspaces = self.list_workspaces(device_ip)
        
        for workspace in workspaces:
            recordings = subprocess.getoutput(f'adb -s {device_ip}:5555 shell ls /storage/self/primary/Documents/Neon/{self._escape_path_with_whitespace(workspace)}/')
            recordings = recordings.splitlines()
            result[workspace] = recordings

        return result

    def download_neon_folder(self, device_ip):
        target_dir = os.path.join(self.root_dir, device_ip)
        os.makedirs(target_dir, exist_ok= True)
        subprocess.Popen(f'adb -s {device_ip}:5555 pull -a /storage/self/primary/Documents/Neon/ {target_dir}'.split(' '))    

    def download_recordings(self, device_ip):
        recordings = self.list_recordings(device_ip)
        for workspace,recordings in recordings.items():
            for recording in recordings:
                self.download_recording(device_ip, workspace, recording)

    def download_last_recording(self, device_ip):
        workspaces = self.list_workspaces(device_ip)
        workspace = workspaces[0] #last_modified_workspace

        recordings = subprocess.getoutput(f'adb -s {device_ip}:5555 shell ls /storage/self/primary/Documents/Neon/{self._escape_path_with_whitespace(workspace)}/')
        recording = recordings.splitlines()[0]
        self.download_recording(device_ip, workspace, recording)

    def download_recording(self, device_ip, workspace, recording):
        target_dir = os.path.join(self.root_dir, device_ip, workspace, recording)
        os.makedirs(target_dir, exist_ok=True)
        device_path = f'/storage/self/primary/Documents/Neon/{self._escape_path_with_whitespace(workspace)}/{self._escape_path_with_whitespace(recording)}'
        local_path  = target_dir
        subprocess.Popen(f'adb -s {device_ip}:5555 pull -a {device_path} {local_path}'.split(' '))
        #sync_folder(device_ip, device_path, local_path)
        

    def sync_folder(self, device_ip, device_path, local_path, recursive=True):
        local_files = subprocess.getoutput(f'find "{local_path}" -maxdepth 1 -type f').splitlines()
        local_file_checksums = dict()
        
        if not local_path in self.local_checksum_cache:
            self.local_checksum_cache[local_path] = dict()
        else:
            print('Use local cache', self.local_checksum_cache[local_path])
        print('Create local checksums ...')
        for local_file in local_files:
            print(f"\r>> {local_file}", end='')
            local_filename = local_file[len(local_path)+1:]
            if not local_filename in self.local_checksum_cache[local_path]:
                checksum = subprocess.getoutput(f'sha256sum "{local_file}"').split(' ')[0]
                local_file_checksums[local_filename] = checksum
        self.local_checksum_cache[local_path] = local_file_checksums
        with open(self.local_checksum_cache_path, 'wb') as f:
            pickle.dump(self.local_checksum_cache, f)
        print()
        print('Download remote files (incl. checksum comparison) ...')
        remote_files = subprocess.getoutput(f'adb -s {device_ip}:5555 shell find "{device_path}" -maxdepth 1 -type f').splitlines()

        if not device_path in self.remote_checksum_cache:
            self.remote_checksum_cache[device_path] = dict()
        else:
            print('Use remote cache', self.remote_checksum_cache[device_path])
        for remote_file in remote_files:
            print(f"\r>> {remote_file}", end='')
            remote_filename = remote_file[len(device_path)+1:]
            if not remote_filename in self.remote_checksum_cache[device_path]:
                checksum = subprocess.getoutput(f'adb -s {device_ip}:5555 shell sha256sum {self._escape_path_with_whitespace(remote_file)}').split(' ')[0]
                self.remote_checksum_cache[device_path][remote_filename] = checksum
            else:
                checksum = self.remote_checksum_cache[device_path][remote_filename]
            if remote_filename not in self.remote_checksum_cache[device_path] or self.remote_checksum_cache[device_path] != checksum:
                subprocess.getoutput(f'adb -s {device_ip}:5555 pull -a {remote_file} {os.path.join(local_path, remote_filename)}')
                print(f'GET {remote_file}')
            else:
                print(f'SKP {remote_file}')
        with open(self.remote_checksum_cache_path, 'wb') as f:
            pickle.dump(self.remote_checksum_cache, f)

        if recursive:
            remote_dirs = subprocess.getoutput(f'adb -s {device_ip}:5555 shell find {device_path} -maxdepth 1 -type d')
            if not 'No such file or directory' in remote_dirs:
                print('REMOTE_DIRS', remote_dirs)
                print('DEVICE_PATH', device_path)
                for d in remote_dirs.splitlines():
                    if d == device_path:
                        continue
                    d_name = d[len(device_path)]
                    self.sync_folder(device_ip, d, os.path.join(local_path, d_name), recursive)
    

if __name__ == '__main__':

    BASE_TARGET_DIR = questionary.path("Select root directory").ask()
    OPTS = ["Download Neon folder", "Download recordings", "Download latest recording"] 
    device_ips = ["192.168.2.{:d}".format(i+100) for i in range(1, 30+1)]

    selected_dev_ips = questionary.checkbox("Select devices", choices = device_ips).ask()
    assert len(selected_dev_ips) > 0, "Select atleast one device"

    session = AdbDownload(BASE_TARGET_DIR, selected_dev_ips)
    operation = questionary.select("Select operation", choices = OPTS).ask()

    for device_ip in session.device_ips:    
        print(f'DEVICE {device_ip}')
        try:
            if operation == OPTS[0]:
                session.download_neon_folder(device_ip)
            elif operation == OPTS[1]:
                session.download_recordings(device_ip)
            elif operation == OPTS[2]:
                session.download_last_recording(device_ip)
        except Exception as e:
            print(e)
        
