# Excluded Components

This document explains what is intentionally excluded from the RSS_Workshop repository and why.

**Purpose**: This repository is a **reference implementation** for architectural transparency, not a complete hardware reproduction system.

---

## Executive Summary

**Excluded Categories**:
1. ✅ **Hardware-specific data** - Each system requires individual setup
2. ✅ **Large binary files** - Training data, models (can be added separately)  
3. ✅ **External packages** - Better maintained upstream
4. ✅ **Deployment infrastructure** - Production-specific

**Core principle**: Include what demonstrates the **software architecture** and **planning algorithms**. Exclude what is hardware-specific, deployment-specific, or better maintained elsewhere.

## Category 1: Hardware-Specific Data (NOT INCLUDED)

**Why excluded**: Each robot setup is unique and requires individual calibration.

### Calibration Data (Hardware-Specific)

**What**: Hand-eye transformation matrices, camera intrinsics, joint calibration

**Files excluded**:
- `config/hand_eye_calibration.yaml`
- `config/camera_intrinsics.yaml`
- `recorded_poses.yaml`

**Why excluded**:
- Unique to each robot + camera combination
- Requires physical calibration procedure
- Changes if hardware is moved or adjusted
- Not reproducible across different setups

**Impact on reviewers**: ❌ None (not needed for Plan-Only mode)

**How to obtain** (if you have hardware):
1. Install `easy_handeye2`: From source
2. Run calibration: `ros2 launch easy_handeye2 calibrate.launch.py`
3. Results saved automatically

**Calibration scripts included?**: ⚠️ Yes, but marked as optional utilities
- `src/mtc_tutorial/scripts/charuco_pose_publisher.py` - Helper script (optional)
- NOT required for Plan-Only or simulation modes

---

## Category 2: External ROS2 Packages (INSTALL SEPARATELY)

**Why excluded**: Better maintained by upstream developers.

### xarm_ros2 (Robot Driver)
- **Status**: External package
- **Install**: `git clone https://github.com/xArm-Developer/xarm_ros2.git`
- **Size**: ~200+ files, actively maintained
- **Required for**: Real robot execution, simulation (for URDF)
- **NOT required for**: Plan-Only verification

### moveit_task_constructor (Framework)
- **Status**: External package
- **Install**: `sudo apt install ros-humble-moveit-task-constructor-*`
- **Required for**: ALL modes (core dependency)
- **Size**: Framework package (apt-managed)

### find_object_2d (Optional Detection)
- **Status**: External package
- **Install**: `sudo apt install ros-humble-find-object-2d`
- **Required for**: Real robot with object detection
- **NOT required for**: Plan-Only, simulation

### realsense2_camera (Camera Driver)
- **Status**: External package
- **Install**: `sudo apt install ros-humble-realsense2-*`
- **Required for**: Real robot with camera
- **NOT required for**: Plan-Only, simulation

### easy_handeye2 (Calibration Tool)
- **Status**: External package
- **Install**: From source (only if calibrating)
- **Required for**: Initial hardware calibration
- **NOT required for**: Plan-Only, simulation, OR if already calibrated

---

### 2. Build Artifacts

Never committed to git:

- `build/` - Compiled binaries and object files
- `install/` - Installed packages
- `log/` - Build and runtime logs
- `__pycache__/` - Python bytecode
- `*.pyc`, `*.pyo` - Compiled Python files

**Reason**: Generated files, should be rebuilt on each system

---

### 3. Large Training Data

Excluded directories:

- `Yolo_pretrain/` - YOLO training datasets and models
- `Langraph_Agent/detector/` - Large detection training data (~1800 files)
- Any `.jpg`, `.png`, `.mp4` files (except documentation images)

**Reason**: 
- Large file sizes (100s of MB)
- User-specific training data
- Can be regenerated or downloaded separately

**Impact**: Object detection requires separate setup

---

### 4. Hardware-Specific Files

Excluded items:

- Camera calibration files (`realsense_calibration.yaml`)
- Hand-eye calibration results (`calibration_results/`)
- Recorded robot poses (`recorded_poses.yaml`)
- Hardware-specific configurations

**Reason**: Specific to each robot and camera setup

**Impact**: Users must calibrate their own system

---

### 5. Experimental/Deprecated Code

Excluded packages:

- `src/xarm_isaac/` - Isaac Sim integration (in development)
- `src/mtc_action_library_core/` - Superseded by direct integration
- `src/mtc_action_library_py/` - Superseded by direct integration
- Various test scripts in workspace root

**Reason**: 
- Not part of minimal working demo
- Alternative implementations exist
- Experimental or work-in-progress

**Impact**: None on core functionality

---

### 6. Documentation (Partially Excluded)

Kept only essential docs:

**Kept**:
- `README.md` - Main introduction
- `docs/ARCHITECTURE.md` - System design
- `docs/QUICK_START.md` - Setup guide
- `docs/API_REFERENCE.md` - API documentation

**Excluded** (from original workspace):
- 20+ specialized guides (Isaac Sim, YOLO, calibration details, etc.)
- Implementation notes and diagrams
- Troubleshooting guides for specific issues

**Reason**: Keep repo focused and minimal

**Where to find**: Original documentation available in source workspace

---

### 7. Configuration Files (Partially Excluded)

Kept only:

- `configs/agent_config.yaml` - Example agent configuration
- Package-specific configs in `src/*/config/`

Excluded:

- Camera intrinsics (hardware-specific)
- Calibration waypoints (user-specific)
- RViz configurations (optional visualization)

---

### 8. Scripts (Selectively Included)

Kept:

- `scripts/run_demo.sh` - Main demo launcher
- `agent/*.sh` - Agent helper scripts

Excluded:

- Hardware diagnostic scripts
- Camera troubleshooting scripts
- Calibration automation scripts

**Reason**: Not needed for basic demo

---

### 9. Secret/Private Data

Never include:

- API keys (`.env` files)
- Passwords or tokens
- Private research data
- Proprietary algorithms

**Note**: `.env.example` template is included, but never `.env` itself

---

## Migration from Full Workspace

If you have the full workspace and need excluded components:

### Get Detection Working

```bash
# Copy detection models (if you have them)
cp -r /path/to/full_workspace/Langraph_Agent/detector/ RSS_Workshop/agent/detector/

# Or retrain your own detection models
# ... follow YOLO training documentation
```

### Get Calibration Data

```bash
# Copy your calibration results
cp /path/to/full_workspace/config/realsense_calibration.yaml RSS_Workshop/configs/

# Or recalibrate your camera
ros2 launch easy_handeye2 calibrate.launch.py
```

### Add Experimental Features

```bash
# If you need Isaac Sim integration
cp -r /path/to/full_workspace/src/xarm_isaac/ RSS_Workshop/src/

# Rebuild workspace
cd RSS_Workshop
colcon build
```

---

## Minimal vs Full Comparison

| Feature | RSS_Workshop (Minimal) | Full Workspace |
|---------|----------------------|----------------|
| Size | ~50 files, <5 MB | ~3500 files, ~500 MB |
| Build time | ~30 seconds | ~5 minutes |
| Core functionality | ✅ All essential features | ✅ + experimental |
| Object detection | ❌ Requires separate setup | ✅ Included |
| Isaac Sim | ❌ Not included | ✅ Included |
| Documentation | ✅ Essential guides | ✅ Comprehensive |
| Dependencies | Minimal | Full stack |

---

## Why This Approach?

### Benefits of Minimal Repository

1. **Faster cloning**: Small repo size, quick to download
2. **Easier to understand**: Focus on core concepts
3. **Maintainable**: Less code to keep up-to-date
4. **Portable**: Fewer dependencies to install
5. **Educational**: Clear separation of components

### When to Use Full Workspace

Use the full workspace if you need:

- Pre-trained detection models
- Isaac Sim integration
- Complete documentation set
- Experimental features
- All calibration tools

---

## Questions?

### "Can I run the demo without XYZ?"

- **Without xarm_ros2**: No, robot driver is essential. Use simulation instead.
- **Without MoveIt**: No, motion planning is core functionality.
- **Without object detection**: Yes, manually specify object IDs.
- **Without RealSense**: Yes, use fake detection or manual objects.

### "How do I add back XYZ?"

See the "Migration from Full Workspace" section above, or install the external dependency directly.

### "Where is the original XYZ?"

Original workspace: `/path/to/uf_custom_ws/`
Specific components: Check the corresponding section in this document.

---

**Last Updated**: February 2025
