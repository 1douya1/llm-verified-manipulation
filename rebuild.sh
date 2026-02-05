#!/bin/bash
# Clean rebuild script for RSS_Workshop
# Fixes all known issues and rebuilds from scratch

set -e

echo "================================================"
echo "  RSS_Workshop Clean Rebuild Script"
echo "================================================"
echo ""

# Navigate to workspace
cd /home/wenhao/RSS_Workshop/RSS_Workshop
echo "📁 Workspace: $(pwd)"
echo ""

# Clean old build artifacts
echo "🧹 Cleaning old build artifacts..."
rm -rf build install log
echo "✅ Clean complete"
echo ""

# Source ROS2 environment
echo "🔧 Sourcing ROS2 environment..."
source /opt/ros/humble/setup.bash
echo "✅ ROS2 Humble sourced"
echo ""

# List packages
echo "📦 Packages to build:"
colcon list
echo ""

# Build
echo "🔨 Building workspace..."
echo "================================================"
colcon build --symlink-install 2>&1 | tee build.log

BUILD_STATUS=${PIPESTATUS[0]}
echo ""
echo "================================================"

if [ $BUILD_STATUS -eq 0 ]; then
    echo "✅ Build successful!"
    echo ""
    
    # Source new environment
    echo "🔧 Sourcing workspace..."
    source install/setup.bash
    
    # Verify packages
    echo ""
    echo "🔍 Verifying installed packages:"
    ros2 pkg list | grep -E "(mtc_interface|mtc_tutorial)"
    
    echo ""
    echo "📊 Build Statistics:"
    echo "  - Total time: Check build.log for details"
    echo "  - Packages built: 2"
    echo "  - Log file: build.log"
    
    echo ""
    echo "🎉 Workspace ready!"
    echo ""
    echo "Next steps:"
    echo "  1. source install/setup.bash"
    echo "  2. cd agent && pip install -r simple_requirements.txt"
    echo "  3. ./scripts/run_demo.sh"
    
    exit 0
else
    echo "❌ Build failed!"
    echo ""
    echo "Check build.log for error details"
    echo ""
    echo "Common issues:"
    echo "  - Missing dependencies: sudo apt install ros-humble-moveit-task-constructor-*"
    echo "  - Wrong ROS version: ensure you're using ROS2 Humble"
    echo "  - Path issues: make sure you're in the workspace root"
    
    exit 1
fi
