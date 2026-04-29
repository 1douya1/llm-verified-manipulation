# Calibration Pipeline

Two transforms must be established before the robot can reliably grasp
something it sees:

1. **Camera intrinsics** -- the 3x3 camera matrix + distortion coefficients
   that let us back-project pixels into camera-frame rays.
2. **Hand-eye extrinsics** -- the rigid transform between the robot base (or
   end-effector, depending on mount) and the camera optical frame.

This document walks through both for the RSS reference setup: UF850 +
RealSense D435i + a 7x9 ChArUco board (25 mm squares, 18 mm markers).

---

## 1. Camera intrinsics (RealSense D435i)

The D435i ships with factory intrinsics that are good enough for a quick
demo, but for a paper-grade calibration you should record your own using
the standard ROS 2 camera calibrator:

```bash
ros2 launch realsense2_camera rs_launch.py
ros2 run camera_calibration cameracalibrator \
    --size 7x9 --square 0.025 \
    image:=/camera/camera/color/image_raw \
    camera:=/camera/camera/color
```

Accept calibration when RMS error is below ~0.3 px. The calibrator writes
two YAML files:

- `ost.yaml` (camera_info layout) -- copy the relevant fields into your
  own `realsense_calibration.yaml` (modelled on
  [`configs/realsense_calibration.example.yaml`](../configs/realsense_calibration.example.yaml)).
- `ost.txt` -- ignore.

Convert to the OpenCV layout used by the ChArUco publisher by copying the
camera matrix + distortion coefficients into a file modelled on
[`configs/realsense_calibration_opencv.example.yaml`](../configs/realsense_calibration_opencv.example.yaml).

**Never commit your real intrinsics** -- `.gitignore` already blocks
`**/*camera_intrinsics*.yaml`, but double-check with `git status` before
`git add`.

---

## 2. Hand-eye calibration

We use [easy_handeye2](https://github.com/marcoesposito1988/easy_handeye2)
(pinned as a git submodule at `src/easy_handeye2`). Two variants:

### 2a. Eye-in-hand (camera on `link_eef`)

```bash
ros2 launch mtc_tutorial charuco_handeye_calibration.launch.py \
    calibration_name:=charuco_eye_in_hand_1 \
    robot_effector_frame:=link_eef \
    camera_frame:=camera_color_optical_frame
```

Move the arm through 15-25 diverse poses while keeping the (fixed) ChArUco
board in view. Aim for pose diversity in both translation and rotation --
the solver needs geometric variety to untangle the AX = XB equation.

### 2b. Eye-to-hand (camera on a fixed tripod)

```bash
ros2 launch mtc_tutorial charuco_handeye_calibration.launch.py \
    calibration_name:=charuco_eye_to_hand_1 \
    robot_effector_frame:=link_eef \
    camera_frame:=camera_color_optical_frame
```

The ChArUco board is attached to `link_eef`; teach the arm to bring it into
the fixed camera's field of view from many angles. The
[`configs/calibration_waypoints.example.yaml`](../configs/calibration_waypoints.example.yaml)
gives an 18-pose starting set.

### Solving

Inside the `easy_handeye2` GUI, hit `Take sample` at every pose, then
`Compute` and `Save`. The solver uses Tsai-Lenz by default; other methods
can be selected via the GUI.

Acceptance criteria (typical):

- **Translation RMS**: < 5 mm
- **Rotation RMS**: < 1.0 deg
- Cross-validate by moving the arm to a *new* pose and checking that
  `tf2_echo link_base charuco_board` reports a transform consistent with
  the physical board location.

The result is written to
`~/.ros/easy_handeye2_calibrations/<calibration_name>.calib`. This file is
intentionally not tracked (see `.gitignore`).

---

## 3. Publishing the calibration

Three publishing strategies are available through
[`charuco_handeye_publish.launch.py`](../src/mtc_tutorial/launch/charuco_handeye_publish.launch.py):

### 3a. easy_handeye2 stock publisher (simplest)

```bash
ros2 launch mtc_tutorial charuco_handeye_publish.launch.py \
    calibration_name:=charuco_eye_to_hand_1
```

Publishes `link_base -> camera_color_optical_frame` directly from the saved
calibration. Good for everyday use.

### 3b. Static TF (production-recommended)

Once the calibration is stable, copy the 6-DoF values into the launch
arguments and use a static transform publisher -- this avoids the runtime
dependency on `easy_handeye2` nodes:

```bash
ros2 launch mtc_tutorial charuco_handeye_publish.launch.py \
    use_static_extrinsics:=true \
    bl_x:=0.457 bl_y:=-0.473 bl_z:=0.321 \
    bl_roll:=0.0  bl_pitch:=0.0  bl_yaw:=1.5708
```

Remember: the `tf2_ros static_transform_publisher` argument order is
**yaw pitch roll** (not roll pitch yaw) in ROS 2.

### 3c. (Not supported in this repo) Handeye -> base->camera_link composer

A helper that chains the handeye output with the fixed RealSense TF chain
to publish `link_base -> camera_link` instead of
`link_base -> camera_color_optical_frame` exists in a separate maniagent
project and is deliberately NOT included here; see
[../external-deps.md](../external-deps.md) section 4.

---

## 4. Validation

After publishing:

```bash
# TF chain
ros2 run tf2_ros tf2_echo link_base camera_color_optical_frame

# Full TF tree (produces frames.gv / frames.pdf)
ros2 run tf2_tools view_frames

# Cross-check against a known object. detection_only.launch.py starts the
# planning-scene bridge by default.
ros2 launch mtc_tutorial detection_only.launch.py
# In RViz: confirm the detected cup/bowl sits on the table, not floating.
```

If objects appear at the camera origin instead of on the table, the
`link_base -> camera_color_optical_frame` transform is almost certainly
wrong -- re-run step 3 (or the calibration itself).

---

## 5. When to recalibrate

- Camera was unplugged and re-plugged in a noticeably different orientation.
- Gripper was swapped, end-effector was re-mounted, or the tripod shifted.
- RMS errors at validation time exceed 1 cm.

When in doubt, re-calibrate. A 15-minute re-run is cheaper than a crash.
