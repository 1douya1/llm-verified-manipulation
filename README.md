# RSS Workshop - AI-Driven Robot Manipulation System

**Supplementary Repository for RSS 2025 Conference**

## 📌 Purpose of This Repository

This is a **reference implementation** and **transparency artifact** accompanying an RSS system paper. The goal is to provide reviewers and researchers with:

1. ✅ **Architecture transparency**: Clear view of system components and data flow
2. ✅ **Planning verification**: Runnable task planning pipeline (no hardware required)
3. ✅ **Code reference**: Documented implementation of MTC-based manipulation
4. ❌ **NOT a full reproduction**: Hardware experiments require specific robot setup and calibration

**Default Execution Mode**: **Plan-Only / Dry-Run** (recommended for reviewers)

---

## 📖 Quick Navigation

**For Reviewers**:
- 🎯 [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md) - Start here! (10-minute verification path)
- 📋 [EXECUTION_MODES.md](EXECUTION_MODES.md) - Plan-Only vs Simulation vs Real Robot
- 🚀 [docs/QUICK_START.md](docs/QUICK_START.md) - Step-by-step setup

**For Understanding**:
- 🏗️ [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and module overview
- 📚 [docs/API_REFERENCE.md](docs/API_REFERENCE.md) - API documentation
- 🐍 [PYTHON_DEPENDENCIES.md](PYTHON_DEPENDENCIES.md) - When you need Python deps

**For Troubleshooting**:
- 🔧 [BUILD_COMMANDS.md](BUILD_COMMANDS.md) - Detailed build instructions
- ❓ [docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md) - What's not included and why

---

---

## ⚡ 30-Second Understanding

**What this repo contains**:
- ROS2 packages for MTC-based manipulation planning
- LLM agent layer for natural language control
- Task planning verification (no robot required)
- Documentation and examples

**What is NOT included**:
- Pre-trained object detection models
- Hardware calibration data
- Full hardware reproduction capability

**For reviewers**: Run in Plan-Only mode to verify planning architecture.

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

## 📋 Requirements

### Minimal Requirements (Plan-Only Mode - Recommended for Reviewers)
- **OS**: Ubuntu 22.04 LTS
- **ROS2**: Humble Hawksbill
- **Python**: 3.10+
- **MoveIt2**: Task Constructor framework

**This mode requires NO robot hardware.**

### Additional Requirements (Hardware Execution - Advanced)
- UFACTORY UF850 robot arm
- Intel RealSense D435i camera  
- Hand-eye calibration
- Pre-trained object detection

**Hardware execution is NOT required for reviewing this work.**

### External Dependencies (Plan-Only Mode)

You must install these packages separately:

1. **MoveIt Task Constructor** (REQUIRED)
   ```bash
   sudo apt install ros-humble-moveit-task-constructor-*
   ```

2. **xarm_ros2** (REQUIRED - provides UF850 URDF/SRDF and MoveIt config)

   This package is **not vendored** in this repository. Install from source:
   ```bash
   # Option A: clone into your workspace alongside this repo
   cd <your_workspace>/src
   git clone https://github.com/xArm-Developer/xarm_ros2.git
   cd .. && colcon build --symlink-install

   # Option B: separate workspace (source it before running the demo)
   mkdir -p ~/xarm_ws/src && cd ~/xarm_ws/src
   git clone https://github.com/xArm-Developer/xarm_ros2.git
   cd ~/xarm_ws && colcon build --symlink-install
   source ~/xarm_ws/install/setup.bash
   ```

   Official repo: https://github.com/xArm-Developer/xarm_ros2

3. **find_object_2d / RealSense** (NOT required for plan-only demo)
   ```bash
   # Only needed for real hardware with perception:
   sudo apt install ros-humble-find-object-2d ros-humble-realsense2-*
   ```

### Python Dependencies (Only for Agent Mode)
- `langchain-core>=0.3.0`
- `langchain-anthropic>=0.3.0`
- `langgraph>=0.2.0`
- `fastapi>=0.116.0`
- `python-dotenv>=1.0.0`

See `agent/simple_requirements.txt` for complete list.
**Not needed for the default plan-only demo.**

---

## 🛠️ Setup Instructions (Plan-Only Mode)

**See [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md) for detailed reviewer instructions.**

### Quick Setup (4 steps)

```bash
# 1. Install system dependencies
sudo apt install ros-humble-desktop ros-humble-moveit-task-constructor-*

# 2. Install xarm_ros2 (UF850 MoveIt config - NOT vendored in this repo)
cd <your_workspace>/src
git clone https://github.com/xArm-Developer/xarm_ros2.git

# 3. Build everything
cd <your_workspace>
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash

# 4. Launch plan-only demo (opens RViz with UF850 + demo scene)
./scripts/run_demo.sh --plan-only
```

**RViz will open** showing the UF850 robot, a table, a cup, and a bowl.
No robot hardware required.

### Detailed Steps

See [docs/QUICK_START.md](docs/QUICK_START.md) for step-by-step instructions with explanations.

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

## ⚠️ Known Limitations

### What's NOT Included

**This repository intentionally excludes**:

1. **Hardware-Specific Data** (system-specific):
   - Hand-eye calibration results
   - Camera intrinsic parameters
   - Robot-specific configurations
   - → Each setup requires individual calibration

2. **Object Detection Models** (large files):
   - Pre-trained YOLO models
   - Training datasets  
   - Detection checkpoints
   - → Can be added separately if needed

3. **External ROS2 Packages** (maintained upstream):
   - `xarm_ros2` - Robot driver (install separately)
   - `find_object_2d` - Detection (optional)
   - → See [EXECUTION_MODES.md](EXECUTION_MODES.md) for requirements per mode

4. **Experimental Features** (not core to paper):
   - Isaac Sim integration
   - Florence-2 visual detection
   - Alternative perception pipelines

**See [docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md) for complete details.**

### Current Constraints

- **Action Library**: The repository uses direct Python-C++ calls (not the separate `mtc_action_library_core` package)
- **Detection**: Object detection requires external camera setup and calibration
- **Simulation**: Full MTC task execution in simulation may have limitations due to collision checking

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

**Maintainer**: Your Name <your.email@example.com>  
**Last Updated**: February 2025  
**Version**: 1.0.0
