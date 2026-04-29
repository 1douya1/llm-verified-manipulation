# Real-Robot Parity Checklist

Use this checklist before treating `RSS_Workshop` as the primary real-robot
workspace and freezing `uf_custom_ws` as read-only reference material.

## Submodules and Build

- [ ] `git submodule status --recursive` shows initialized entries without a
  leading `-` for `src/xarm_ros2`, `src/xarm_ros2/xarm_sdk/cxx`, and
  `src/easy_handeye2`.
- [ ] UF850 assets exist in `src/xarm_ros2`:
  `uf850_moveit_realmove.launch.py`, `uf850_moveit_fake.launch.py`,
  `uf850_driver.launch.py`, and `config/uf850/joint_limits.yaml`.
- [ ] `colcon build --symlink-install --packages-up-to mtc_tutorial` passes
  after sourcing ROS 2 Humble.
- [ ] `ros2 pkg list` includes `xarm_moveit_config`, `xarm_api`,
  `easy_handeye2`, and `mtc_tutorial`.

## Launch and Motion

- [ ] Plan-only stack starts with `./scripts/run_demo.sh --plan-only`.
- [ ] Fake UF850 launch resolves:
  `ros2 launch xarm_moveit_config uf850_moveit_fake.launch.py`.
- [ ] Real UF850 stack resolves:
  `ros2 launch mtc_tutorial pour_demo.launch.py robot_ip:=<UF850_IP>`.
- [ ] `ros2 node list` shows `move_group` and the MTC modular task server.
- [ ] `ros2 run mtc_tutorial test_modular_tasks --plan-only` plans without
  sending hardware motion.

## Perception and TF

- [ ] RealSense starts with aligned depth:
  `ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true enable_sync:=true`.
- [ ] `ros2 topic hz /camera/camera/color/image_raw` is stable near the
  expected camera frame rate.
- [ ] Hand-eye replay starts with `charuco_handeye_publish.launch.py`.
- [ ] `ros2 run tf2_ros tf2_echo link_base camera_color_optical_frame` is
  stable and physically plausible.
- [ ] `ros2 launch mtc_tutorial detection_only.launch.py` starts detection,
  markers, and the planning-scene bridge exactly once.
- [ ] RViz shows detected cups/bowls as collision objects on the table, not
  at the camera origin or floating in space.

## Agent Execution

- [ ] `agent/action_tools.py` defaults to `plan_only=False`, so real-robot
  actions plan and then execute directly.
- [ ] Explicit `plan_only=True` reaches `lib.execute(...)` for pick, place,
  move-and-pour, return-home, and the full sequence.
- [ ] `python3 agent_app.py --dry-run` forces planning-only behavior.
- [ ] Successful real execution updates the scene manager holding/last-action
  state; planning-only checks do not claim the robot is holding an object.
- [ ] E-stop is reachable before every real motion run.

## Migration Audit

| Capability from `uf_custom_ws` | RSS status | Notes |
| --- | --- | --- |
| UF850 driver and MoveIt real/fake launch | Migrated via submodule | Provided by pinned `xarm_ros2` `v2.0.0-humble`. |
| MTC pouring action stack | Migrated | `mtc_tutorial` plus `mtc_action_library_*`. |
| RealSense YOLO detection | Migrated | `object_single_shot_detection.py` and `detection_only.launch.py`. |
| Detection to planning scene | Migrated | Started by `detection_only.launch.py` by default. |
| ChArUco/easy_handeye2 calibration | Replaced by RSS flow | Use `charuco_handeye_*` launch files and `handeye_pipeline`. |
| `publish_camera_root_from_handeye.py` | Legacy, not migrated | Revisit only if the RSS TF replay cannot validate on hardware. |
| Florence-2 perception | Legacy, not migrated | Broken RSS launch entry removed; keep in `uf_custom_ws` only. |
| Private calibration and recorded poses | Regenerate locally | Do not commit lab-specific calibration output. |
