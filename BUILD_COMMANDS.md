# Build and Run Commands

## Prerequisites

Ensure you have:
- ROS2 Humble installed
- External dependencies installed (see README.md)
- Python dependencies installed

## Build Instructions

### 1. Source ROS2 Environment

```bash
source /opt/ros/humble/setup.bash
```

### 2. Build the Workspace

```bash
cd RSS_Workshop
colcon build --symlink-install
```

**Expected output**:
```
Starting >>> mtc_interface
Starting >>> mtc_tutorial
Finished <<< mtc_interface [X.Xs]
Finished <<< mtc_tutorial [X.Xs]

Summary: 2 packages finished [X.Xs]
```

**Note**: You may see warnings about unused variables or CMake policies. These are safe to ignore.

### 3. Source the Workspace

```bash
source install/setup.bash
```

## Run Commands

### Option 1: Using the Demo Script (Recommended)

```bash
./scripts/run_demo.sh
```

This interactive script will:
- Check all dependencies
- Verify ROS2 environment
- Offer choice between full/dry-run modes
- Launch the agent

### Option 2: Manual Launch

#### Terminal 1: Launch Robot/Simulation

**Real Robot**:
```bash
source /opt/ros/humble/setup.bash
ros2 launch xarm_moveit_config xarm_moveit_realmove.launch.py \
    robot_ip:=192.168.1.xxx \
    dof:=6 \
    robot_type:=xarm
```

**Simulation (Fake Controllers)**:
```bash
source /opt/ros/humble/setup.bash
ros2 launch xarm_moveit_config xarm_moveit_fake.launch.py \
    dof:=6 \
    robot_type:=xarm
```

#### Terminal 2: Launch Object Detection (Optional)

```bash
source install/setup.bash
ros2 launch mtc_tutorial detection_only.launch.py
```

#### Terminal 3: Launch Agent

```bash
cd agent
source ../install/setup.bash
python3 agent_app.py
```

Or with options:
```bash
python3 agent_app.py --dry-run  # Test without robot
```

## Verification Commands

### Check Build

```bash
# List built packages
colcon list

# Expected output:
# mtc_interface    src/mtc_interface    (ros.ament_cmake)
# mtc_tutorial     src/mtc_tutorial     (ros.ament_cmake)
```

### Check ROS2 Topics

```bash
source install/setup.bash
ros2 topic list
```

Expected topics (when robot/simulation is running):
- `/planning_scene`
- `/joint_states`
- `/move_group/monitored_planning_scene`
- `/object_detection_result` (if detection is running)

### Check ROS2 Nodes

```bash
ros2 node list
```

Expected nodes:
- `/move_group` (MoveIt)
- `/scene_manager_node` (when agent is running)
- Detection nodes (if detection is running)

### Check Action Servers

```bash
ros2 action list
```

Expected actions:
- `/execute_pour_server/execute_pour`
- `/recognize_objects` (if using move_group)

## Troubleshooting Build Issues

### Issue: "Package not found"

```bash
# Make sure you're in the workspace root
cd RSS_Workshop

# Check that packages are visible
colcon list

# If no packages found, check that package.xml exists
ls src/mtc_interface/package.xml
ls src/mtc_tutorial/package.xml
```

### Issue: "Could not find package 'moveit_task_constructor_core'"

This means MoveIt Task Constructor is not installed. Install it:

```bash
sudo apt install ros-humble-moveit-task-constructor-*
```

### Issue: "Python module not found"

```bash
# Install Python dependencies
cd agent
pip install -r simple_requirements.txt
```

### Issue: Build warnings about Boost/CMake policies

These are safe to ignore. They come from upstream MoveIt packages and don't affect functionality.

### Clean Build

If you encounter build issues, try a clean build:

```bash
# Remove build artifacts
rm -rf build install log

# Rebuild
colcon build --symlink-install
```

## Development Workflow

### Rebuild After Code Changes

**For C++ changes**:
```bash
colcon build --symlink-install --packages-select mtc_tutorial
source install/setup.bash
```

**For Python changes**:
No rebuild needed if you used `--symlink-install`. Just restart the node.

### Run Tests

```bash
# Unit tests (if implemented)
colcon test --packages-select mtc_interface mtc_tutorial

# Test results
colcon test-result --all
```

### Code Style

**Python**:
```bash
# Format code
black agent/*.py

# Lint
flake8 agent/*.py
```

**C++**:
```bash
# Format code
find src -name "*.cpp" -o -name "*.hpp" | xargs clang-format -i
```

## Performance Tips

### Faster Builds

```bash
# Use parallel jobs (adjust -j based on your CPU cores)
colcon build --symlink-install --parallel-workers 4
```

### Faster Agent Responses

- Use faster model: Edit `agent_app.py`, change model to "claude-sonnet-3-5"
- Reduce context: Limit chat history in `agent_app.py`

## Deployment

### Create Release Build

```bash
# Build with optimizations
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### Package for Distribution

```bash
# Create tarball
tar -czf rss_workshop_v1.0.tar.gz \
    --exclude='build' \
    --exclude='install' \
    --exclude='log' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    RSS_Workshop/
```

---

**Quick Reference**:

| Task | Command |
|------|---------|
| Build | `colcon build --symlink-install` |
| Source | `source install/setup.bash` |
| Run demo | `./scripts/run_demo.sh` |
| Run agent | `cd agent && python3 agent_app.py` |
| List topics | `ros2 topic list` |
| List nodes | `ros2 node list` |
| Clean | `rm -rf build install log` |

---

**Last Updated**: February 2025
