#!/bin/bash
# ============================================================
#  RealSense camera restart helper
# ============================================================
#
#  Kills stale realsense2_camera processes, waits for the USB
#  device to release, then relaunches the driver. Assumes the
#  workspace overlay is already sourced.
#
#  Usage:
#    source <ws>/install/setup.bash
#    ./scripts/real_robot/restart_realsense.sh
#
# ============================================================

set -e

echo "[1/3] Stopping stale RealSense processes..."
REALSENSE_PIDS=$(ps aux | grep -E "realsense2_camera_node|rs_launch" | grep -v grep | awk '{print $2}' || true)
if [ -n "$REALSENSE_PIDS" ]; then
    echo "  PIDs: $REALSENSE_PIDS"
    echo "$REALSENSE_PIDS" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

echo "[2/3] Checking device holders..."
OCCUPIED=$(lsof /dev/video* 2>/dev/null | grep -v "COMMAND" | wc -l)
if [ "$OCCUPIED" -gt 0 ]; then
    echo "  Device still busy; waiting 3s..."
    sleep 3
fi

echo "[3/3] Relaunching realsense2_camera..."
exec ros2 launch realsense2_camera rs_launch.py \
    align_depth.enable:=true \
    enable_sync:=true
