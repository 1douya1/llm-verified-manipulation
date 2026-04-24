"""OpenCV ChArUco board detection with explicit transform output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from handeye_pipeline.config import BoardConfig
from handeye_pipeline.geometry import matrix_to_quaternion


@dataclass
class DetectionResult:
    detected: bool
    transform_camera_board: dict | None = None
    num_markers: int = 0
    num_corners: int = 0
    reprojection_error: float | None = None
    quality: dict[str, Any] = field(default_factory=dict)
    message: str = ""


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on host packages
        raise RuntimeError("OpenCV is required for ChArUco detection") from exc
    if not hasattr(cv2, "aruco"):
        raise RuntimeError(
            "cv2.aruco is unavailable. Install an OpenCV build with contrib modules "
            "(for example python3-opencv on ROS2 Humble systems)."
        )
    return cv2


def _dictionary(cv2, name: str):
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"Unknown ArUco dictionary '{name}'")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def create_charuco_board(board_config: BoardConfig):
    """Create a ChArUco board object compatible with OpenCV 4.x variants."""
    cv2 = _load_cv2()
    aruco_dict = _dictionary(cv2, board_config.dictionary)
    size = (board_config.squares_x, board_config.squares_y)
    try:
        board = cv2.aruco.CharucoBoard(size, board_config.square_length, board_config.marker_length, aruco_dict)
    except TypeError:
        board = cv2.aruco.CharucoBoard_create(
            board_config.squares_x,
            board_config.squares_y,
            board_config.square_length,
            board_config.marker_length,
            aruco_dict,
        )
    return board, aruco_dict


class CharucoDetector:
    """Detect ``T_camera_board`` from RGB/BGR images and camera intrinsics."""

    def __init__(self, board_config: BoardConfig):
        self.cv2 = _load_cv2()
        self.board_config = board_config
        self.board, self.aruco_dict = create_charuco_board(board_config)
        self.aruco_params = self.cv2.aruco.DetectorParameters()
        self.detector = (
            self.cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
            if hasattr(self.cv2.aruco, "ArucoDetector")
            else None
        )
        self.charuco_detector = None
        if hasattr(self.cv2.aruco, "CharucoDetector"):
            try:
                self.charuco_detector = self.cv2.aruco.CharucoDetector(
                    self.board,
                    self.cv2.aruco.CharucoParameters(),
                    self.aruco_params,
                )
            except Exception:
                self.charuco_detector = None

    def detect(
        self,
        image: np.ndarray,
        camera_intrinsics: Mapping[str, Any],
        *,
        min_corners: int = 8,
    ) -> DetectionResult:
        """Detect a board pose.

        Returns ``T_camera_board``. OpenCV's PnP convention maps board/object
        coordinates into camera optical coordinates.
        """
        camera_matrix = np.asarray(camera_intrinsics["camera_matrix"], dtype=float).reshape(3, 3)
        dist_coeffs = np.asarray(camera_intrinsics.get("distortion_coefficients", [0, 0, 0, 0, 0]), dtype=float)
        gray = self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

        marker_corners, marker_ids = self._detect_markers(gray)
        num_markers = 0 if marker_ids is None else len(marker_ids)
        if marker_ids is None or num_markers == 0:
            return DetectionResult(False, num_markers=0, message="No ArUco markers detected")

        charuco_corners, charuco_ids = self._interpolate(gray, marker_corners, marker_ids)
        num_corners = 0 if charuco_corners is None else len(charuco_corners)
        if charuco_ids is None or num_corners < min_corners:
            return DetectionResult(
                False,
                num_markers=num_markers,
                num_corners=num_corners,
                message=f"Only {num_corners} ChArUco corners detected; need at least {min_corners}",
            )

        success, rvec, tvec = self._estimate_pose(charuco_corners, charuco_ids, camera_matrix, dist_coeffs)
        if not success:
            return DetectionResult(
                False,
                num_markers=num_markers,
                num_corners=num_corners,
                message="ChArUco pose estimation failed",
            )

        rotation_matrix, _ = self.cv2.Rodrigues(rvec)
        transform = {
            "translation": np.asarray(tvec, dtype=float).reshape(3).tolist(),
            "rotation": matrix_to_quaternion(rotation_matrix).tolist(),
        }
        reprojection_error = self._reprojection_error(
            charuco_corners,
            charuco_ids,
            rvec,
            tvec,
            camera_matrix,
            dist_coeffs,
        )
        return DetectionResult(
            True,
            transform_camera_board=transform,
            num_markers=num_markers,
            num_corners=num_corners,
            reprojection_error=reprojection_error,
            quality={
                "num_markers": num_markers,
                "num_corners": num_corners,
                "reprojection_error": reprojection_error,
            },
            message="Detected",
        )

    def _detect_markers(self, gray: np.ndarray):
        if self.detector is not None:
            corners, ids, _ = self.detector.detectMarkers(gray)
            return corners, ids
        corners, ids, _ = self.cv2.aruco.detectMarkers(gray, self.aruco_dict, parameters=self.aruco_params)
        return corners, ids

    def _interpolate(self, gray: np.ndarray, marker_corners, marker_ids):
        if self.charuco_detector is not None:
            try:
                corners, ids, _, _ = self.charuco_detector.detectBoard(gray)
                return corners, ids
            except Exception:
                pass
        try:
            _, corners, ids = self.cv2.aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                self.board,
            )
        except TypeError:
            _, corners, ids = self.cv2.aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                self.board,
                cameraMatrix=None,
                distCoeffs=None,
            )
        return corners, ids

    def _estimate_pose(self, corners, ids, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        if hasattr(self.cv2.aruco, "estimatePoseCharucoBoard"):
            return self.cv2.aruco.estimatePoseCharucoBoard(
                corners,
                ids,
                self.board,
                camera_matrix,
                dist_coeffs,
                None,
                None,
            )
        object_points = self._charuco_object_points(ids)
        success, rvec, tvec = self.cv2.solvePnP(object_points, corners, camera_matrix, dist_coeffs)
        return success, rvec, tvec

    def _charuco_object_points(self, ids):
        if hasattr(self.board, "getChessboardCorners"):
            points = self.board.getChessboardCorners()
        else:
            points = self.board.chessboardCorners
        return np.asarray(points, dtype=np.float32)[ids.flatten()]

    def _reprojection_error(self, corners, ids, rvec, tvec, camera_matrix, dist_coeffs) -> float | None:
        try:
            object_points = self._charuco_object_points(ids)
            projected, _ = self.cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist_coeffs)
            observed = np.asarray(corners, dtype=float).reshape(-1, 2)
            projected = projected.reshape(-1, 2)
            return float(np.mean(np.linalg.norm(observed - projected, axis=1)))
        except Exception:
            return None
