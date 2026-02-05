# Optional Utilities

This document lists scripts and tools included in the repository that are **optional** and **not required** for the basic demonstration.

---

## Overview

**For Plan-Only verification**: None of these utilities are needed.

**For hardware execution**: Some may be useful for setup and debugging.

---

## Calibration Utilities (Hardware-Specific)

### `src/mtc_tutorial/scripts/charuco_pose_publisher.py`

**Purpose**: Publishes ChArUco calibration board poses for hand-eye calibration.

**When needed**: Only during initial hardware calibration setup

**Dependencies**: 
- RealSense camera
- ChArUco calibration board
- OpenCV with ArUco module

**Usage**:
```bash
ros2 run mtc_tutorial charuco_pose_publisher.py
```

**Required for reviewers**: ❌ NO

**Can be deleted**: Yes, if not using ChArUco calibration

---

## Detection Utilities (Optional)

### `src/mtc_tutorial/scripts/object_single_shot_detection.py`

**Purpose**: One-shot object detection using various backends.

**When needed**: For real-time object detection with camera

**Dependencies**:
- RealSense camera OR camera providing RGB-D topics
- Detection backend (find_object_2d, YOLO, etc.)

**Usage**:
```bash
ros2 launch mtc_tutorial detection_only.launch.py
```

**Required for reviewers**: ❌ NO (can specify manual object poses)

---

### `src/mtc_tutorial/scripts/detection_to_planning_scene.py`

**Purpose**: Injects detected objects into MoveIt planning scene.

**When needed**: When using real-time object detection

**Usage**: Automatically launched with detection nodes

**Required for reviewers**: ❌ NO

---

### `src/mtc_tutorial/scripts/pointcloud_geometry_fitter.py`

**Purpose**: Fits geometric primitives (cylinders) to point cloud data.

**When needed**: For improved object pose estimation from depth data

**Usage**: Called internally by detection pipeline

**Required for reviewers**: ❌ NO

---

## Visualization Utilities (Optional)

### `src/mtc_tutorial/scripts/object_marker_publisher.py`

**Purpose**: Publishes visualization markers for detected objects in RViz.

**When needed**: For debugging and visualization

**Usage**: Run alongside detection nodes

**Required for reviewers**: ❌ NO

---

## MCP Server (Reference Implementation)

### `src/mtc_tutorial/scripts/mtc_mcp_server.py`

**Purpose**: Model Context Protocol (MCP) server for robot control.

**Status**: Reference implementation (not used in main agent)

**When needed**: If exploring alternative agent architectures

**Required for reviewers**: ❌ NO

**Can be deleted**: Yes, not used by main agent (`agent_app.py`)

---

## Client Utilities

### `src/mtc_tutorial/scripts/ros_client_tools.py`

**Purpose**: ROS2 action client wrappers and utilities.

**Status**: Used by MCP server (reference implementation)

**Required for main demo**: ❌ NO (agent uses different path)

**Can be deleted**: Only if deleting mtc_mcp_server.py

---

### `src/mtc_tutorial/scripts/pour_client.py`

**Purpose**: Simple client for testing ExecutePour action.

**Status**: Debugging tool

**Usage**:
```bash
ros2 run mtc_tutorial pour_client.py
```

**Required for reviewers**: ❌ NO

---

## Web Interface (Optional)

### `agent/simple_backend.py`

**Purpose**: FastAPI backend for web-based control interface.

**When needed**: If you prefer web UI over command line

**Usage**:
```bash
cd agent
./start_simple.sh
# Open simple_frontend.html in browser
```

**Required for reviewers**: ❌ NO

---

### `agent/simple_frontend.html`

**Purpose**: Web UI for robot control.

**Companion to**: `simple_backend.py`

**Required for reviewers**: ❌ NO

---

## Launch Files (Selectively Used)

### Included Launch Files

**Active**:
- ✅ `detection_only.launch.py` - For hardware detection setup
- ✅ `modular_task_server.launch.py` - Main task server
- ✅ `pick_place_demo.launch.py` - Demo launcher
- ✅ `pour_demo.launch.py` - Pour task demo

**Disabled** (renamed):
- ⚠️ `florence_visual_detection.launch.py.disabled` - Requires missing script

---

## Summary Table

| Utility | Required for Plan-Only | Required for Simulation | Required for Hardware | Can Delete |
|---------|------------------------|-------------------------|----------------------|------------|
| charuco_pose_publisher.py | ❌ | ❌ | ⚠️ If using ChArUco | ✅ |
| object_single_shot_detection.py | ❌ | ❌ | ⚠️ If using detection | ⚠️ |
| detection_to_planning_scene.py | ❌ | ❌ | ✅ Yes | ⚠️ |
| pointcloud_geometry_fitter.py | ❌ | ❌ | ⚠️ Optional | ✅ |
| object_marker_publisher.py | ❌ | ❌ | ❌ | ✅ |
| mtc_mcp_server.py | ❌ | ❌ | ❌ | ✅ |
| ros_client_tools.py | ❌ | ❌ | ❌ | ⚠️ |
| pour_client.py | ❌ | ❌ | ❌ | ✅ |
| simple_backend.py | ❌ | ❌ | ❌ | ✅ |
| simple_frontend.html | ❌ | ❌ | ❌ | ✅ |

**Legend**:
- ✅ Yes
- ❌ No
- ⚠️ Maybe (depends on specific setup)

---

## Minimal Core Files

If you want the absolute minimal set:

**Must keep**:
- `src/mtc_tutorial/src/*.cpp` - Core planning algorithms
- `src/mtc_tutorial/include/` - Headers
- `src/mtc_interface/` - Message definitions
- `src/mtc_tutorial/CMakeLists.txt`, `package.xml` - Build config

**Can remove** (for minimal repo):
- All scripts in `src/mtc_tutorial/scripts/` (except if using detection)
- `agent/` directory (entire LLM agent layer)
- Web interface files
- Visualization utilities

**Result**: Pure MTC task planning system (~20 files)

---

## For Reviewers

**Recommendation**: Don't delete anything. All included files serve documentation or reference purposes.

The repository is already minimal (~60 files, ~5 MB). Further reduction would hurt clarity without significant benefit.

---

**Last Updated**: 2026-02-05  
**Purpose**: Clarify what's optional vs required
