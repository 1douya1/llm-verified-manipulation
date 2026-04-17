# scripts/diagnostics

Standalone Python utilities to verify that the real-robot stack is wired
correctly **before** you trust it with motion. They are intentionally
ROS-light: each script does one focused check, prints a clear
`[OK]/[WARN]/[ERR]` result, and exits.

> Always run these AFTER `source install/setup.bash` in the same shell.

## Quick reference

| Script | What it checks | When to run |
|---|---|---|
| `system_diagnosis.py` | Wraps the five checks below into one PASS/FAIL summary. | First-time setup, every fresh boot. |
| `diagnose_robot_env.py` | `mtc_action_library` import works; `/move_group` is up; key parameters and topics exist. | Right after launching `uf850_moveit_*.launch.py`. |
| `check_joint_limits.py` | `xarm_moveit_config/config/uf850/joint_limits.yaml` defines `has_acceleration_limits: true`. Walks up from the script to find it inside the `xarm_ros2` submodule. | When you see the MoveIt warning *"Joint acceleration limits are not defined"*. |
| `handeye_transform_viewer.py` | Polls `/tf` for `link_base -> camera_color_optical_frame`, `link_base -> link_eef`, and `link_eef -> camera_color_optical_frame`. | After launching either `easy_handeye2` publisher or your own `static_transform_publisher` from `configs/handeye_*.yaml`. |

## Typical sequence

```bash
source install/setup.bash

ros2 launch xarm_moveit_config uf850_moveit_realmove.launch.py robot_ip:=<IP> &
ros2 launch realsense2_camera rs_launch.py &
ros2 launch easy_handeye2 publish.launch.py name:=uf850_d435i_eih &

python3 scripts/diagnostics/system_diagnosis.py
```

If `system_diagnosis.py` returns 0, you're cleared to proceed to
`docs/REAL_ROBOT_QUICK_START.md` step 8 (perception bringup).

## Troubleshooting (common false alarms)

- **`move_group` missing**: plug-in USB / camera alone does **not** start
  MoveIt. Launch `uf850_moveit_fake.launch.py` or `uf850_moveit_realmove.launch.py`
  first, then re-run diagnostics.
- **`link_base` does not exist in /tf**: the robot model + state publisher
  are not running yet — same fix as above (MoveIt / `pour_demo.launch.py`).
- **Camera step fails while the device is plugged in**: the RealSense ROS
  driver must be running. Typical color topics are `/camera/color/image_raw`
  **or** `/camera/camera/color/image_raw` (namespace). Use
  `ros2 topic list | grep image_raw` to confirm, then match your launch file.

## What is NOT here

- No motion. None of these scripts command the arm.
- No calibration. See `scripts/real_robot/` and
  `docs/CALIBRATION_PIPELINE.md`.
- No GUI. Use `rviz2` or `tf2_tools view_frames` for visual debugging.
