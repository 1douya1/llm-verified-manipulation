# Real-Robot Quick Start

From zero to a real-robot pouring demo in 10 steps. Expected time on a clean
Ubuntu 22.04 machine with ROS 2 Humble already installed: about 45 minutes
(most of which is the first `colcon build`).

> **Read [SAFETY_CHECKLIST.md](SAFETY_CHECKLIST.md) before running any motion.**
> The E-stop MUST be within arm's reach throughout the whole procedure.

---

## Target Hardware

- **Arm**: UFACTORY UF850 (6-DoF), firmware compatible with xarm_ros2
  `v2.0.0-humble`.
- **Camera**: Intel RealSense D435i, connected via a USB3 cable (USB2
  frame-rates are too low for YOLO).
- **Mount**: either eye-in-hand (camera on `link_eef`) or eye-to-hand (camera
  on a fixed tripod). Both are supported; the examples below use eye-to-hand.
- **Compute**: 16 GB RAM minimum, GPU optional but useful for YOLO.

---

## Step 1 -- Install system dependencies

```bash
sudo apt update
sudo apt install -y \
    ros-humble-desktop \
    ros-humble-moveit \
    ros-humble-moveit-task-constructor-* \
    ros-humble-realsense2-* \
    ros-humble-find-object-2d
```

## Step 2 -- Clone this repo with submodules

```bash
git clone https://github.com/1douya1/safe-robotic-pouring.git RSS_Workshop
cd RSS_Workshop
git submodule update --init --recursive   # pulls xarm_ros2 + xarm_sdk/cxx + easy_handeye2
```

`--recursive` is required: `xarm_ros2` contains its own C++ SDK submodule.

## Step 3 -- Build

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash
```

If the build fails with "package X not found" for anything inside
`xarm_ros2/`, re-run `git submodule update --init --recursive`.

## Step 4 -- Python dependencies

```bash
/usr/bin/python3 -m pip install -r agent/simple_requirements.txt
/usr/bin/python3 -m pip install "numpy<2" "opencv-python==4.10.0.84" ultralytics pyrealsense2
```

Use ROS Humble with Ubuntu's system Python 3.10. `cv_bridge` is built against
NumPy 1.x, so NumPy 2.x will fail at runtime with `_ARRAY_API not found`.

For the LLM agent:

```bash
echo "ANTHROPIC_API_KEY=sk-..." > agent/.env
```

## Step 5 -- Verify the camera

```bash
./scripts/real_robot/fix_realsense_issues.sh     # sanity check (no launch yet)
# In a new terminal:
ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true enable_sync:=true
# Another terminal:
ros2 topic hz /camera/camera/color/image_raw
```

You should see a stable ~30 Hz frame rate. If not, unplug and re-plug the USB
cable and rerun `fix_realsense_issues.sh`.

## Step 6 -- Verify the arm

```bash
ros2 launch mtc_tutorial pour_demo.launch.py robot_ip:=<UF850_IP>
```

RViz opens. Check that:
- The UF850 model is at its home joints.
- The MoveIt `move_group` node is up (`ros2 node list | grep move_group`).
- No red errors in the console about controllers.

## Step 7 -- Hand-eye calibration

Follow [CALIBRATION_PIPELINE.md](CALIBRATION_PIPELINE.md) end to end. The
short version:

```bash
# Print a ChArUco board (7x5, 25 mm squares, 18 mm markers) and mount it.
# Then:
ros2 launch mtc_tutorial charuco_handeye_calibration.launch.py \
    calibration_name:=charuco_eye_to_hand_1
# Save from the easy_handeye2 GUI once RMS < ~5 mm.
```

The result is stored under `~/.ros/easy_handeye2_calibrations/`.

## Step 8 -- Replay calibration in every subsequent run

```bash
ros2 launch mtc_tutorial charuco_handeye_publish.launch.py \
    calibration_name:=charuco_eye_to_hand_1
# OR, if you prefer a static transform:
ros2 launch mtc_tutorial charuco_handeye_publish.launch.py \
    use_static_extrinsics:=true \
    bl_x:=0.457 bl_y:=-0.473 bl_z:=0.321 \
    bl_roll:=<r> bl_pitch:=<p> bl_yaw:=<y>
```

Sanity check:

```bash
ros2 run tf2_ros tf2_echo link_base camera_color_optical_frame
# Values should be stable; translation should match your taped-up measurement.

# Or use the bundled poller (also prints base->ee and ee->camera in one go):
python3 scripts/diagnostics/handeye_transform_viewer.py --once
```

Before moving on, run the all-in-one stack diagnostic. It wraps every check
in `scripts/diagnostics/` and exits 0 only when everything is green:

```bash
python3 scripts/diagnostics/system_diagnosis.py
```

If a step fails, see `scripts/diagnostics/README.md` for the matching
single-purpose script (`diagnose_robot_env.py`, `check_joint_limits.py`,
`handeye_transform_viewer.py`).

## Step 9 -- Start perception

```bash
# Detection + planning-scene bridge
ros2 launch mtc_tutorial detection_only.launch.py
```

RViz should now show collision objects matching the real cups/bowls on the
table. If objects appear at the camera origin instead of on the table, the
TF chain from Step 8 is wrong -- re-verify before proceeding.

For bridge-only debugging, disable the built-in bridge and start it manually:

```bash
ros2 launch mtc_tutorial detection_only.launch.py enable_scene_bridge:=false
ros2 run mtc_tutorial detection_to_planning_scene.py
```

## Step 10 -- Run the agent

```bash
cd agent
python3 agent_app.py
# At the prompt: "Pour from the blue cup into the white bowl."
```

The agent plans a pick -> move -> pour -> place sequence, displays the plan
in RViz, and sends it to the MTC action server without an extra confirmation
gate. Use explicit `plan_only=True` tool calls or `python3 agent_app.py
--dry-run` when you want planning-only behavior.
**Keep your hand on the E-stop.**

---

## Extended capabilities (NOT part of this repo)

The following scripts exist in a separate "maniagent" project that happens
to share the same framework; they are **intentionally out of scope** for
the RSS pipeline:

- `pointcloud_geometry_fitter.py` -- 6-DoF pose refinement via point-cloud
  primitive fitting (cylinders/boxes).
- `publish_camera_root_from_handeye.py` -- alternative
  `link_base -> camera_link` TF publisher that composes handeye with the
  intrinsic camera TF chain.
- Florence-2 visual detection launch/node -- alternative perception backend
  using Florence-2 instead of YOLOv8.

These are mentioned only so that someone reading older logs or config
names is not confused. They will not be added here; see
[../external-deps.md](../external-deps.md) section 4.

---

## Recovery tips

- **RealSense stuck / no frames**: `./scripts/real_robot/fix_realsense_issues.sh`,
  then unplug and re-plug, then relaunch.
- **MoveIt reports "Unable to plan"**: ensure the TF chain includes
  `link_base -> camera_color_optical_frame` and that planning-scene objects
  are on the table, not floating. Run `tf2_echo` and `ros2 topic echo
  /planning_scene --once`.
- **xarm_ros2 builds fail**: the nested `xarm_sdk/cxx` submodule is
  probably not initialized. `cd src/xarm_ros2 && git submodule update --init --recursive`.
- **Agent hangs**: check `agent/.env` for the Anthropic API key; check
  network connectivity.

---

For deeper dives see:

- [CALIBRATION_PIPELINE.md](CALIBRATION_PIPELINE.md)
- [SAFETY_CHECKLIST.md](SAFETY_CHECKLIST.md)
- [ACTION_LIBRARY.md](ACTION_LIBRARY.md) (baseline / single-action testing path)
- [../EXECUTION_MODES.md](../EXECUTION_MODES.md)
- [../external-deps.md](../external-deps.md)
