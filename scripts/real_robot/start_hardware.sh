#!/bin/bash
# ============================================================
#  RSS Workshop - Real-Robot Startup Helper
# ============================================================
#
#  This is a *guided launcher* for the full real-robot pipeline.
#  It prints the exact commands to run in four terminals:
#
#    Terminal 1: RealSense D435i driver
#    Terminal 2: UF850 arm + MoveIt (pour_demo launch)
#    Terminal 3a: Hand-eye calibration OR calibration replay
#    Terminal 3b: Detection + planning-scene bridge
#    Terminal 4: TF sanity checks
#
#  We deliberately do not run these in a single terminal: ROS 2
#  launch files dominate output and one misbehaving node would
#  hide errors from the others.
#
#  SAFETY: Before running, read docs/SAFETY_CHECKLIST.md and
#  ensure the workspace is clear and the E-stop is within reach.
#
#  Usage:
#    ./scripts/real_robot/start_hardware.sh [--ws <workspace>] [--robot-ip <ip>]
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

WS_DIR=""
ROBOT_IP="<UF850_IP>"
while [ $# -gt 0 ]; do
    case "$1" in
        --ws=*) WS_DIR="${1#--ws=}" ;;
        --ws)
            if [ $# -lt 2 ]; then echo "--ws requires a value" >&2; exit 1; fi
            WS_DIR="$2"
            shift 2
            continue
            ;;
        --robot-ip=*) ROBOT_IP="${1#--robot-ip=}" ;;
        --robot-ip)
            if [ $# -lt 2 ]; then echo "--robot-ip requires a value" >&2; exit 1; fi
            ROBOT_IP="$2"
            shift 2
            continue
            ;;
    esac
    shift
done

# Reasonable default: repo is the workspace root
if [ -z "$WS_DIR" ]; then
    if [ -f "$REPO_DIR/src/mtc_tutorial/package.xml" ]; then
        WS_DIR="$REPO_DIR"
    else
        # Walk up: repo inside <ws>/src/RSS_Workshop
        PARENT="$(dirname "$REPO_DIR")"
        GRAND="$(dirname "$PARENT")"
        if [ "$(basename "$PARENT")" = "src" ]; then
            WS_DIR="$GRAND"
        else
            WS_DIR="$REPO_DIR"
        fi
    fi
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

cat <<EOF

========================================================
  RSS Workshop - Real-Robot Launch Plan
========================================================

  Workspace : ${WS_DIR}

  ${YELLOW}SAFETY${NC}
  ------
  - Read ${CYAN}docs/SAFETY_CHECKLIST.md${NC} first.
  - Keep the E-stop within reach.
  - Clear the workspace of obstacles before any arm motion.

  Run the following blocks in separate terminals. Each block
  assumes you have already sourced the workspace overlay:

    source ${WS_DIR}/install/setup.bash

  ${GREEN}Terminal 1 -- RealSense camera${NC}
  ----------------------------------
    ros2 launch realsense2_camera rs_launch.py \\
        align_depth.enable:=true enable_sync:=true

  ${GREEN}Terminal 2 -- UF850 + MoveIt${NC}
  ----------------------------------
    # Avoid Qt high-DPI scaling issues on some setups
    export QT_ENABLE_HIGHDPI_SCALING=0
    ros2 launch mtc_tutorial pour_demo.launch.py robot_ip:=${ROBOT_IP}

  ${GREEN}Terminal 3a -- Hand-eye calibration REPLAY${NC}
  ----------------------------------
    # If calibration was already performed, replay the saved result
    # so that link_base -> camera_link TF is published.
    ros2 launch mtc_tutorial charuco_handeye_publish.launch.py

  (First-time calibration only -- see docs/CALIBRATION_PIPELINE.md)
    ros2 launch mtc_tutorial charuco_handeye_calibration.launch.py

  ${GREEN}Terminal 3b -- Detection + planning-scene bridge${NC}
  ----------------------------------
    ros2 launch mtc_tutorial detection_only.launch.py
    # detection_only.launch.py starts detection_to_planning_scene by default.

  ${GREEN}Terminal 4 -- TF sanity checks${NC}
  ----------------------------------
    ros2 run tf2_ros tf2_echo link_base camera_color_optical_frame
    # full tree visualization (writes frames.gv / frames.pdf)
    ros2 run tf2_tools view_frames

========================================================

EOF
