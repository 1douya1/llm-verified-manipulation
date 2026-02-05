#!/bin/bash
set -e

echo "=== RSS_Workshop 编译检查脚本 ==="
echo ""

# 切换到工作空间
cd /home/wenhao/RSS_Workshop/RSS_Workshop

echo "📁 当前目录: $(pwd)"
echo ""

# 检查包
echo "🔍 检查 ROS2 包..."
source /opt/ros/humble/setup.bash
colcon list
echo ""

# 清理旧构建
echo "🧹 清理旧构建产物..."
rm -rf build install log
echo "✅ 清理完成"
echo ""

# 编译
echo "🔨 开始编译..."
colcon build --symlink-install 2>&1 | tee build_output.log
BUILD_STATUS=${PIPESTATUS[0]}
echo ""

# 检查编译结果
if [ $BUILD_STATUS -eq 0 ]; then
    echo "✅ 编译成功！"
    echo ""
    
    # 检查生成的文件
    echo "📦 检查生成的包..."
    ls -la install/
    echo ""
    
    # 统计
    echo "📊 文件统计..."
    echo "总文件数: $(find . -type f | grep -v -E '(build|install|log|\.git)' | wc -l)"
    echo "Python文件: $(find . -name "*.py" | grep -v -E '(build|install|log)' | wc -l)"
    echo "C++文件: $(find . -name "*.cpp" -o -name "*.hpp" | grep -v -E '(build|install|log)' | wc -l)"
    echo "文档文件: $(find . -name "*.md" | wc -l)"
    echo ""
    
    # 验证包
    echo "🔍 验证安装的包..."
    source install/setup.bash
    ros2 pkg list | grep -E "(mtc_interface|mtc_tutorial)" || echo "警告: 未找到包"
    echo ""
    
    echo "✅ 所有检查完成！"
    exit 0
else
    echo "❌ 编译失败！"
    echo "查看 build_output.log 了解详情"
    exit 1
fi
