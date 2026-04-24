"""Configuration loading and validation for handeye_pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class CalibrationConfig:
    mode: str
    solver: str = "tsai"
    min_samples: int = 15


@dataclass(frozen=True)
class RobotConfig:
    base_frame: str
    ee_frame: str


@dataclass(frozen=True)
class CameraConfig:
    optical_frame: str
    rgb_topic: str = "/camera/color/image_raw"
    camera_info_topic: str = "/camera/color/camera_info"


@dataclass(frozen=True)
class BoardConfig:
    type: str
    squares_x: int
    squares_y: int
    square_length: float
    marker_length: float
    dictionary: str
    frame: str = "charuco_board"


@dataclass(frozen=True)
class OutputConfig:
    sample_file: str
    result_file: str


@dataclass(frozen=True)
class HandeyeConfig:
    calibration: CalibrationConfig
    robot: RobotConfig
    camera: CameraConfig
    board: BoardConfig
    output: OutputConfig
    source_path: Path | None = None


REQUIRED_FIELDS = (
    "calibration.mode",
    "robot.base_frame",
    "robot.ee_frame",
    "camera.optical_frame",
    "board.type",
    "board.square_length",
    "board.marker_length",
    "board.squares_x",
    "board.squares_y",
    "board.dictionary",
    "output.sample_file",
    "output.result_file",
)


def _get_nested(data: Mapping[str, Any], dotted_key: str) -> Any:
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"Missing required config field: {dotted_key}")
        current = current[part]
    return current


def validate_config_dict(data: Mapping[str, Any]) -> None:
    """Validate required fields and common hand-eye values."""
    for field in REQUIRED_FIELDS:
        _get_nested(data, field)

    mode = str(_get_nested(data, "calibration.mode"))
    if mode not in {"eye_to_hand", "eye_in_hand"}:
        raise ValueError("calibration.mode must be 'eye_to_hand' or 'eye_in_hand'")

    if str(_get_nested(data, "board.type")).lower() != "charuco":
        raise ValueError("Only board.type='charuco' is supported in v0.1")

    for key in ("board.square_length", "board.marker_length"):
        if float(_get_nested(data, key)) <= 0:
            raise ValueError(f"{key} must be positive")

    for key in ("board.squares_x", "board.squares_y"):
        if int(_get_nested(data, key)) < 2:
            raise ValueError(f"{key} must be >= 2")


def load_config(path: str | Path) -> HandeyeConfig:
    """Load and validate a YAML config file."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    validate_config_dict(data)

    calibration_data = data["calibration"]
    camera_data = data["camera"]
    board_data = data["board"]

    return HandeyeConfig(
        calibration=CalibrationConfig(
            mode=str(calibration_data["mode"]),
            solver=str(calibration_data.get("solver", "tsai")).lower(),
            min_samples=int(calibration_data.get("min_samples", 15)),
        ),
        robot=RobotConfig(
            base_frame=str(data["robot"]["base_frame"]),
            ee_frame=str(data["robot"]["ee_frame"]),
        ),
        camera=CameraConfig(
            optical_frame=str(camera_data["optical_frame"]),
            rgb_topic=str(camera_data.get("rgb_topic", "/camera/color/image_raw")),
            camera_info_topic=str(camera_data.get("camera_info_topic", "/camera/color/camera_info")),
        ),
        board=BoardConfig(
            type=str(board_data["type"]),
            squares_x=int(board_data["squares_x"]),
            squares_y=int(board_data["squares_y"]),
            square_length=float(board_data["square_length"]),
            marker_length=float(board_data["marker_length"]),
            dictionary=str(board_data["dictionary"]),
            frame=str(board_data.get("frame", "charuco_board")),
        ),
        output=OutputConfig(
            sample_file=str(data["output"]["sample_file"]),
            result_file=str(data["output"]["result_file"]),
        ),
        source_path=config_path,
    )
