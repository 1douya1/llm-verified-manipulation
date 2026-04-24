"""Hand-eye calibration solvers.

Primary v0.1 convention:
    Samples contain ``T_base_ee`` and ``T_camera_board``.

For eye-to-hand, the camera is fixed relative to the robot base and the board is
attached to the end effector. The solver estimates ``T_base_camera``.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

from handeye_pipeline.geometry import (
    compose_transform,
    invert_transform,
    matrix_to_quaternion,
    matrix_to_transform,
    quaternion_to_matrix,
    transform_to_matrix,
)


METHODS = {
    "tsai": "CALIB_HAND_EYE_TSAI",
    "park": "CALIB_HAND_EYE_PARK",
    "horaud": "CALIB_HAND_EYE_HORAUD",
}


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("OpenCV is required for hand-eye solving") from exc
    return cv2


def _method_flag(cv2, method: str) -> int:
    key = method.lower()
    if key not in METHODS:
        raise ValueError(f"Unsupported solver method '{method}'. Use one of: {', '.join(METHODS)}")
    return getattr(cv2, METHODS[key])


def _sample_matrices(samples: list[Mapping]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    robot = []
    board = []
    for sample in samples:
        robot.append(transform_to_matrix(sample["robot"]["transform"]))
        board.append(transform_to_matrix(sample["board"]["transform"]))
    return robot, board


def _rotvec_to_matrix(rotvec: np.ndarray) -> np.ndarray:
    try:
        from scipy.spatial.transform import Rotation

        return Rotation.from_rotvec(rotvec).as_matrix()
    except Exception:  # pragma: no cover
        cv2 = _load_cv2()
        matrix, _ = cv2.Rodrigues(rotvec.reshape(3, 1))
        return matrix


def _matrix_to_rotvec(matrix: np.ndarray) -> np.ndarray:
    try:
        from scipy.spatial.transform import Rotation

        return Rotation.from_matrix(matrix).as_rotvec()
    except Exception:  # pragma: no cover
        cv2 = _load_cv2()
        rotvec, _ = cv2.Rodrigues(matrix)
        return rotvec.reshape(3)


def _params_to_matrix(params: np.ndarray) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, :3] = _rotvec_to_matrix(params[:3])
    matrix[:3, 3] = params[3:6]
    return matrix


def _matrix_to_params(matrix: np.ndarray) -> np.ndarray:
    return np.r_[_matrix_to_rotvec(matrix[:3, :3]), matrix[:3, 3]]


def _eye_to_hand_residual(params: np.ndarray, robot_mats: list[np.ndarray], board_mats: list[np.ndarray]) -> np.ndarray:
    z_base_camera = _params_to_matrix(params[:6])
    x_ee_board = _params_to_matrix(params[6:])
    residuals = []
    for t_base_ee, t_camera_board in zip(robot_mats, board_mats):
        left = t_base_ee @ x_ee_board
        right = z_base_camera @ t_camera_board
        residuals.extend(left[:3, 3] - right[:3, 3])
        residuals.extend(_matrix_to_rotvec(left[:3, :3].T @ right[:3, :3]))
    return np.asarray(residuals)


def _initial_eye_to_hand(robot_mats: list[np.ndarray], board_mats: list[np.ndarray]) -> np.ndarray:
    guesses = [robot @ np.linalg.inv(board) for robot, board in zip(robot_mats, board_mats)]
    z_guess = np.eye(4)
    z_guess[:3, 3] = np.mean([guess[:3, 3] for guess in guesses], axis=0)
    x_guess = np.eye(4)
    return np.r_[_matrix_to_params(z_guess), _matrix_to_params(x_guess)]


def solve_eye_to_hand(samples: list[Mapping], *, method: str = "tsai", min_samples: int = 10) -> dict:
    """Estimate ``T_base_camera`` for a fixed camera and board-on-EE setup."""
    if len(samples) < min_samples:
        raise ValueError(f"Need at least {min_samples} samples; got {len(samples)}")
    try:
        from scipy.optimize import least_squares
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("scipy.optimize.least_squares is required for eye_to_hand v0.1") from exc

    robot_mats, board_mats = _sample_matrices(samples)
    result = least_squares(
        _eye_to_hand_residual,
        _initial_eye_to_hand(robot_mats, board_mats),
        args=(robot_mats, board_mats),
        max_nfev=5000,
    )
    t_base_camera = _params_to_matrix(result.x[:6])
    transform = matrix_to_transform(t_base_camera)
    return {
        "schema_version": "handeye_pipeline.result.v0.1",
        "calibration_mode": "eye_to_hand",
        "solver_method": method.lower(),
        "solver_backend": "scipy_least_squares_ax_zb",
        "used_samples": len(samples),
        "parent_frame": samples[0].get("frames", {}).get("robot_base", "link_base"),
        "child_frame": samples[0].get("frames", {}).get("camera_optical", "camera_color_optical_frame"),
        "transform": transform,
        "rotation_matrix": t_base_camera[:3, :3].tolist(),
        "translation_vector": t_base_camera[:3, 3].tolist(),
        "quaternion_xyzw": transform["rotation"],
        "optimization": {
            "success": bool(result.success),
            "cost": float(result.cost),
            "message": result.message,
        },
    }


def solve_eye_in_hand(samples: list[Mapping], *, method: str = "tsai", min_samples: int = 10) -> dict:
    """Estimate ``T_ee_camera`` using OpenCV ``calibrateHandEye``."""
    if len(samples) < min_samples:
        raise ValueError(f"Need at least {min_samples} samples; got {len(samples)}")
    cv2 = _load_cv2()
    robot_mats, board_mats = _sample_matrices(samples)
    r_gripper2base = [matrix[:3, :3] for matrix in robot_mats]
    t_gripper2base = [matrix[:3, 3] for matrix in robot_mats]
    r_target2cam = [matrix[:3, :3] for matrix in board_mats]
    t_target2cam = [matrix[:3, 3] for matrix in board_mats]
    rotation, translation = cv2.calibrateHandEye(
        r_gripper2base,
        t_gripper2base,
        r_target2cam,
        t_target2cam,
        method=_method_flag(cv2, method),
    )
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = np.asarray(translation).reshape(3)
    transform = matrix_to_transform(matrix)
    return {
        "schema_version": "handeye_pipeline.result.v0.1",
        "calibration_mode": "eye_in_hand",
        "solver_method": method.lower(),
        "solver_backend": "opencv_calibrateHandEye",
        "used_samples": len(samples),
        "parent_frame": samples[0].get("frames", {}).get("robot_ee", "link_eef"),
        "child_frame": samples[0].get("frames", {}).get("camera_optical", "camera_color_optical_frame"),
        "transform": transform,
        "rotation_matrix": matrix[:3, :3].tolist(),
        "translation_vector": matrix[:3, 3].tolist(),
        "quaternion_xyzw": matrix_to_quaternion(matrix[:3, :3]).tolist(),
    }


def solve_handeye(samples: list[Mapping], config_or_mode, *, method: str | None = None, min_samples: int | None = None) -> dict:
    """Dispatch to the configured hand-eye mode."""
    if hasattr(config_or_mode, "calibration"):
        mode = config_or_mode.calibration.mode
        method = method or config_or_mode.calibration.solver
        min_samples = min_samples or config_or_mode.calibration.min_samples
    else:
        mode = str(config_or_mode)
        method = method or "tsai"
        min_samples = min_samples or 10

    if mode == "eye_to_hand":
        return solve_eye_to_hand(samples, method=method, min_samples=min_samples)
    if mode == "eye_in_hand":
        return solve_eye_in_hand(samples, method=method, min_samples=min_samples)
    raise ValueError(f"Unsupported calibration mode: {mode}")


def estimate_eye_to_hand_board_mount(samples: list[Mapping], result: Mapping) -> list[dict]:
    """Return per-sample ``T_ee_board`` estimates from solved ``T_base_camera``."""
    t_base_camera = transform_to_matrix(result["transform"])
    estimates = []
    for sample in samples:
        t_base_ee = transform_to_matrix(sample["robot"]["transform"])
        t_camera_board = transform_to_matrix(sample["board"]["transform"])
        estimates.append(matrix_to_transform(np.linalg.inv(t_base_ee) @ t_base_camera @ t_camera_board))
    return estimates
