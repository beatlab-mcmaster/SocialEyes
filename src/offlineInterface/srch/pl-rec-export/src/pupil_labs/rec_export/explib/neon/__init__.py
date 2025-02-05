from pathlib import Path
from typing import Generator, Union

import numpy as np

from pupil_labs.neon_recording.stream.imu import imu_pb2
from pupil_labs.neon_recording.stream.imu.imu_stream import parse_neon_imu_raw_packets


imu_dtype = np.dtype(
    [
        ("unix_time_ns", np.uint64),
        ("gyro_x", np.float32),
        ("gyro_y", np.float32),
        ("gyro_z", np.float32),
        ("accel_x", np.float32),
        ("accel_y", np.float32),
        ("accel_z", np.float32),
        ("quaternion_w", np.float32),
        ("quaternion_x", np.float32),
        ("quaternion_y", np.float32),
        ("quaternion_z", np.float32),
    ]
)


def imu_packets_to_numpy(packets: Generator[imu_pb2.ImuPacket, None, None]):
    data = []
    for packet in packets:
        data.append((
            packet.tsNs,
            packet.gyroData.x,
            packet.gyroData.y,
            packet.gyroData.z,
            packet.accelData.x,
            packet.accelData.y,
            packet.accelData.z,
            packet.rotVecData.w,
            packet.rotVecData.x,
            packet.rotVecData.y,
            packet.rotVecData.z,
        ))

    return np.array(data, dtype=imu_dtype)


def raw_imu_file_to_packets(file_path: Union[str, Path]):
    with Path(file_path).open("rb") as handle:
        yield from parse_neon_imu_raw_packets(handle.read())


def raw_imu_file_to_numpy(file_path: Union[str, Path]):
    packet_iterator = raw_imu_file_to_packets(file_path)
    return imu_packets_to_numpy(packet_iterator)
