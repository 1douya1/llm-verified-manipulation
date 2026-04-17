# External Dependencies

This repository uses a **mixed dependency strategy**: hardware-critical ROS2
packages are pinned as git submodules so that a fresh clone + `submodule
update` reproduces the exact tree we tested against; everything else is
installed via `apt` / `pip` with minimum compatible versions.

The submodule/apt/pip matrix below is the authoritative list. `README.md`
only links back here to avoid duplicate maintenance.

## 1. Submodules (pinned in `.gitmodules`)

| Path | Upstream | Locked at | Why this version |
|------|----------|-----------|-------------------|
| `src/xarm_ros2` | https://github.com/xArm-Developer/xarm_ros2 | tag `v2.0.0-humble` (commit `39cbe4a5a102fdd9f658e67296e8fc6e709c9b13`) | Only official Humble release tag; matches the UF850 firmware we validated against. Nested submodule `xarm_sdk/cxx` must also be initialized. |
| `src/easy_handeye2` | https://github.com/marcoesposito1988/easy_handeye2 | branch `master`, commit `b42cae604b5c01dbd650fcdac40dbf334cb098f4` | Upstream has no tags; `master` HEAD matches `package.xml` version `0.5.0` which is what the `uf_custom_ws` reference workspace uses. |

### Initialization

```bash
git clone https://github.com/1douya1/safe-robotic-pouring.git RSS_Workshop
cd RSS_Workshop
git submodule update --init --recursive
```

The `--recursive` flag is required because `xarm_ros2` itself contains the
`xarm_sdk/cxx` submodule (xArm C++ SDK).

### Updating a locked submodule

```bash
cd src/xarm_ros2
git fetch --tags
git checkout <new-tag>
cd ../..
git add src/xarm_ros2
git commit -m "Bump xarm_ros2 to <new-tag>"
```

We do not auto-bump. Submodule changes go through a PR with a short
justification note in this file.

## 2. APT packages (ROS 2 Humble)

See Section 3 of [README.md](README.md) for the base ROS 2 install. The
packages below are consumed at runtime but **not** vendored:

| Package | Plan-only | Real robot | Notes |
|---------|-----------|------------|-------|
| `ros-humble-desktop` | required | required | Base distro |
| `ros-humble-moveit` | required | required | MoveIt 2 |
| `ros-humble-moveit-task-constructor-*` | required | required | MTC core + demos |
| `ros-humble-realsense2-*` | not used | required | Intel RealSense D435i driver |
| `ros-humble-find-object-2d` | not used | optional | Alternative marker detector |

## 3. Python packages (`pip`)

| Package | Min version | Plan-only | Real robot | Notes |
|---------|-------------|-----------|------------|-------|
| `langchain-core` | 0.2.0 | optional (agent dry-run) | required | LangGraph state machine base |
| `langchain-anthropic` | 0.1.0 | optional | required | Claude API wrapper |
| `langgraph` | 0.1.0 | optional | required | Agent orchestration |
| `opencv-python` | 4.5 | not used | required | ChArUco calibration + YOLO input |
| `ultralytics` | 8.0 | not used | required | YOLO object detection |
| `pyrealsense2` | 2.54 | not used | required | Pulls RGB + depth frames |

Full pinned list lives in [agent/simple_requirements.txt](agent/simple_requirements.txt).

## 4. NOT included in this repository

The following are **intentionally** out of scope and documented for
transparency:

- `moveit_task_constructor` source — use the `ros-humble-moveit-task-constructor-*`
  apt packages.
- `Yolo_RealSense` — research-only object detection code from a separate
  project; see [docs/OPTIONAL_INTEGRATIONS.md](docs/OPTIONAL_INTEGRATIONS.md)
  (added in Phase 2).
- `pointcloud_geometry_fitter.py`, `publish_camera_root_from_handeye.py`,
  `launch/florence_visual_detection.launch.py` — these originate from a
  separate maniagent project and are not part of the RSS pipeline.
- Private calibration data (`recorded_poses.yaml`, camera intrinsics, etc.)
  are `.gitignore`d and must be regenerated locally.
