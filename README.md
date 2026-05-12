# RSS Workshop - AI-Driven Robot Manipulation System

**Supplementary Repository for RSS 2025 Conference**

## Purpose of This Repository

This repository supports **two complementary use cases** for the RSS system paper:

1. **Reviewer / researcher path** -- runnable planning pipeline with no robot
   hardware required (default, recommended for reviewers).
2. **Full hardware path** -- end-to-end execution on UFACTORY UF850 + Intel
   RealSense D435i, including ChArUco hand-eye calibration, perception, and
   MTC-based motion execution.

Both paths share the same source tree, build system, and agent layer -- the
only difference is whether the robot + camera are physically connected.

**Default Execution Mode**: **Plan-Only / Dry-Run** (recommended for reviewers).
For the real-robot path, start at
[docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md).

---

## Quick Navigation

**For reviewers** (no robot hardware):
- [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md) -- 10-minute verification path
- [EXECUTION_MODES.md](EXECUTION_MODES.md) -- Plan-Only vs Fake vs Real Robot
- [docs/QUICK_START.md](docs/QUICK_START.md) -- plan-only step-by-step setup

**For the full hardware path** (new in v2.0):
- [docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md) -- 10 steps from zero to real-robot pour
- [docs/CALIBRATION_PIPELINE.md](docs/CALIBRATION_PIPELINE.md) -- ChArUco hand-eye procedure
- [docs/SAFETY_CHECKLIST.md](docs/SAFETY_CHECKLIST.md) -- **must read before any motion**

**For understanding the code**:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- system design and data flow
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) -- action / tool reference
- [external-deps.md](external-deps.md) -- authoritative submodule / apt / pip matrix

**For troubleshooting**:
- [BUILD_COMMANDS.md](BUILD_COMMANDS.md) -- detailed build instructions
- [docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md) -- what is intentionally left out

---

---

## 30-Second Understanding

**What this repo contains**:
- ROS 2 packages for MTC-based manipulation planning
- LLM agent layer for natural language control (LangGraph + Claude)
- Plan-only pipeline -- no robot required
- Real-robot pipeline -- UF850 + RealSense D435i, ChArUco hand-eye calibration,
  perception-to-planning-scene bridge, MTC execution
- Pinned external dependencies as git submodules (xarm_ros2, easy_handeye2)

**What is NOT included**:
- Pre-trained object detection model weights (`*.pt`, `*.pth` are gitignored)
- Hardware-specific calibration data (ship only the example skeletons in [configs/](configs/))
- Scripts from a separate maniagent project that happen to share the same
  framework (see [external-deps.md](external-deps.md), Section 4)

**For reviewers**: Run in Plan-Only mode to verify the planning architecture.
**For robot operators**: See [docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md).

---

## 🎯 System Overview

This repository demonstrates an AI-driven robot manipulation system combining:
- **Natural Language Robot Control**: Use plain English to command tasks
- **AI Agent Integration**: LangGraph + Claude Sonnet 4 for task planning
- **Scene Understanding**: Real-time object detection and scene state management
- **MTC Task Planning**: High-level task-based motion planning

**System Architecture**:
```
Natural Language Input → Claude AI Agent → Action Tools → ROS2 MTC → (Planning/Execution)
                                ↓
                         Scene Manager (ROS2 subscriber)
```

**Key Innovation**: Hierarchical task planning with LLM-driven natural language interface.

---

## 🚀 What's Included

### Core Components

1. **AI Agent** (`agent/`)
   - `agent_app.py`: Main natural language agent application
   - `action_tools.py`: Robot action tools wrapped for LangChain
   - `scene_manager.py`: ROS2 scene state manager
   - `task_graph.py`: Task graph definitions for complex sequences

2. **ROS2 Packages** (`src/`)
   - `mtc_interface`: Message and action definitions
   - `mtc_tutorial`: MTC task builders and execution servers

3. **Documentation** (`docs/`)
   - Architecture diagrams
   - Usage guides
   - Quick reference materials

4. **Demo Script** (`scripts/`)
   - `run_demo.sh`: One-command demo launcher

---

## Requirements

### Plan-Only Mode (recommended for reviewers)
- Ubuntu 22.04 LTS
- ROS 2 Humble Hawksbill
- Python 3.10+
- MoveIt 2 + MoveIt Task Constructor
- **No robot or camera required**

### Real-Robot Mode (additional, on top of the above)
- UFACTORY UF850 robot arm (tested firmware: ships with v2.0.0-humble driver)
- Intel RealSense D435i camera
- Completed ChArUco hand-eye calibration (eye-in-hand *or* eye-to-hand)
- Anthropic API key (for the LLM agent)

**External dependencies** are documented in one place:
see [external-deps.md](external-deps.md) for the authoritative submodule /
apt / pip matrix. The short version is:

```bash
# 1. System ROS 2 + MoveIt + MTC
sudo apt install ros-humble-desktop ros-humble-moveit-task-constructor-*

# 2. Clone this repo WITH its submodules (xarm_ros2, easy_handeye2)
git clone https://github.com/1douya1/safe-robotic-pouring.git RSS_Workshop
cd RSS_Workshop
git submodule update --init --recursive   # pulls xarm_ros2 AND xarm_sdk/cxx
```

### Python Dependencies (Agent layer and/or real robot)

The full pip pin list (with which packages are required for plan-only vs
real-robot) is **only** maintained in
[external-deps.md, Section 3](external-deps.md#3-python-packages-pip).

For the agent / web UI in this repo:

```bash
pip install -r agent/simple_requirements.txt
```

For the real-robot perception layer install in addition:

```bash
/usr/bin/python3 -m pip install "numpy<2" "opencv-python==4.10.0.84" ultralytics pyrealsense2
```

ROS 2 Humble's `cv_bridge` is built against NumPy 1.x on Ubuntu 22.04, so
keep the system Python used by ROS on `numpy<2`.

---

## Quick Start (Plan-Only)

**See [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md) for the detailed reviewer path.**

```bash
# 1. Install system dependencies
sudo apt install ros-humble-desktop ros-humble-moveit-task-constructor-*

# 2. Clone with submodules
git clone https://github.com/1douya1/safe-robotic-pouring.git RSS_Workshop
cd RSS_Workshop
git submodule update --init --recursive

# 3. Build (only the packages we need)
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash

# Sanity check: mtc_tutorial should come from this workspace, xarm from xarm_ros2
ros2 pkg prefix mtc_tutorial
ros2 pkg prefix xarm_moveit_config

# 4. Launch plan-only demo
./scripts/run_demo.sh --plan-only
```

RViz opens with the UF850 robot, a table, a cup, and a bowl. Trigger a plan
from another terminal:

```bash
source install/setup.bash
ros2 run mtc_tutorial test_modular_tasks
```

> Note: `--packages-up-to mtc_tutorial` builds only `mtc_tutorial` and its
> dependencies (`mtc_interface`, `xarm_moveit_config`, ...), skipping unrelated
> packages (`realsense_gazebo_plugin`, etc.) that may fail on some systems.

> If you previously ran `colcon build` from `RSS_Workshop/src`, you may have a
> second overlay at `src/install`. Source that underlay before the repo overlay:
> `source src/install/setup.bash && source install/setup.bash`. To make the fix
> persistent, rebuild the repo overlay once after sourcing `src/install`.

---

## Quick Start (Real Robot)

**Before reading this section, read [docs/SAFETY_CHECKLIST.md](docs/SAFETY_CHECKLIST.md).**

```bash
# 0. One-time: ensure hand-eye calibration has been done.
#    See docs/CALIBRATION_PIPELINE.md for the ChArUco procedure.

# 1. Clone + build (same as plan-only)
git clone https://github.com/1douya1/safe-robotic-pouring.git RSS_Workshop
cd RSS_Workshop
git submodule update --init --recursive
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mtc_tutorial
source install/setup.bash

# 2. Python deps for perception + agent
/usr/bin/python3 -m pip install -r agent/simple_requirements.txt
/usr/bin/python3 -m pip install "numpy<2" "opencv-python==4.10.0.84" ultralytics pyrealsense2

# 3. Guided launch plan (prints the 4-terminal command set)
./scripts/run_demo.sh --real-robot
```

The guided launcher prints the exact commands to start (in separate terminals):
the RealSense driver, the UF850 + MoveIt stack, the calibration publisher, the
detection bridge, and TF sanity checks. Full walkthrough in
[docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md).

### Detailed Steps

See [docs/QUICK_START.md](docs/QUICK_START.md) (plan-only) or
[docs/REAL_ROBOT_QUICK_START.md](docs/REAL_ROBOT_QUICK_START.md) (real robot)
for step-by-step instructions with explanations.

---

## 🎮 Running the Plan-Only Demo

### Recommended for Reviewers

```bash
# One command:
./scripts/run_demo.sh --plan-only
```

This will:
1. Check all dependencies (ROS2, MoveIt, xarm_ros2)
2. Build the workspace if needed
3. Launch MoveIt2 for UF850 with fake controllers
4. Open RViz with the robot model and planning scene
5. Inject demo collision objects (table, cup, bowl)
6. Start the MTC modular_task_server

### What You'll See in RViz

- UF850 robot model in its home position
- A brown table surface
- A blue cylinder (cup / source container)
- A red cylinder (bowl / target container)
- The MotionPlanning panel for interactive planning

### Trigger a Plan

Once RViz is open and objects are visible, run in a **new terminal**:

```bash
source install/setup.bash
ros2 run mtc_tutorial test_modular_tasks
```

This plans a pick task (plan-only, no execution) and displays the result.

### For Hardware Execution

See [EXECUTION_MODES.md](EXECUTION_MODES.md) for simulation and real-robot modes.

**Hardware execution is NOT required for reviewing this work.**

---

## 📂 Repository Structure

```
RSS_Workshop/
├── agent/                          # AI Agent module
│   ├── agent_app.py               # Main natural language agent
│   ├── action_tools.py            # LangChain-wrapped robot actions
│   ├── scene_manager.py           # ROS2 scene state manager
│   ├── task_graph.py              # Task graph definitions
│   └── simple_requirements.txt    # Python dependencies
│
├── src/                           # ROS2 packages
│   ├── mtc_interface/            # Message/Action definitions
│   │   ├── action/ExecutePour.action, ExecuteTask.action
│   │   └── msg/DetectedObject.msg, DetectionResult.msg
│   │
│   └── mtc_tutorial/             # MTC task builders & demo
│       ├── src/                  # C++ task builders & servers
│       ├── scripts/              # Python utilities
│       │   ├── spawn_demo_scene.py   # <-- NEW: inject demo objects
│       │   └── mtc_mcp_server.py     # MCP tool server
│       ├── launch/
│       │   ├── plan_only_demo.launch.py  # <-- NEW: one-launch demo
│       │   └── pour_demo.launch.py
│       ├── config/
│       │   └── demo_scene.yaml   # <-- NEW: demo collision objects
│       └── include/              # C++ headers
│
├── scripts/
│   └── run_demo.sh               # One-command demo entrypoint
│
├── configs/                       # Agent configuration
├── docs/                          # Documentation
├── LICENSE
└── README.md
```

---

## 🔧 Available Robot Actions

The AI agent can execute the following actions through natural language:

### Core Actions
- **pick_object(object_id)**: Grasp a specified object
- **place_object(object_id, return_to_origin)**: Place an object at a location
- **move_and_pour(target_id, should_pour, velocity)**: Move to target and optionally pour
- **return_home()**: Return robot to home position

### Query Actions
- **get_scene_objects()**: List all detected objects
- **get_robot_status()**: Check robot state (holding, last action)
- **ask_user_clarification(question, options)**: Ask user for clarification

See `docs/API_REFERENCE.md` for detailed action parameters.

---

## 🧪 Testing

### Smoke Test (No Robot Required)

```bash
# Test the agent without robot hardware
cd agent
python3 -c "
from scene_manager import get_scene_manager
from action_tools import get_tools

scene = get_scene_manager()
tools = get_tools()
print('✅ All imports successful')
print(f'✅ Available tools: {len(tools)}')
"
```

### Integration Test (Requires ROS2)

```bash
# Ensure ROS2 is running, then:
source install/setup.bash
ros2 topic list  # Should show /planning_scene, /joint_states, etc.
ros2 node list   # Should show move_group if MoveIt is running
```

---

## Known Limitations / What is NOT Included

1. **Hardware-specific data** -- live intrinsics, hand-eye results, and
   `recorded_poses.yaml` are installation-specific and are gitignored. Only
   the `configs/*.example.yaml` *skeletons* are tracked.
2. **Object detection model weights** -- `*.pt`, `*.pth`, `*.onnx` are
   gitignored. Download or retrain YOLOv8 yourself.
3. **Isaac Sim integration** -- intentionally out of scope.
4. **`moveit_task_constructor`, `find_object_2d`, `realsense2_camera` source**
   -- consumed via `apt` rather than vendored.
5. **Scripts from a separate maniagent project** (pointcloud_geometry_fitter,
   publish_camera_root_from_handeye, florence_visual_detection launch) -- these
   share the same framework but are not part of the RSS pipeline. They are
   only referenced in [external-deps.md](external-deps.md), Section 4.

See [docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md) for the
long-form rationale.

---

## 🐛 Troubleshooting

### Agent won't start
```bash
# Check Python dependencies
pip install -r agent/simple_requirements.txt

# Verify ROS2 environment
source install/setup.bash
echo $ROS_DISTRO  # Should output: humble
```

### No objects detected
```bash
# Check if detection node is running
ros2 node list | grep detection

# Verify detection topic
ros2 topic echo /object_detection_result --once
```

### Planning failures
```bash
# Check MoveIt is running
ros2 node list | grep move_group

# Verify planning scene
ros2 topic echo /planning_scene --once

# Check joint states
ros2 topic echo /joint_states --once
```

---

## 📚 Additional Resources

- **Full Documentation**: See `docs/` folder
- **Agent Usage Guide**: `docs/AGENT_USAGE_GUIDE.md`
- **Architecture Overview**: `docs/ARCHITECTURE.md`
- **MTC Task Constructor**: https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html

---

## 📝 Citation

If you use this code in your research, please cite:

```bibtex
@inproceedings{rss2025_workshop,
  title={AI-Driven Robot Manipulation with Natural Language Control},
  author={Your Name},
  booktitle={Robotics: Science and Systems (RSS)},
  year={2025}
}
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **MoveIt Task Constructor**: For the powerful task-based planning framework
- **UFACTORY**: For the UF850 robot platform
- **Anthropic**: For the Claude AI model
- **LangChain/LangGraph**: For the AI agent framework

---

**Version**: 2.0 (Plan-Only + Real-Robot)
**Review snapshot**: tag `v1.1.0-review` preserves the original plan-only submission.
