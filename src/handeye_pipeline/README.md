# handeye_pipeline v0.1

Reusable hand-eye calibration pipeline for lab use. The package decouples ChArUco detection, sample IO, hand-eye solving, validation, and TF export from the main pouring/manipulation pipeline.

## Hardware Assumptions

- Robot: UFactory xArm / UF850
- Camera: Intel RealSense D435i
- ROS: ROS2 Humble
- Board: ChArUco board
- Default mode: `eye_to_hand`
- Default frames:
  - robot base: `link_base`
  - robot end effector: `link_eef`
  - camera optical: `camera_color_optical_frame`

## Install

From the ROS2 workspace root:

```bash
colcon build --packages-select handeye_pipeline
source install/setup.bash
```

Python-only CLI checks can also run from source:

```bash
PYTHONPATH=src/handeye_pipeline python3 -m handeye_pipeline.cli --help
```

## Quick Start

```bash
handeye-init-config --output config/uf850_realsense_eye_to_hand.yaml
ros2 launch handeye_pipeline collect_samples.launch.py config:=config/uf850_realsense_eye_to_hand.yaml
ros2 service call /save_sample std_srvs/srv/SetBool "{data: true}"
handeye-validate --config config/uf850_realsense_eye_to_hand.yaml
handeye-solve --config config/uf850_realsense_eye_to_hand.yaml
handeye-export-tf --config config/uf850_realsense_eye_to_hand.yaml
```

## Sample Collection Workflow

1. Start the RealSense camera and robot TF publishers.
2. Launch `collect_samples.launch.py`.
3. Move the robot to diverse poses with the ChArUco board visible.
4. Trigger one sample per stable pose:

```bash
ros2 service call /save_sample std_srvs/srv/SetBool "{data: true}"
```

The node stores `T_base_ee` from TF and `T_camera_board` from ChArUco detection in the configured sample file.

## Solve And Validate

```bash
handeye-validate --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
handeye-solve --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
```

The default `eye_to_hand` result is `T_base_camera`, exported as translation, quaternion, rotation matrix, and a ready-to-run static TF command.

## Publish TF

```bash
ros2 launch handeye_pipeline publish_calibration_tf.launch.py result_file:=data/handeye_result.yaml
```

Equivalent direct command format:

```bash
ros2 run tf2_ros static_transform_publisher x y z qx qy qz qw link_base camera_color_optical_frame
```

## Sample YAML Schema

```yaml
schema_version: handeye_pipeline.sample.v0.1
samples:
  - id: sample_0001
    timestamp: "2026-01-01T00:00:00Z"
    frames:
      robot_base: link_base
      robot_ee: link_eef
      camera_optical: camera_color_optical_frame
      calibration_board: charuco_board
    robot:
      transform:
        translation: [x, y, z]
        rotation: [qx, qy, qz, qw]
    board:
      transform:
        translation: [x, y, z]
        rotation: [qx, qy, qz, qw]
    detection_quality:
      num_markers: 12
      num_corners: 20
      reprojection_error: 0.8
```

## Known Limitations

- v0.1 prioritizes eye-to-hand with a fixed camera and board mounted on the end effector.
- The collection node uses a simple service trigger and does not synchronize image/TF with advanced filters.
- Validation metrics are pragmatic warnings, not a full uncertainty model.
- Real calibration quality still depends on viewpoint diversity, board rigidity, camera intrinsics, and clean TF.
