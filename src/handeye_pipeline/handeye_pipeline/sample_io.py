"""Stable YAML/JSON sample IO for hand-eye calibration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import yaml


SCHEMA_VERSION = "handeye_pipeline.sample.v0.1"


def make_sample(
    robot_transform: Mapping[str, Any],
    board_transform: Mapping[str, Any],
    frame_names: Mapping[str, str],
    *,
    sample_id: str | None = None,
    timestamp: str | None = None,
    detection_quality: Mapping[str, Any] | None = None,
) -> dict:
    """Create a sample dict.

    ``robot_transform`` is usually ``T_base_ee``. ``board_transform`` is usually
    ``T_camera_board`` from ChArUco detection.
    """
    return {
        "id": sample_id or f"sample_{uuid4().hex[:8]}",
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "frames": dict(frame_names),
        "robot": {"transform": dict(robot_transform)},
        "board": {"transform": dict(board_transform)},
        "detection_quality": dict(detection_quality or {}),
    }


def _read(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "samples": []}
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if "samples" not in data and isinstance(data, list):
        data = {"schema_version": SCHEMA_VERSION, "samples": data}
    return data


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(dict(data), stream, sort_keys=False)


def save_sample(path: str | Path, sample: Mapping[str, Any]) -> None:
    """Write a sample file containing one sample."""
    _write(Path(path), {"schema_version": SCHEMA_VERSION, "samples": [dict(sample)]})


def append_sample(path: str | Path, sample: Mapping[str, Any]) -> None:
    """Append one sample to a YAML sample file."""
    sample_path = Path(path)
    data = _read(sample_path)
    samples = list(data.get("samples", []))
    samples.append(dict(sample))
    data["schema_version"] = data.get("schema_version", SCHEMA_VERSION)
    data["samples"] = samples
    _write(sample_path, data)


def load_samples(path: str | Path) -> list[dict]:
    """Load samples from YAML or JSON-like YAML."""
    data = _read(Path(path))
    validate_sample_file(data)
    return list(data.get("samples", []))


def _require_transform(sample: Mapping[str, Any], section: str) -> None:
    transform = sample.get(section, {}).get("transform")
    if not isinstance(transform, Mapping):
        raise ValueError(f"Sample {sample.get('id', '<unknown>')} missing {section}.transform")
    for key, size in (("translation", 3), ("rotation", 4)):
        values = transform.get(key)
        if not isinstance(values, (list, tuple)) or len(values) != size:
            raise ValueError(
                f"Sample {sample.get('id', '<unknown>')} {section}.transform.{key} "
                f"must have {size} values"
            )


def validate_sample_file(data_or_path: str | Path | Mapping[str, Any]) -> bool:
    """Validate the v0.1 sample schema.

    Raises ``ValueError`` with a human-readable message when invalid.
    """
    if isinstance(data_or_path, (str, Path)):
        data = _read(Path(data_or_path))
    else:
        data = data_or_path

    samples = data.get("samples")
    if not isinstance(samples, list):
        raise ValueError("Sample file must contain a top-level 'samples' list")

    for sample in samples:
        if "id" not in sample:
            raise ValueError("Each sample must contain an id")
        if "timestamp" not in sample:
            raise ValueError(f"Sample {sample['id']} missing timestamp")
        frames = sample.get("frames", {})
        if not isinstance(frames, Mapping):
            raise ValueError(f"Sample {sample['id']} frames must be a mapping")
        _require_transform(sample, "robot")
        _require_transform(sample, "board")
    return True
