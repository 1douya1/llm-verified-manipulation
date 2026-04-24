"""Export solved transforms to YAML and ROS2 static TF commands."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml


def static_transform_command(result: Mapping, parent_frame: str | None = None, child_frame: str | None = None) -> str:
    """Build a ROS2 ``static_transform_publisher`` command."""
    transform = result["transform"]
    translation = transform["translation"]
    rotation = transform["rotation"]
    parent = parent_frame or result.get("parent_frame") or result.get("frames", {}).get("parent")
    child = child_frame or result.get("child_frame") or result.get("frames", {}).get("child")
    if not parent or not child:
        raise ValueError("parent_frame and child_frame are required for TF export")
    values = [*translation, *rotation, parent, child]
    return "ros2 run tf2_ros static_transform_publisher " + " ".join(str(v) for v in values)


def save_result_yaml(path: str | Path, result: Mapping) -> None:
    result_path = Path(path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(dict(result), stream, sort_keys=False)


def load_result_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def export_launch_config(result: Mapping) -> dict:
    """Return launch-friendly static transform fields."""
    transform = result["transform"]
    return {
        "parent_frame": result.get("parent_frame") or result.get("frames", {}).get("parent"),
        "child_frame": result.get("child_frame") or result.get("frames", {}).get("child"),
        "translation": transform["translation"],
        "rotation_xyzw": transform["rotation"],
    }
