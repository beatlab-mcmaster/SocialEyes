from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Mp4File(BaseModel):
    file_name: str
    file_size_bytes: int
    creation_time: datetime
    modification_time: datetime

class NeonRecording(BaseModel):
    workspace_id: str
    recording_id: str
    mp4_files: list[Mp4File]

class NeonStatistics(BaseModel):
    is_active: bool
    recordings: list[NeonRecording]

class StorageStatistics(BaseModel):
    total_gb: int
    used_gb: int
    free_gb: int

class DisplayStatistics(BaseModel):
    is_locked: bool
    is_on: bool

class WifiStatistics(BaseModel):
    ssid: str | None
    bssid: str | None
    rssi: int | None

class UsbDeviceStatistics(BaseModel):
    manufacturer_name: str | None
    product_name: str | None

class PhoneStatistics(BaseModel):
    now: datetime # The phone's current time
    timezone: str
    battery_level: int
    storage: StorageStatistics
    display: DisplayStatistics
    usb_devices: list[UsbDeviceStatistics]
    wifi: WifiStatistics

class DeviceStatistics(BaseModel):
    version: Literal["1.0"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # This computer's current time
    phone: PhoneStatistics
    neon: NeonStatistics