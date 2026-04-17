# Execution Modes

This repository supports three execution modes with different hardware and
dependency requirements. Plan-Only is the reviewer-friendly default;
Real Robot is the full paper reproduction.

---

## Mode 1: Plan-Only / Dry-Run (DEFAULT)

**Purpose**: Verify system architecture and planning capabilities without
robot hardware.

**What it does**:
- Builds the ROS 2 workspace.
- Launches MoveIt 2 for UF850 with fake controllers.
- Opens RViz with the robot model + demo planning scene (table, cup, bowl).
- Starts the MTC modular task server.
- Triggering a plan produces motion plans that are visualized but not sent
  to any real hardware.

**Requirements**:
- ROS 2 Humble + MoveIt 2 + MTC
- `xarm_ros2` (provided as a git submodule -- `git submodule update --init --recursive`)
- Python 3.10+

**How to run**:

```bash
./scripts/run_demo.sh --plan-only
# In another terminal:
source install/setup.bash
ros2 run mtc_tutorial test_modular_tasks
```

Expected output:
- RViz shows planned trajectory preview.
- Console prints per-stage planning results.
- No robot motion.

---

## Mode 2: Fake Execution (OPTIONAL)

**Purpose**: Same as Plan-Only but with MoveIt fake controllers that publish
fake joint states, so the robot model in RViz actually moves through the
plan.

**Requirements**: same as Plan-Only.

**How to run**:

```bash
# Terminal 1: fake controller + RViz
ros2 launch xarm_moveit_config xarm_moveit_fake.launch.py \
    dof:=6 robot_type:=xarm

# Terminal 2: agent dry-run
source install/setup.bash
cd agent
python3 agent_app.py --dry-run
```

Expected output:
- RViz shows the robot executing the plan against fake joint states.
- No real hardware communication.

---

## Mode 3: Real Robot Execution

**Purpose**: End-to-end paper reproduction. Requires UF850 + RealSense D435i
and a completed ChArUco hand-eye calibration.

**Safety first**: Read [docs/SAFETY_CHECKLIST.md](docs/SAFETY_CHECKLIST.md)
BEFORE any motion. Keep the E-stop within reach. Start with reduced
velocity scaling.

**Prerequisites**:
- UF850 arm, accessible on the lab network
- Intel RealSense D435i mounted (eye-in-hand OR eye-to-hand)
- ChArUco calibration completed -- see
  [docs/CALIBRATION_PIPELINE.md](docs/CALIBRATION_PIPELINE.md)
- `pip install` the perception extras (`opencv-python`, `ultralytics`,
  `pyrealsense2`) in addition to `agent/simple_requirements.txt`
- Anthropic API key (for the LLM agent)

**How to run** -- the `--real-robot` flag prints a guided 4-terminal plan:

```bash
./scripts/run_demo.sh --real-robot
```

It tells you to start these in separate terminals (full walkthrough in
[docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md)):

```bash
# Terminal 1 -- RealSense driver
ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true enable_sync:=true

# Terminal 2 -- UF850 + MoveIt + MTC action server
export QT_ENABLE_HIGHDPI_SCALING=0
ros2 launch mtc_tutorial pour_demo.launch.py

# Terminal 3a -- Replay hand-eye calibration (or run calibration first time)
ros2 launch mtc_tutorial charuco_handeye_publish.launch.py

# Terminal 3b -- Detection + planning-scene bridge
ros2 launch mtc_tutorial detection_only.launch.py
ros2 run mtc_tutorial detection_to_planning_scene.py

# Terminal 4 -- TF sanity checks (optional but recommended on first run)
ros2 run tf2_ros tf2_echo link_base camera_color_optical_frame

# Finally: run the LLM agent
cd agent && python3 agent_app.py
```

---

## Comparison Table

| Feature | Plan-Only | Fake Execution | Real Robot |
|---------|-----------|----------------|------------|
| Robot hardware | not required | not required | required |
| `xarm_ros2` submodule | required | required | required |
| Hand-eye calibration | not used | not used | required |
| Camera + intrinsics | not used | not used | required |
| Object detection (YOLO) | not used | not used | required |
| Anthropic API key | optional (agent dry-run) | optional | required |
| Planning verification | yes | yes | yes |
| Motion execution | no | simulated | real |
| Reviewer-friendly | yes | yes | no |

---

## Recommended for RSS Reviewers

Mode 1 (Plan-Only / Dry-Run). Minimal dependencies, no hardware, and still
exercises the same MTC planning stack, agent-to-action-tool glue, and
planning-scene assembly that drives the real robot. The reviewer tag
`v1.1.0-review` freezes exactly this mode for first-round review.

---

## Implementation Details

### Plan-Only Mode

- `scripts/run_demo.sh --plan-only` invokes `plan_only_demo.launch.py`.
- `plan_only_demo.launch.py` starts `move_group`, loads MoveIt config from
  the `xarm_ros2` submodule, injects the `demo_scene.yaml` collision
  objects, and starts the MTC modular task server.
- `ros2 run mtc_tutorial test_modular_tasks` triggers a pick plan; nothing
  is sent to a controller.

### Fake Execution Mode

- Uses MoveIt's `moveit_fake_controller_manager` -- see
  `xarm_moveit_config/launch/xarm_moveit_fake.launch.py` in the
  `src/xarm_ros2` submodule.
- Joint states are synthesized from the planned trajectory; there is no
  hardware interface.

### Real Robot Mode

- The `pour_demo.launch.py` launch loads the real UF850 driver from
  `src/xarm_ros2` and brings up MoveIt with the hardware interface.
- `charuco_handeye_publish.launch.py` publishes the `link_base ->
  camera_color_optical_frame` transform (either via `easy_handeye2`'s stock
  publisher or as a static transform, depending on `use_static_extrinsics`).
- `detection_to_planning_scene.py` subscribes to the YOLO detection topic
  and converts detections into MoveIt planning-scene objects.
- The agent (`agent/agent_app.py`) uses LangGraph to translate natural
  language into `action_tools` calls, which ultimately invoke the MTC
  action server from terminal 2.

---

## FAQ

**Q: Which mode should reviewers use?**
A: Mode 1 (Plan-Only). It demonstrates the full architecture without
requiring the lab hardware.

**Q: Can I reproduce the full hardware experiments?**
A: Yes -- start at [docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md).
You will need the same hardware (UF850 + D435i) or a close equivalent,
and you will need to run your own hand-eye calibration.

**Q: Why is calibration not shipped?**
A: Every physical setup has its own camera mount, lens, and table
geometry. Shipping someone else's calibration would silently produce
incorrect TF. Only the *example* skeleton is in the repo; you provide
the numbers yourself.

**Q: Do I need the Anthropic API key?**
A: Only for the LLM agent. You can drive the MTC pipeline directly through
`action_tools.py` or through the `mtc_action_library` baseline (P1.1 in
the v2.0 release) if you want a deterministic, LLM-free path.

---

**Version**: 2.0 (dual-track Plan-Only + Real-Robot)
**Reviewer snapshot**: tag `v1.1.0-review`
