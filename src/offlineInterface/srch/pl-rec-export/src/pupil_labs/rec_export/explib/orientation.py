import math
import typing as T

import numpy as np


class OrientationEstimation:
    def __init__(self, gyro_error=50):
        self.q = [1.0, 0.0, 0.0, 0.0]  # vector to hold quaternion
        gyro_mean_error = np.radians(gyro_error)
        self.beta = (
            np.sqrt(3.0 / 4.0) * gyro_mean_error
        )  # compute beta (see README in original github page)
        self.pitch = 0
        self.roll = 0

    def update(
        self,
        accel: T.Tuple[float, float, float],
        gyro: T.Tuple[float, float, float],
        duration_ns: float,
    ):  # 2-tuples (x, y, z) for accel, gyro
        ax, ay, az = accel  # Units G (but later normalised)
        gx, gy, gz = (np.radians(x) for x in gyro)  # Units deg/s
        q1, q2, q3, q4 = (
            self.q[x] for x in range(4)
        )  # short name local variable for readability
        # Auxiliary variables to avoid repeated arithmetic
        _2q1 = 2 * q1
        _2q2 = 2 * q2
        _2q3 = 2 * q3
        _2q4 = 2 * q4
        _4q1 = 4 * q1
        _4q2 = 4 * q2
        _4q3 = 4 * q3
        _8q2 = 8 * q2
        _8q3 = 8 * q3
        q1q1 = q1 * q1
        q2q2 = q2 * q2
        q3q3 = q3 * q3
        q4q4 = q4 * q4

        # Normalise accelerometer measurement
        norm = np.sqrt(ax * ax + ay * ay + az * az)
        if norm == 0:
            return  # handle NaN
        norm = 1 / norm  # use reciprocal for division
        ax *= norm
        ay *= norm
        az *= norm

        # Gradient decent algorithm corrective step
        s1 = _4q1 * q3q3 + _2q3 * ax + _4q1 * q2q2 - _2q2 * ay
        s2 = (
            _4q2 * q4q4
            - _2q4 * ax
            + 4 * q1q1 * q2
            - _2q1 * ay
            - _4q2
            + _8q2 * q2q2
            + _8q2 * q3q3
            + _4q2 * az
        )
        s3 = (
            4 * q1q1 * q3
            + _2q1 * ax
            + _4q3 * q4q4
            - _2q4 * ay
            - _4q3
            + _8q3 * q2q2
            + _8q3 * q3q3
            + _4q3 * az
        )
        s4 = 4 * q2q2 * q4 - _2q2 * ax + 4 * q3q3 * q4 - _2q3 * ay
        norm = 1 / np.sqrt(
            s1 * s1 + s2 * s2 + s3 * s3 + s4 * s4
        )  # normalise step magnitude
        s1 *= norm
        s2 *= norm
        s3 *= norm
        s4 *= norm

        # Compute rate of change of quaternion
        q_dot1 = 0.5 * (-q2 * gx - q3 * gy - q4 * gz) - self.beta * s1
        q_dot2 = 0.5 * (q1 * gx + q3 * gz - q4 * gy) - self.beta * s2
        q_dot3 = 0.5 * (q1 * gy - q2 * gz + q4 * gx) - self.beta * s3
        q_dot4 = 0.5 * (q1 * gz + q2 * gy - q3 * gx) - self.beta * s4

        # Integrate to yield quaternion
        q1 += q_dot1 * (duration_ns * 1e-9)
        q2 += q_dot2 * (duration_ns * 1e-9)
        q3 += q_dot3 * (duration_ns * 1e-9)
        q4 += q_dot4 * (duration_ns * 1e-9)
        norm = 1 / np.sqrt(
            q1 * q1 + q2 * q2 + q3 * q3 + q4 * q4
        )  # normalise quaternion
        self.q = q1 * norm, q2 * norm, q3 * norm, q4 * norm

        # These are modified to account for Invisible IMU coordinate system and
        # positioning of the IMU within the invisible headset
        roll = (
            np.degrees(
                -np.arcsin(2.0 * (self.q[1] * self.q[3] - self.q[0] * self.q[2]))
            )
            + 7
        )
        # bring to range [-180. 180)
        roll = ((roll + 180) % 360) - 180
        self.roll = roll

        pitch = (
            np.degrees(
                np.arctan2(
                    2.0 * (self.q[0] * self.q[1] + self.q[2] * self.q[3]),
                    self.q[0] * self.q[0]
                    - self.q[1] * self.q[1]
                    - self.q[2] * self.q[2]
                    + self.q[3] * self.q[3],
                )
            )
            + 90
        )
        # bring to range [-180. 180)
        pitch = ((pitch + 180) % 360) - 180
        self.pitch = pitch


# def euler_from_quaternion(x, y, z, w):
#     """
#     Convert a quaternion into euler angles (roll, pitch, yaw)
#     roll is rotation around y in radians (counterclockwise)
#     pitch is rotation around x in radians (counterclockwise)
#     yaw is rotation around z in radians (counterclockwise)
#     """
#     t0 = -2.0 * (x * z - y * w)
#     t1 = +2.0 * (w * w + z * z) - 1.0
#     roll_y = np.arctan2(t0, t1)

#     t2 = +2.0 * (x * w + y * z)
#     # t2 = +1.0 if t2 > +1.0 else t2
#     # t2 = -1.0 if t2 < -1.0 else t2
#     t2[t2 > +1.0] = +1.0
#     t2[t2 < +1.0] = +1.0
#     t2 = -1.0 if t2 < -1.0 else t2
#     pitch_x = np.arcsin(t2)

#     t3 = -2.0 * (x * y - z * w)
#     t4 = +2.0 * (y * y + w * w) - 1.0
#     yaw_z = np.arctan2(t3, t4)

#     return roll_y, pitch_x, yaw_z  # in radians


def euler_from_quaternion(x, y, z, w):
    """
    Convert a quaternion into euler angles (roll, pitch, yaw)
    roll is rotation around y in radians (counterclockwise)
    pitch is rotation around x in radians (counterclockwise)
    yaw is rotation around z in radians (counterclockwise)
    """
    t0 = -2.0 * (x * z - y * w)
    t1 = +2.0 * (w * w + z * z) - 1.0
    roll_y = math.atan2(t0, t1)

    t2 = +2.0 * (x * w + y * z)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    pitch_x = math.asin(t2)

    t3 = -2.0 * (x * y - z * w)
    t4 = +2.0 * (y * y + w * w) - 1.0
    yaw_z = math.atan2(t3, t4)

    return roll_y, pitch_x, yaw_z  # in radians
