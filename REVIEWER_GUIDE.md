# Reviewer Guide

**Target Audience**: RSS 2025 Conference Reviewers  
**Time Required**: ~15 minutes for basic verification  
**Hardware Required**: None

---

## What This Repository Is

This is a **reference implementation** and **transparency artifact** for an RSS system paper on AI-driven robot manipulation.

**Primary Goal**: Demonstrate software architecture and planning algorithms.

**NOT a Goal**: Reproduce full hardware experiments (requires specific robot setup).

---

## What Reviewers Should Do

### Recommended: 10-Minute Quick Verification

**Purpose**: Verify that the system builds and the core planning infrastructure is sound.

```bash
# 1. Install dependencies (5 min)
sudo apt update
sudo apt install ros-humble-desktop ros-humble-moveit-task-constructor-*

# 2. Clone and build (3 min)
git clone <repo-url> RSS_Workshop
cd RSS_Workshop
colcon build --symlink-install
source install/setup.bash

# 3. Run plan-only verification (2 min)
./scripts/run_demo.sh
# Select option 1: "Plan-Only Mode"
```

**Expected output**:
```
✅ mtc_tutorial package loaded
✅ mtc_interface messages loaded
✅ Plan-Only verification complete!
```

**What this demonstrates**:
- ✅ Code builds successfully with ROS2 Humble
- ✅ MTC task interfaces are properly defined
- ✅ Planning infrastructure is in place

---

## What Reviewers Should NOT Do

❌ **Do NOT attempt full hardware reproduction**
- Requires specific robot (UFACTORY UF850)
- Requires camera setup and calibration
- Requires trained object detection models
- Not expected or required for review

❌ **Do NOT expect plug-and-play execution**
- This is a reference implementation
- Hardware setups vary significantly
- Calibration is system-specific

---

## Understanding the System

### Architecture (5 minutes)

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to understand:
1. **Layer 2 (Core)**: MTC task planning (C++)
2. **Layer 4 (Optional)**: LLM agent interface (Python)
3. **Layer 1 (Hardware)**: MoveIt2 + robot driver

**Core contribution**: Hierarchical task planning with LLM interface (Layers 2-4).

### Code Structure (10 minutes)

**Core planning logic** (this is the main contribution):
```
src/mtc_tutorial/src/
├── modular_task_builders.cpp  # Task planning algorithms
├── execute_pour_server.cpp    # ROS2 action server
└── pour_task_builder.cpp      # Pour task logic
```

**Agent interface** (optional layer):
```
agent/
├── agent_app.py          # LLM agent entry point
├── action_tools.py       # Action abstraction
└── scene_manager.py      # Scene state management
```

**Interfaces**:
```
src/mtc_interface/
├── action/ExecutePour.action  # Pour task definition
└── msg/DetectionResult.msg    # Scene detection
```

---

## Execution Modes Explained

See [EXECUTION_MODES.md](EXECUTION_MODES.md) for full details.

### Mode 1: Plan-Only (Recommended) ⭐

**What it tests**: Software architecture, planning pipeline  
**Hardware**: None required  
**Time**: ~10 minutes  
**Use**: Reviewer verification

### Mode 2: Dry-Run with Agent (Optional)

**What it tests**: LLM integration layer  
**Hardware**: None required  
**Time**: ~15 minutes  
**Use**: Understanding agent architecture

**Requires**: Python dependencies + API key
```bash
cd agent
pip install -r simple_requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
```

### Mode 3: Full Simulation (Advanced, Optional)

**What it tests**: MoveIt planning, RViz visualization  
**Hardware**: None required (uses fake controllers)  
**Time**: ~30 minutes  
**Use**: Understanding motion planning

**Requires**: xarm_ros2 package
```bash
git clone https://github.com/xArm-Developer/xarm_ros2.git
```

### Mode 4: Real Robot (NOT for Reviewers)

**What it tests**: Full hardware execution  
**Hardware**: UFACTORY UF850 + RealSense camera + calibration  
**Time**: Several hours (setup + calibration)  
**Use**: Authors' original experiments

**NOT expected or required for review.**

---

## Common Questions

### Q: Can I reproduce the hardware experiments?

**A**: Not without the exact hardware setup. This repo focuses on **software transparency**, not hardware reproduction.

### Q: Why is calibration data not included?

**A**: Calibration is hardware-specific. Each robot+camera setup requires individual calibration. Including our calibration data would not be useful for other systems.

### Q: What about object detection models?

**A**: Pre-trained models are large (100s of MB) and training-data-specific. They can be added separately if needed, but are not required for understanding the architecture.

### Q: Is the agent layer essential?

**A**: No. The core contribution (MTC task planning) is in C++ and can be used without the agent layer. The agent provides a natural language interface.

### Q: Can I test without the Anthropic API key?

**A**: Yes, use Plan-Only mode (Mode 1) or simulation (Mode 3). The API key is only needed for the LLM agent layer.

---

## What's Intentionally Excluded

See [docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md) for complete details.

**Summary**:
1. ❌ **Hardware calibration data** - System-specific
2. ❌ **Object detection models** - Large files, training-specific
3. ❌ **External packages** (xarm_ros2, etc.) - Better maintained upstream
4. ❌ **Deployment infrastructure** - Production-specific

---

## File Organization

```
RSS_Workshop/
├── README.md                    # Main introduction
├── EXECUTION_MODES.md          # ⭐ Execution modes guide
├── REVIEWER_GUIDE.md           # ⭐ This file
├── PYTHON_DEPENDENCIES.md      # Python deps guide
│
├── agent/                       # Layer 4: LLM agent (optional)
│   ├── agent_app.py
│   ├── action_tools.py
│   └── scene_manager.py
│
├── src/                         # Layers 2-3: Core ROS2 packages
│   ├── mtc_interface/          # Interface definitions
│   └── mtc_tutorial/           # ⭐ Core planning algorithms
│       ├── src/*.cpp           # C++ task builders
│       └── scripts/*.py        # Python utilities
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md         # ⭐ System architecture
│   ├── QUICK_START.md          # Quick start guide
│   └── EXCLUDED_COMPONENTS.md  # What's not included
│
└── scripts/
    └── run_demo.sh             # ⭐ Demo launcher
```

**⭐ = Essential for reviewers**

---

## Evaluation Checklist

Use this checklist to evaluate the repository:

### Build and Structure (5 min)
- [ ] Repository clones successfully
- [ ] Builds with `colcon build --symlink-install`
- [ ] No build errors (warnings are OK)
- [ ] Package structure is clear

### Documentation (10 min)
- [ ] README clearly states purpose
- [ ] Execution modes are documented
- [ ] Excluded components are explained
- [ ] Architecture is described

### Code Quality (10 min)
- [ ] C++ code follows ROS2 conventions
- [ ] MTC task builders are well-structured
- [ ] Python code is readable
- [ ] Comments explain key algorithms

### Reproducibility (5 min)
- [ ] Plan-Only mode runs successfully
- [ ] Dependencies are documented
- [ ] Build instructions are clear
- [ ] No undocumented requirements

### Transparency (5 min)
- [ ] Core algorithms are visible
- [ ] System limitations are stated
- [ ] Hardware dependencies are clear
- [ ] Excluded components are justified

---

## Recommended Review Flow

1. **5 min**: Read README.md and this guide
2. **10 min**: Build and run Plan-Only mode
3. **10 min**: Read docs/ARCHITECTURE.md
4. **10 min**: Examine core code in `src/mtc_tutorial/src/`
5. **10 min**: (Optional) Test agent layer if interested

**Total**: ~45 minutes for thorough review

---

## Contact and Issues

If you encounter issues:

1. **Check documentation first**:
   - EXECUTION_MODES.md
   - docs/QUICK_START.md
   - BUILD_COMMANDS.md

2. **Common issues**:
   - Wrong ROS2 version → Must use Humble
   - Missing MTC → `sudo apt install ros-humble-moveit-task-constructor-*`
   - Build fails → Try clean rebuild: `rm -rf build install log && colcon build`

3. **For paper-related questions**: Contact authors via paper submission system

---

## Summary

**For reviewers**:
- ✅ Run Plan-Only mode (~10 minutes)
- ✅ Read architecture docs (~10 minutes)
- ✅ Examine core code (~10 minutes)
- ❌ Do NOT attempt full hardware reproduction

**Core contribution**: MTC-based hierarchical task planning with LLM interface

**This repository provides**: Software transparency and architectural reference

**This repository does NOT provide**: Plug-and-play hardware reproduction

---

**Last Updated**: 2026-02-05  
**Repository Purpose**: Reference implementation for RSS 2025 paper  
**Recommended Time**: 10-45 minutes depending on depth
