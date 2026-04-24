"""Command-line entry points for handeye_pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

import yaml

from handeye_pipeline.config import load_config
from handeye_pipeline.sample_io import load_samples, validate_sample_file
from handeye_pipeline.solver import solve_handeye
from handeye_pipeline.tf_export import load_result_yaml, save_result_yaml, static_transform_command
from handeye_pipeline.validation import validate_samples


def _default_config_path() -> Path:
    source_tree = Path(__file__).resolve().parents[1] / "config" / "uf850_realsense_eye_to_hand.yaml"
    if source_tree.exists():
        return source_tree
    installed_share = (
        Path(__file__).resolve().parents[4]
        / "share"
        / "handeye_pipeline"
        / "config"
        / "uf850_realsense_eye_to_hand.yaml"
    )
    if installed_share.exists():
        return installed_share
    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("handeye_pipeline")) / "config" / "uf850_realsense_eye_to_hand.yaml"
    except Exception as exc:
        raise FileNotFoundError("Cannot locate default handeye_pipeline config") from exc


def _config_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", help="Path to handeye YAML config")
    return parser


def _resolve_config(config_arg: str | None) -> str:
    return config_arg or str(_default_config_path())


def init_config_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a local hand-eye config from the v0.1 template")
    parser.add_argument("--output", default="config/uf850_realsense_eye_to_hand.yaml")
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_default_config_path(), output)
    print(f"Wrote config template: {output}")
    return 0


def collect_main(argv: list[str] | None = None) -> int:
    parser = _config_parser("Show sample collection settings for the ROS2 collect node")
    args = parser.parse_args(argv)
    config_path = _resolve_config(args.config)
    config = load_config(config_path)
    print("Use the ROS2 collection node for live samples:")
    print(
        "  ros2 launch handeye_pipeline collect_samples.launch.py "
        f"config:={Path(config_path)}"
    )
    print(f"RGB topic: {config.camera.rgb_topic}")
    print(f"Camera info topic: {config.camera.camera_info_topic}")
    print(f"Robot TF: {config.robot.base_frame} -> {config.robot.ee_frame}")
    print(f"Samples will be appended to: {config.output.sample_file}")
    return 0


def solve_main(argv: list[str] | None = None) -> int:
    parser = _config_parser("Solve hand-eye calibration from a sample YAML file")
    parser.add_argument("--samples", help="Override sample file from config")
    parser.add_argument("--output", help="Override result file from config")
    parser.add_argument("--min-samples", type=int, help="Override config calibration.min_samples")
    parser.add_argument("--method", choices=["tsai", "park", "horaud"], help="Override solver method")
    args = parser.parse_args(argv)
    config = load_config(_resolve_config(args.config))
    sample_file = Path(args.samples or config.output.sample_file)
    result_file = Path(args.output or config.output.result_file)
    samples = load_samples(sample_file)
    result = solve_handeye(
        samples,
        config,
        method=args.method,
        min_samples=args.min_samples,
    )
    save_result_yaml(result_file, result)
    print(f"Solved {result['calibration_mode']} with {result['used_samples']} samples")
    print(f"Wrote result: {result_file}")
    print(static_transform_command(result))
    return 0


def validate_main(argv: list[str] | None = None) -> int:
    parser = _config_parser("Validate hand-eye sample quality")
    parser.add_argument("--samples", help="Override sample file from config")
    parser.add_argument("--result", help="Optional solved result YAML")
    args = parser.parse_args(argv)
    config = load_config(_resolve_config(args.config))
    sample_file = Path(args.samples or config.output.sample_file)
    validate_sample_file(sample_file)
    samples = load_samples(sample_file)
    result = load_result_yaml(args.result) if args.result else None
    metrics = validate_samples(samples, min_samples=config.calibration.min_samples, result=result)
    print(yaml.safe_dump(metrics, sort_keys=False))
    return 0


def export_tf_main(argv: list[str] | None = None) -> int:
    parser = _config_parser("Export a solved calibration as a ROS2 static TF command")
    parser.add_argument("--result", help="Override result file from config")
    parser.add_argument("--parent-frame")
    parser.add_argument("--child-frame")
    args = parser.parse_args(argv)
    config = load_config(_resolve_config(args.config))
    result_file = Path(args.result or config.output.result_file)
    result = load_result_yaml(result_file)
    print(static_transform_command(result, args.parent_frame, args.child_frame))
    return 0


def _run(main_func, argv: list[str] | None = None) -> None:
    try:
        raise SystemExit(main_func(argv))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    _run(solve_main)
