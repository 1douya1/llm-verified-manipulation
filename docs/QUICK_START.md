# Quick Start Guide

**Target Audience**: RSS reviewers and researchers  
**Recommended Mode**: Plan-Only with RViz (no robot hardware required)  
**Time Required**: ~10 minutes

---

## Prerequisites

- Ubuntu 22.04
- ROS2 Humble
- ~3GB disk space (including xarm_ros2)

---

## Option 1: Plan-Only Demo with RViz (Recommended) ⭐

**Purpose**: Launch MoveIt2 for UF850 in fake-controller mode, visualise a
demo planning scene in RViz, and trigger MTC task planning -- all without
robot hardware or perception.

### Step 1: Install ROS2 Dependencies

```bash
# Install ROS2 Humble (if not already installed)
sudo apt update
sudo apt install ros-humble-desktop

# Install MoveIt Task Constructor (REQUIRED)
sudo apt install ros-humble-moveit-task-constructor-*
```

### Step 2: Install xarm_ros2 (UF850 MoveIt Config)

This repository does **not** vendor xarm_ros2. You need to install it from
source so that the `xarm_moveit_config` package is available.

```bash
# Clone into the same workspace (simplest)
cd <workspace_root>/src
git clone https://github.com/xArm-Developer/xarm_ros2.git
```

Or, if you prefer a separate workspace:

```bash
mkdir -p ~/xarm_ws/src && cd ~/xarm_ws/src
git clone https://github.com/xArm-Developer/xarm_ros2.git
cd ~/xarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
# Source this BEFORE sourcing the RSS_Workshop workspace:
source ~/xarm_ws/install/setup.bash
```

### Step 3: Build

```bash
cd <workspace_root>     # the folder containing src/ with this repo
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

**Expected output** (the two packages from this repo):
```
Starting >>> mtc_interface
Finished <<< mtc_interface [~5s]
Starting >>> mtc_tutorial
Finished <<< mtc_tutorial [~18s]

Summary: 2 packages finished [~25s]
```

### Step 4: Launch the Plan-Only Demo

```bash
./scripts/run_demo.sh --plan-only
```

Or directly:

```bash
ros2 launch mtc_tutorial plan_only_demo.launch.py
```

### What You Will See

1. **RViz opens** with the UF850 robot model in its home position.
2. After a few seconds, **collision objects appear**:
   - A brown table surface
   - A blue cylinder ("object" -- the cup / source container)
   - A red cylinder ("bowl" -- the pour target)
3. The **modular_task_server** is running and ready for action goals.

### Step 5: Trigger a Plan

In a **new terminal**:

```bash
source install/setup.bash
ros2 run mtc_tutorial test_modular_tasks
```

This sends a pick-task goal to the MTC server. You should see planning
output in the terminal and (if successful) the planned trajectory in RViz.

### What This Demonstrates

- ROS2 packages build and launch correctly
- MoveIt2 + fake controllers work without hardware
- MTC task planning produces valid plans
- Planning scene manipulation via ROS2 messages
- **No real robot, camera, or perception required**

---

## Option 2: Agent Dry-Run (Optional)

**Additional Purpose**: Test LLM agent integration layer.

### Extra Dependencies

```bash
cd agent
pip install -r simple_requirements.txt

# Configure API key for LLM
echo "ANTHROPIC_API_KEY=your-key-here" > .env
```

### Run

```bash
./scripts/run_demo.sh --agent
```

**What you'll see**:
- Agent accepts natural language commands
- Plans tasks (does not execute)
- Prints planning results

---

## Option 3: Real Hardware (NOT Expected for Reviewers)

Requires specific hardware setup. See [EXECUTION_MODES.md](../EXECUTION_MODES.md) for details.

**Hardware needed**:
- UFACTORY UF850 robot
- RealSense D435i camera
- Hand-eye calibration
- Object detection setup

**We do NOT recommend this for reviewers.**

---

## Optional: MCP-Inspector Demo

If you want to explore the MCP (Model Context Protocol) tool interface used
by the AI agent, you can use MCP-Inspector to call tools interactively.

### Prerequisites

- The plan-only demo must be running (Step 4 above).
- Install the MCP SDK: `pip install "mcp[cli]"`

### Steps

1. **Start the MCP server** in a new terminal:
   ```bash
   source install/setup.bash
   python3 src/mtc_tutorial/scripts/mtc_mcp_server.py
   ```
   The server communicates over stdio.

2. **Connect MCP-Inspector**:
   ```bash
   mcp dev src/mtc_tutorial/scripts/mtc_mcp_server.py
   ```

3. **Call tools** in the Inspector UI:
   - `setup_planning_scene()` -- injects objects into the planning scene
   - `pick_container(source_pose={"x": 0.0, "y": -0.4, "z": 0.07}, plan_only=true)` -- plans a pick
   - `check_object_exists(object_id="object")` -- verifies the cup is in the scene

4. **Observe** JSON results in the Inspector and trajectory changes in RViz.

This is entirely optional and not required for reviewing the core contribution.

---

## Troubleshooting

### Build Fails

```bash
# Check ROS2 version
echo $ROS_DISTRO  # Should output: humble

# Install missing dependencies
sudo apt install ros-humble-moveit-task-constructor-*

# Clean rebuild
rm -rf build install log
colcon build --symlink-install
```

### "xarm_moveit_config not found"

```bash
# Verify xarm_ros2 is installed
ros2 pkg list | grep xarm_moveit_config

# If not found, install it (see Step 2 above)
cd <workspace>/src
git clone https://github.com/xArm-Developer/xarm_ros2.git
cd .. && colcon build --symlink-install
source install/setup.bash
```

### "Package not found" after build

```bash
# Make sure BOTH ROS2 and workspace are sourced
source /opt/ros/humble/setup.bash
source install/setup.bash

# Verify packages
ros2 pkg list | grep mtc
```

### No objects visible in RViz

- Wait ~8 seconds after launch for the scene spawner to publish.
- Check the **PlanningScene** display is enabled in RViz.
- Verify with: `ros2 topic echo /planning_scene --once`

---

## What Each Mode Tests

| Mode | Tests | Requirements |
|------|-------|--------------|
| **1. Plan-Only + RViz** | Build, MoveIt launch, scene injection, MTC planning, RViz visualisation | ROS2, MoveIt, xarm_ros2 |
| **2. Agent Dry-Run** | Above + LLM integration, natural language parsing | + Python deps, API key |
| **3. Real Robot** | Above + hardware execution, object detection | Full hardware setup |

---

## Expected Time

- **Plan-Only with RViz (Option 1)**: ~10 minutes
- **Agent Dry-Run (Option 2)**: ~15 minutes
- **Real Hardware (Option 3)**: Several hours (not recommended for reviewers)

---

## Intentionally Excluded

The following are **not** included in this repository and are **not** needed
for the plan-only demo:

| Component | Reason |
|-----------|--------|
| Real robot hardware | Demo uses fake controllers |
| RealSense camera / drivers | No perception in plan-only mode |
| YOLO / Florence detection models | Scene is injected from YAML |
| Hand-eye calibration data | Hardware-specific |
| xarm_ros2 source code | Not vendored; install separately |
| Isaac Sim integration | Experimental, not core to paper |

See [EXCLUDED_COMPONENTS.md](EXCLUDED_COMPONENTS.md) for full details.

---

## Next Steps

After completing Quick Start:

1. **Understand Architecture**: Read [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Explore Code**: Check `src/mtc_tutorial/src/` for C++ planning logic
3. **Read Paper**: Refer to RSS paper for theoretical background
4. **See Execution Modes**: [EXECUTION_MODES.md](../EXECUTION_MODES.md)

---

**Recommended Path for Reviewers**: Option 1 (Plan-Only with RViz)

This takes ~10 minutes and produces a visible result: RViz showing the robot,
collision objects, and planned trajectories.
