"""Basic hand-eye calibration quality checks."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from handeye_pipeline.geometry import transform_to_matrix
from handeye_pipeline.solver import estimate_eye_to_hand_board_mount


def _rotation_angle(matrix: np.ndarray) -> float:
    value = (np.trace(matrix) - 1.0) / 2.0
    return float(np.arccos(np.clip(value, -1.0, 1.0)))


def validate_samples(samples: list[Mapping], *, min_samples: int = 10, result: Mapping | None = None) -> dict:
    """Return simple metrics and warnings for lab users."""
    warnings = []
    if len(samples) < min_samples:
        warnings.append(f"too few samples: got {len(samples)}, recommended at least {min_samples}")

    missing_frames = [sample.get("id", "<unknown>") for sample in samples if not sample.get("frames")]
    if missing_frames:
        warnings.append(f"missing frame names in {len(missing_frames)} samples")

    robot_translations = []
    reprojection_errors = []
    for sample in samples:
        robot_translations.append(transform_to_matrix(sample["robot"]["transform"])[:3, 3])
        error = sample.get("detection_quality", {}).get("reprojection_error")
        if error is not None:
            reprojection_errors.append(float(error))

    if len(robot_translations) > 1:
        positions = np.vstack(robot_translations)
        spread = np.ptp(positions, axis=0)
        if float(np.linalg.norm(spread)) < 0.05:
            warnings.append("low viewpoint diversity: robot translation spread is under 5 cm")
        uniqueish = np.unique(np.round(positions, 3), axis=0)
        if len(uniqueish) < max(2, len(samples) // 3):
            warnings.append("repeated robot poses: many samples have nearly identical EE positions")

    if reprojection_errors and float(np.mean(reprojection_errors)) > 2.0:
        warnings.append("high reprojection error: mean error is above 2 px")

    metrics = {
        "sample_count": len(samples),
        "warnings": warnings,
        "detection_quality": {
            "samples_with_reprojection_error": len(reprojection_errors),
            "mean_reprojection_error": float(np.mean(reprojection_errors)) if reprojection_errors else None,
            "max_reprojection_error": float(np.max(reprojection_errors)) if reprojection_errors else None,
        },
    }

    if result and result.get("calibration_mode") == "eye_to_hand" and len(samples) >= 2:
        estimates = [transform_to_matrix(t) for t in estimate_eye_to_hand_board_mount(samples, result)]
        reference = estimates[0]
        translation_residuals = []
        rotation_residuals = []
        for estimate in estimates[1:]:
            delta = np.linalg.inv(reference) @ estimate
            translation_residuals.append(float(np.linalg.norm(delta[:3, 3])))
            rotation_residuals.append(_rotation_angle(delta[:3, :3]))
        metrics["transform_consistency"] = {
            "mean_translation_residual_m": float(np.mean(translation_residuals)) if translation_residuals else 0.0,
            "max_translation_residual_m": float(np.max(translation_residuals)) if translation_residuals else 0.0,
            "mean_rotation_residual_rad": float(np.mean(rotation_residuals)) if rotation_residuals else 0.0,
            "max_rotation_residual_rad": float(np.max(rotation_residuals)) if rotation_residuals else 0.0,
        }

    return metrics
