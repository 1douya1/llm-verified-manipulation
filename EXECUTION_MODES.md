# Execution Modes

This repository supports three execution modes with different hardware and dependency requirements.

---

## Mode 1: Plan-Only / Dry-Run (DEFAULT) ⭐

**Purpose**: Verify system architecture and planning capabilities without robot hardware.

**What it does**:
- Builds ROS2 workspace
- Launches MTC planning servers
- Tests task planning pipeline
- Prints planning results to console
- **Does NOT execute on real hardware**

**Requirements**:
- ROS2 Humble
- MoveIt2
- MTC (MoveIt Task Constructor)
- Python dependencies (for agent layer)

**Use this mode if**:
- You are a reviewer verifying the system
- You don't have robot hardware
- You want to understand the planning architecture

**How to run**:
```bash
# Build workspace
colcon build --symlink-install
source install/setup.bash

# Run plan-only demo (NO robot required)
./scripts/run_demo.sh
# Select option 2: "Dry-run Mode"
```

**Expected output**:
- Task planning succeeds/fails
- Console output showing planning stages
- No robot motion

---

## Mode 2: Fake Execution (OPTIONAL)

**Purpose**: Test with MoveIt fake controllers (simulated joint states).

**What it does**:
- Same as Plan-Only mode
- Additionally publishes fake joint states
- Visualizes in RViz
- Still no real robot motion

**Requirements**:
- Same as Plan-Only mode
- `xarm_ros2` package (for robot description)

**Use this mode if**:
- You want to visualize planning in RViz
- You want to test joint-space trajectories
- You want to verify collision checking

**How to run**:
```bash
# Terminal 1: Launch fake controllers
source /opt/ros/humble/setup.bash
ros2 launch xarm_moveit_config xarm_moveit_fake.launch.py \
    dof:=6 robot_type:=xarm

# Terminal 2: Run agent
source install/setup.bash
cd agent
python3 agent_app.py
```

**Expected output**:
- RViz shows robot model
- Planned trajectories visualized
- Fake joint states published

---

## Mode 3: Real Robot Execution (ADVANCED)

**Purpose**: Execute on real hardware (NOT EXPECTED for reviewers).

**What it does**:
- Full hardware execution
- Requires calibrated system
- Requires object detection
- Safety-critical

**Requirements**:
- UFACTORY UF850 robot arm
- Intel RealSense D435i camera
- Calibrated hand-eye transformation
- Real-time object detection
- Anthropic API key (for LLM agent)

**Use this mode if**:
- You have the exact hardware setup
- System is fully calibrated
- You accept hardware risks

**How to run**:
```bash
# Terminal 1: Launch robot + MoveIt
ros2 launch xarm_moveit_config xarm_moveit_realmove.launch.py \
    robot_ip:=192.168.1.xxx dof:=6 robot_type:=xarm

# Terminal 2: Launch object detection
ros2 launch mtc_tutorial detection_only.launch.py

# Terminal 3: Run agent
source install/setup.bash
cd agent
python3 agent_app.py
```

**⚠️ Safety Warning**:
- Ensure workspace is clear
- Keep emergency stop accessible
- Monitor robot motion continuously
- Start with slow velocity scaling

---

## Comparison Table

| Feature | Plan-Only (DEFAULT) | Fake Execution | Real Robot |
|---------|---------------------|----------------|------------|
| **Robot hardware** | ❌ Not required | ❌ Not required | ✅ Required |
| **xarm_ros2** | ❌ Optional* | ✅ Required | ✅ Required |
| **Calibration** | ❌ Not needed | ❌ Not needed | ✅ Required |
| **Object detection** | ❌ Not needed | ❌ Not needed | ✅ Required |
| **Anthropic API key** | ⚠️ Optional** | ⚠️ Optional** | ✅ Required |
| **Planning verification** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Motion execution** | ❌ No | ⚠️ Simulated | ✅ Real |
| **Reviewer-friendly** | ✅ YES | ⚠️ Maybe | ❌ NO |

\* xarm_ros2 only needed if you want to verify URDF/SRDF loading  
\*\* API key optional if testing without LLM agent

---

## Recommended for RSS Reviewers

**We recommend Mode 1 (Plan-Only / Dry-Run)** because:

1. ✅ Minimal dependencies
2. ✅ No hardware required
3. ✅ Demonstrates system architecture
4. ✅ Verifies planning pipeline
5. ✅ Safe and reproducible

The goal of this repository is **transparency and reproducibility of the software architecture**, not full hardware reproduction.

---

## Implementation Details

### Plan-Only Mode Implementation

The plan-only mode works by:
1. Building MTC task graphs
2. Running motion planning
3. Checking for valid solutions
4. Printing results without execution

Key files:
- `src/mtc_tutorial/src/modular_task_builders.cpp` - Task planning logic
- `agent/action_tools.py` - Agent action abstraction
- `agent/agent_app.py --dry-run` - Dry-run flag

### Fake Execution Mode Implementation

Uses MoveIt's fake controller manager:
- Publishes fake joint states
- Updates planning scene
- No real hardware communication

Configured in xarm_ros2 launch files.

### Real Robot Mode Implementation

Full pipeline:
- ROS2 hardware interface → xarm_ros2 driver
- Object detection → planning scene injection
- LLM agent → MTC planning → trajectory execution

---

## FAQ

**Q: Which mode should reviewers use?**  
A: Mode 1 (Plan-Only / Dry-Run). It requires minimal setup and demonstrates the system architecture.

**Q: Can I reproduce the full hardware experiments?**  
A: Not without the exact hardware setup (UF850 robot + RealSense camera + calibration). This repo focuses on software transparency.

**Q: Why is calibration not included?**  
A: Calibration is hardware-specific. Each setup requires individual calibration. See `docs/EXCLUDED_COMPONENTS.md`.

**Q: Do I need the Anthropic API key?**  
A: Only for testing the LLM agent layer. Planning-only mode can work without it.

**Q: Is the agent layer required?**  
A: No. The MTC task builders (`src/mtc_tutorial/`) can be used standalone without the agent layer.

---

**Last Updated**: 2026-02-05  
**Recommended Mode for Reviewers**: Plan-Only / Dry-Run (Mode 1)
