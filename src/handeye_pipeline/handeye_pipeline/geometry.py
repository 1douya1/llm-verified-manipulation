"""Small transform helpers with no ROS dependency.

Transform convention used by this package:
    ``T_parent_child`` maps a point expressed in ``child`` coordinates into
    ``parent`` coordinates:

    ``p_parent = R_parent_child @ p_child + t_parent_child``.

Dictionary transforms use ``translation: [x, y, z]`` and quaternion
``rotation: [x, y, z, w]``.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

try:
    from scipy.spatial.transform import Rotation
except Exception:  # pragma: no cover - exercised only on minimal systems
    Rotation = None


def _as_float_array(values: Sequence[float], shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape:
        raise ValueError(f"Expected shape {shape}, got {array.shape}")
    return array


def quaternion_to_matrix(quaternion_xyzw: Sequence[float]) -> np.ndarray:
    """Return a 3x3 rotation matrix from a quaternion in ``[x, y, z, w]`` order."""
    q = _as_float_array(quaternion_xyzw, (4,))
    norm = np.linalg.norm(q)
    if norm == 0:
        raise ValueError("Quaternion must not be zero length")
    q = q / norm
    if Rotation is not None:
        return Rotation.from_quat(q).as_matrix()

    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def matrix_to_quaternion(rotation_matrix: Sequence[Sequence[float]]) -> np.ndarray:
    """Return quaternion ``[x, y, z, w]`` from a 3x3 rotation matrix."""
    matrix = _as_float_array(rotation_matrix, (3, 3))
    if Rotation is not None:
        return Rotation.from_matrix(matrix).as_quat()

    trace = np.trace(matrix)
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (matrix[2, 1] - matrix[1, 2]) * s
        y = (matrix[0, 2] - matrix[2, 0]) * s
        z = (matrix[1, 0] - matrix[0, 1]) * s
    else:
        i = int(np.argmax(np.diag(matrix)))
        if i == 0:
            s = 2.0 * np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2])
            w = (matrix[2, 1] - matrix[1, 2]) / s
            x = 0.25 * s
            y = (matrix[0, 1] + matrix[1, 0]) / s
            z = (matrix[0, 2] + matrix[2, 0]) / s
        elif i == 1:
            s = 2.0 * np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2])
            w = (matrix[0, 2] - matrix[2, 0]) / s
            x = (matrix[0, 1] + matrix[1, 0]) / s
            y = 0.25 * s
            z = (matrix[1, 2] + matrix[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1])
            w = (matrix[1, 0] - matrix[0, 1]) / s
            x = (matrix[0, 2] + matrix[2, 0]) / s
            y = (matrix[1, 2] + matrix[2, 1]) / s
            z = 0.25 * s
    q = np.array([x, y, z, w], dtype=float)
    return q / np.linalg.norm(q)


def transform_to_matrix(transform: Mapping[str, Sequence[float]]) -> np.ndarray:
    """Convert a transform dict into a homogeneous 4x4 matrix."""
    translation = _as_float_array(transform["translation"], (3,))
    rotation = quaternion_to_matrix(transform["rotation"])
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


def matrix_to_transform(matrix: Sequence[Sequence[float]]) -> dict:
    """Convert a homogeneous 4x4 matrix into a transform dict."""
    matrix = _as_float_array(matrix, (4, 4))
    return {
        "translation": matrix[:3, 3].astype(float).tolist(),
        "rotation": matrix_to_quaternion(matrix[:3, :3]).astype(float).tolist(),
    }


def invert_transform(transform: Mapping[str, Sequence[float]]) -> dict:
    """Invert ``T_parent_child`` and return ``T_child_parent``."""
    matrix = transform_to_matrix(transform)
    inverse = np.eye(4, dtype=float)
    inverse[:3, :3] = matrix[:3, :3].T
    inverse[:3, 3] = -inverse[:3, :3] @ matrix[:3, 3]
    return matrix_to_transform(inverse)


def compose_transform(
    first: Mapping[str, Sequence[float]],
    second: Mapping[str, Sequence[float]],
) -> dict:
    """Compose transforms.

    If ``first`` is ``T_a_b`` and ``second`` is ``T_b_c``, the returned
    transform is ``T_a_c``.
    """
    return matrix_to_transform(transform_to_matrix(first) @ transform_to_matrix(second))


def make_transform(translation: Sequence[float], rotation_xyzw: Sequence[float]) -> dict:
    """Create a normalized transform dict."""
    return matrix_to_transform(transform_to_matrix({"translation": translation, "rotation": rotation_xyzw}))
