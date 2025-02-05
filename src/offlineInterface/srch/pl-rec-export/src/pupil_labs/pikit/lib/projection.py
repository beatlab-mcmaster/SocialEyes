import numpy as np

HAVE_MP = True
try:
    import mpmath as mp
except ImportError:
    HAVE_MP = False


# scipy is ~5x faster but not always available
HAVE_SCIPY = True
try:
    import scipy.optimize
except ImportError:
    HAVE_SCIPY = False

HAVE_CV = True
try:
    import cv2
except ImportError:
    HAVE_CV = False


def apply_distortion_model(point, dist_coeffs):
    x, y = point
    r = np.linalg.norm([x, y])

    k1, k2, p1, p2, k3, k4, k5, k6 = dist_coeffs

    scale = 1 + k1 * r ** 2 + k2 * r ** 4 + k3 * r ** 6
    scale /= 1 + k4 * r ** 2 + k5 * r ** 4 + k6 * r ** 6

    x_dist = scale * x + 2 * p1 * x * y + p2 * (r ** 2 + 2 * x ** 2)
    y_dist = scale * y + p1 * (r ** 2 + 2 * y ** 2) + 2 * p2 * x * y

    return np.asarray([x_dist, y_dist])


def normalize_points_fast(points, camera_matrix, dist_coeffs, new_camera_matrix=None):
    if len(points) == 0:
        return []

    dist_coeffs = np.squeeze(dist_coeffs).tolist()
    if len(dist_coeffs) == 5:
        dist_coeffs += [0.0, 0.0, 0.0]

    points = np.asarray(points, dtype=np.float32)
    if len(points.shape) == 2:
        points = np.expand_dims(points, axis=1)
        points.shape = -1, 1, 2
    else:
        raise Exception("expect a list/np.array of 2d-points")

    undist_point = cv2.undistortPoints(
        points,
        np.asarray(camera_matrix, dtype=np.float32),
        np.asarray(dist_coeffs, dtype=np.float32),
        P=new_camera_matrix,
    )
    return np.squeeze(undist_point, axis=1).tolist()


def normalize_points_accurate(points, camera_matrix, dist_coeffs):
    if len(points) == 0:
        return []

    dist_coeffs = np.squeeze(dist_coeffs).tolist()
    if len(dist_coeffs) == 5:
        dist_coeffs += [0.0, 0.0, 0.0]

    points = np.asarray(points)

    if len(points.shape) == 1:
        raise Exception("expect a list/np.array of 2d-points")

    normalized_points = []
    for point in points:
        x, y = np.squeeze(point)
        x_prime = (x - camera_matrix[0][2]) / camera_matrix[0][0]
        y_prime = (y - camera_matrix[1][2]) / camera_matrix[1][1]

        if HAVE_SCIPY:
            res = scipy.optimize.root(
                lambda p_norm: apply_distortion_model(p_norm, dist_coeffs)
                - np.asarray([x_prime, y_prime]),
                [x_prime, y_prime],
                method="lm",
            )
            normalized_points.append([res.x[0], res.x[1]])
        elif HAVE_MP:
            res = mp.findroot(
                lambda x, y: apply_distortion_model((x, y), dist_coeffs)
                - np.asarray([x_prime, y_prime]),
                (x_prime, y_prime),
                verbose=False,
                multidimensional=True,
                tol=1e-4,
                solver="muller",
            )
            normalized_points.append([float(res[0]), float(res[1])])
        else:
            raise Exception("no library to perform computation")

    return normalized_points


def distort_points_fast(points, camera_matrix, dist_coeffs):
    if len(points) == 0:
        return []

    dist_coeffs = np.squeeze(dist_coeffs).tolist()
    if len(dist_coeffs) == 5:
        dist_coeffs += [0.0, 0.0, 0.0]

    points = np.asarray(points, dtype=np.float32)
    if len(points.shape) == 2:
        points = np.expand_dims(points, axis=1)
        points.shape = -1, 1, 2
    else:
        raise Exception("expect a list/np.array of 2d-points")

    points_3d = cv2.convertPointsToHomogeneous(points)
    projected_points = cv2.projectPoints(
        np.asarray(points_3d),
        rvec=np.zeros((1, 3)),
        tvec=np.zeros((1, 3)),
        cameraMatrix=np.asarray(camera_matrix),
        distCoeffs=np.asarray(dist_coeffs),
    )[0]
    return np.squeeze(projected_points, axis=1).tolist()


def distort_points_accurate(points, camera_matrix, dist_coeffs):
    if len(points) == 0:
        return []

    dist_coeffs = np.squeeze(dist_coeffs).tolist()
    if len(dist_coeffs) == 5:
        dist_coeffs += [0.0, 0.0, 0.0]

    points = np.asarray(points)

    if len(points.shape) == 1:
        raise Exception("expect a list/np.array of 2d-points")

    distorted_points = []
    for point in points:
        point = np.squeeze(point)
        x_dist_prime, y_dist_prime = apply_distortion_model(point, dist_coeffs)

        x_corr = x_dist_prime * camera_matrix[0][0] + camera_matrix[0][2]
        y_corr = y_dist_prime * camera_matrix[1][1] + camera_matrix[1][2]
        distorted_points.append([x_corr, y_corr])

    return distorted_points


def normalize_point(point, camera_matrix, dist_coeffs):
    return normalize_points_fast([point], camera_matrix, dist_coeffs)[0]


def distort_point(point, camera_matrix, dist_coeffs):
    return distort_points_fast([point], camera_matrix, dist_coeffs)[0]


def rectifyFrame(frame, camera_matrix, dist_coeffs, new_camera_matrix):
    return cv2.undistort(
        frame,
        cameraMatrix=np.asarray(camera_matrix),
        distCoeffs=np.asarray(dist_coeffs),
        newCameraMatrix=np.asarray(new_camera_matrix),
    )
