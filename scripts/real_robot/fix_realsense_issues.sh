#!/bin/bash
# ============================================================
#  RealSense Camera Diagnostic and Recovery Helper
# ============================================================
#
#  Common issues this script addresses:
#    - Stale realsense2_camera_node processes holding the USB device
#    - User not in the `video` group (permission denied on /dev/video*)
#    - Device enumeration failures after a hot-plug
#
#  Run this *before* the RealSense launch in terminal 1 if
#  `rs_launch.py` reports "No RealSense devices were found" or
#  the camera frame-rate drops to zero.
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo "RealSense diagnostic and recovery"
echo "=========================================="

# 1. Find and optionally kill stale RealSense processes
echo ""
echo "[1/6] Checking for stale realsense processes..."
REALSENSE_PIDS=$(ps aux | grep -E "realsense2_camera_node|rs_launch" | grep -v grep | awk '{print $2}' || true)

if [ -n "$REALSENSE_PIDS" ]; then
    echo "  Found PIDs: $REALSENSE_PIDS"
    read -p "  Kill these processes? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "$REALSENSE_PIDS" | xargs kill -9 2>/dev/null || true
        sleep 2
        echo "  Done."
    fi
else
    echo "  No stale processes."
fi

# 2. Check device holders
echo ""
echo "[2/6] Checking /dev/video* holders..."
OCCUPIED=$(lsof /dev/video* 2>/dev/null | grep -v "COMMAND" || true)
if [ -n "$OCCUPIED" ]; then
    echo "  Devices currently in use:"
    echo "$OCCUPIED" | head -5
    echo "  Waiting 3s for the device to release..."
    sleep 3
else
    echo "  No process is holding a /dev/video* device."
fi

# 3. Permission / group membership
echo ""
echo "[3/6] Checking group membership..."
if groups | grep -q video; then
    echo "  User is in the 'video' group."
else
    echo "  User is NOT in the 'video' group."
    echo "    sudo usermod -a -G video \$USER   # then re-login or 'newgrp video'"
fi

# 4. Video devices exist?
echo ""
echo "[4/6] Listing /dev/video* devices..."
VIDEO_DEVICES=$(ls /dev/video* 2>/dev/null | wc -l)
if [ "$VIDEO_DEVICES" -gt 0 ]; then
    echo "  Found $VIDEO_DEVICES device(s)."
    ls -l /dev/video* 2>/dev/null | head -5
else
    echo "  No /dev/video* devices visible. Re-plug the camera or run:"
    echo "    sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

# 5. ROS 2
echo ""
echo "[5/6] ROS 2 Humble install..."
if [ -f "/opt/ros/humble/setup.bash" ]; then
    echo "  /opt/ros/humble/setup.bash present."
else
    echo "  ROS 2 Humble not found at /opt/ros/humble/setup.bash."
fi

# 6. Workspace build status
echo ""
echo "[6/6] Workspace build artifact..."
if [ -f "$REPO_DIR/install/setup.bash" ]; then
    echo "  $REPO_DIR/install/setup.bash present."
elif [ -d "$REPO_DIR/../../install" ] && [ -f "$REPO_DIR/../../install/setup.bash" ]; then
    echo "  Parent-workspace install/setup.bash present."
else
    echo "  No colcon install/ detected; build first:"
    echo "    cd <workspace> && colcon build --symlink-install --packages-up-to mtc_tutorial"
fi

echo ""
echo "=========================================="
echo "Diagnostic complete."
echo "=========================================="
echo ""
echo "If the camera still does not enumerate, try in order:"
echo "  1. Unplug and re-plug the USB cable."
echo "  2. sudo udevadm control --reload-rules && sudo udevadm trigger"
echo "  3. lsusb | grep Intel   # confirm the device appears"
echo "  4. Test with 'rs-enumerate-devices' from librealsense."
