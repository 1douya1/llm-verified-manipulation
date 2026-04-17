# Release Notes — v2.0.0 "Full Hardware Support"

`v2.0.0` is the first release where the repository ships **two parallel
tracks** that both work end-to-end:

- **Plan-Only** track (unchanged from `v1.1.0-review`): reviewers can run
  the MTC pour demo in MoveIt2 + RViz with no robot, no camera, no LLM
  key, and no submodule fetch beyond what apt provides.
- **Real-Robot** track (new in `v2.0.0`): a UF850 + RealSense D435i +
  LangGraph agent pipeline with calibration scripts, perception bridge,
  hand-eye TF replay, and operator-facing diagnostics.

The intent is that someone evaluating the paper still has a 5-minute path,
while someone reproducing the experiments has a single, self-contained
repo to clone.

---

## Highlights

### New: real-robot launch & control path
- `scripts/run_demo.sh --real-robot` and `scripts/real_robot/start_hardware.sh`
  print a guided 4-terminal launch plan (RealSense → UF850/MoveIt →
  calibration replay → detection bridge), so a fresh operator can copy
  commands instead of stitching launch files.
- `scripts/real_robot/fix_realsense_issues.sh` and `restart_realsense.sh`
  recover from the most common D435i USB / "device busy" failures.

### New: pinned hardware-stack submodules
- `src/xarm_ros2` pinned to upstream tag `v2.0.0-humble`
  (commit `39cbe4a5...`).
- `src/easy_handeye2` pinned to `master` HEAD
  `b42cae604b5c01dbd650fcdac40dbf334cb098f4`.
- `external-deps.md` documents the rationale and the
  `git submodule update --init --recursive` flow (the second `xarm_sdk/cxx`
  submodule **must** be initialized).

### New: `mtc_action_library` (C++ + Python)
- `src/mtc_action_library_core/`: shared C++ library wrapping pick / place
  / move-to-pour / return-home as reusable MTC stage builders.
- `src/mtc_action_library_py/`: pybind11 bindings + a Python
  `ActionLibrary.execute()` API, plus debug helpers.
- Intentionally **decoupled** from the MCP main chain in `mtc_tutorial`
  and the LangGraph agent — see `docs/ACTION_LIBRARY.md`. It exists as
  a baseline and as a single-action smoke-test entry point.

### New: calibration & perception assets in-tree
- `src/mtc_tutorial/launch/charuco_handeye_calibration.launch.py`
- `src/mtc_tutorial/launch/charuco_handeye_publish.launch.py`
  (refactored to remove the maniagent-only
  `publish_camera_root_from_handeye.py` dependency; now supports either
  the `easy_handeye2` stock publisher or a `static_transform_publisher`
  fallback).
- Updated `object_single_shot_detection.py`, `detection_to_planning_scene.py`,
  `ros_client_tools.py` to the versions verified on real hardware.
- `configs/*.example.yaml`: realsense intrinsics, eye-in-hand (xArm
  factory reference values for UF850 + D435i), eye-to-hand (skeleton —
  user must calibrate), and a 18-pose calibration waypoint set.

### New: operator diagnostics (`scripts/diagnostics/`)
- `system_diagnosis.py` — one-shot PASS/FAIL summary of the whole stack.
- `diagnose_robot_env.py`, `check_joint_limits.py` — ported from
  `uf_custom_ws` with hardcoded paths replaced by upward search and with
  references to maniagent-only scripts removed.
- `handeye_transform_viewer.py` — fresh utility, polls
  `link_base ↔ camera_color_optical_frame` (and the eye-in-hand variant)
  via `tf2_ros`.

### New: documentation suite
- `README.md` and `EXECUTION_MODES.md` rewritten as dual-track docs.
- `docs/REAL_ROBOT_QUICK_START.md` — 10-step setup-from-scratch guide.
- `docs/CALIBRATION_PIPELINE.md` — intrinsics + ChArUco hand-eye flow.
- `docs/SAFETY_CHECKLIST.md` — pre-power-on / pre-motion / post-crash
  checklist. **Read before enabling motion.**
- `docs/ACTION_LIBRARY.md` — what `mtc_action_library` is and isn't.
- `external-deps.md` — submodule / apt / pip / first-party matrix
  (single source of truth; README only summarizes).
- `scripts/diagnostics/README.md` — when to run each diagnostic.

### Hardened
- `.gitignore` blocks calibration outputs (`recorded_poses*.yaml`,
  `handeye_result*.yaml`, `*.calib`), camera intrinsics
  (`**/*camera_intrinsics*.yaml`), and ML model weights (`*.pt`,
  `*.pth`, `*.onnx`, `*.pb`, `*.weights`, `models/*.pth`, ...).
- `agent/start_agent.sh` rewritten with the same workspace-detection
  contract as `scripts/run_demo.sh`, so it works whether RSS_Workshop is
  the colcon workspace OR is nested under `some_ws/src/RSS_Workshop/`.

---

## Intentionally NOT included (and why)

These items are real, but live elsewhere and are out of scope for this repo:

- `pointcloud_geometry_fitter.py`, `publish_camera_root_from_handeye.py`,
  `launch/florence_visual_detection.launch.py` — belong to a separate
  maniagent project; only documented here for cross-reference.
- `Langraph_Agent/baselines/` and `Langraph_Agent/detector/` — research
  baselines; not migrated.
- `Yolo_RealSense` — research-only object detection; see
  `external-deps.md` Section 4.
- `moveit_task_constructor` source — install via the
  `ros-humble-moveit-task-constructor-*` apt packages.
- Private calibration data (`recorded_poses.yaml`, camera intrinsics,
  `*.calib`) — `.gitignore`d and must be regenerated locally.

---

## Upgrade / migration notes

### From `v1.1.0-review` (or any pre-v2 plan-only checkout)

```bash
git fetch origin
git checkout v2.0.0
git submodule update --init --recursive   # NEW: xarm_ros2 + easy_handeye2
rm -rf build install log
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash
./scripts/run_demo.sh --plan-only         # should behave exactly as before
```

### To enable real-robot mode

Follow `docs/REAL_ROBOT_QUICK_START.md` end to end. Before any motion,
run `scripts/diagnostics/system_diagnosis.py` and the
`docs/SAFETY_CHECKLIST.md` walkthrough.

---

## Known limitations

- The `mtc_action_library_*` packages currently target only the UF850
  joint group `uf850` and gripper group `uf850_gripper`. Other arms work
  in plan-only mode through `xarm_moveit_config`, but the action library
  bindings have not been retested.
- Hand-eye TF replay relies on `easy_handeye2`'s
  `~/.ros/easy_handeye2_calibrations/` cache. There is no in-repo binary
  cache; you must run the calibration once locally.
- The agent layer (`agent/agent_app.py`) requires an Anthropic API key
  with Claude 3.5+ access. There is no fallback to a local model in this
  release.
- **Gazebo/jsoncpp compatibility on newer CMake**: the thirdparty package
  `realsense_gazebo_plugin` (under `xarm_ros2/thirdparty/`) can fail
  configure due to policy compatibility in system `jsoncpp`.
  The practical workaround is:
  - skip `realsense_gazebo_plugin`
  - pass `--cmake-args -DCMAKE_POLICY_VERSION_MINIMUM=3.5`
  We still build `xarm_gazebo` in the full-build path, because
  `xarm_moveit_config/package.xml` explicitly depends on it.

---

## Verification checklist used to cut this release

Run these locally **before** tagging `v2.0.0`:

```bash
# 1. Repo + submodule integrity
git submodule status                       # both lines should start with a space (clean)
git submodule status --recursive | head    # xarm_sdk/cxx also initialized

# 2. Plan-only build + run (mandatory)
rm -rf build install log
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash
./scripts/run_demo.sh --plan-only          # RViz comes up, MTC plans visible

# 3. Full build (mandatory once, to prove the action library compiles)
# Use a shell that has ONLY /opt/ros/humble sourced (do not stack
# another workspace's install/ on top — colcon will warn about
# overriding xarm_* from an underlay and may pick wrong headers).
# If needed, clear overlay env first:
#   unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH
rm -rf build install log
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-skip realsense_gazebo_plugin \
  --cmake-args -DCMAKE_POLICY_VERSION_MINIMUM=3.5
colcon list | grep -E "mtc_(interface|tutorial|action_library_core|action_library_py)"

# 4. Real-robot dry-run (mandatory if you have hardware)
source install/setup.bash
python3 scripts/diagnostics/system_diagnosis.py    # 5/5 PASS
./scripts/run_demo.sh --real-robot                 # prints the launch plan
# Then exercise calibration replay + detection bridge per
# docs/REAL_ROBOT_QUICK_START.md steps 7-10.
```

If steps 2 and 3 pass but you cannot run step 4 (no hardware), still cut
the release — the plan-only demo is unaffected, and the real-robot path
is gated on the diagnostic script anyway.
