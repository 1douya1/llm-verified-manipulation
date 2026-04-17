#!/bin/bash
# 修复 CMake 缓存冲突并重新构建
#
# Skips Gazebo-only packages from xarm_ros2:
#   - realsense_gazebo_plugin (xarm_ros2/thirdparty)
#   - xarm_gazebo
# On newer CMake, jsoncpp's system config can fail while resolving Gazebo deps.
# Plan-only and real-robot execution paths in this repo do not need these.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔧 修复 CMake 缓存冲突问题"
echo "================================"
echo ""

echo "📁 当前位置: $(pwd)"
echo ""

# 清理旧的构建产物（这是关键！）
echo "🧹 清理旧的构建缓存..."
rm -rf build install log
echo "✅ 清理完成"
echo ""

# Source ROS2 环境
echo "🔧 Source ROS2 环境..."
# 为避免 overlay/underlay 串扰，建议在新终端运行本脚本，并且只 source humble。
if [[ "${AMENT_PREFIX_PATH:-}" == *"/uf_custom_ws/install"* ]]; then
    echo "⚠️  检测到 uf_custom_ws underlay，先清理 overlay 相关环境变量..."
    unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH
fi
source /opt/ros/humble/setup.bash
echo "✅ ROS2 环境已加载"
echo ""

# 重新构建
echo "🔨 开始全新构建..."
echo "================================"
colcon build --symlink-install --packages-skip realsense_gazebo_plugin xarm_gazebo

BUILD_STATUS=$?
echo ""
echo "================================"

if [ $BUILD_STATUS -eq 0 ]; then
    echo "✅ 构建成功！"
    echo ""
    
    # Source 新环境
    source install/setup.bash
    
    # 验证
    echo "🔍 验证安装的包..."
    ros2 pkg list | grep -E "(mtc_interface|mtc_tutorial)"
    
    echo ""
    echo "🎉 所有完成！工作空间已准备就绪。"
    echo ""
    echo "下一步："
    echo "  1. source install/setup.bash"
    echo "  2. ./scripts/run_demo.sh"
else
    echo "❌ 构建失败，请检查错误信息"
    exit 1
fi
