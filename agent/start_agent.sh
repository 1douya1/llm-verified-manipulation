#!/bin/bash
# 自然语言Agent启动脚本

echo "================================================"
echo "  🤖 启动自然语言机器人Agent"
echo "================================================"

# 检查是否在正确的目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "📁 工作空间: $WORKSPACE_DIR"
echo "📁 Agent目录: $SCRIPT_DIR"

# 检查.env文件
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo ""
    echo "⚠️  警告: 未找到.env文件"
    echo "   请创建.env文件并设置ANTHROPIC_API_KEY"
    echo ""
    echo "   echo 'ANTHROPIC_API_KEY=your-key' > $SCRIPT_DIR/.env"
    echo ""
    read -p "是否继续? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Source ROS2环境
echo ""
echo "🔧 正在Source ROS2环境..."
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
    echo "✅ ROS2环境已加载"
else
    echo "❌ 未找到 install/setup.bash"
    echo "   请先编译工作空间: colcon build"
    exit 1
fi

# 检查move_group是否运行
echo ""
echo "🔍 检查move_group状态..."
if ros2 node list | grep -q "move_group"; then
    echo "✅ move_group正在运行"
else
    echo "⚠️  警告: move_group未运行"
    echo "   建议在另一个终端启动:"
    echo "   ros2 launch xarm_moveit_config xarm_moveit_realmove.launch.py"
    echo ""
    read -p "是否继续? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查Python依赖
echo ""
echo "🐍 检查Python依赖..."
python3 -c "import langchain_core, langchain_anthropic, langgraph" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Python依赖已安装"
else
    echo "❌ 缺少Python依赖"
    echo "   请安装: pip install -r $SCRIPT_DIR/simple_requirements.txt"
    exit 1
fi

# 启动Agent
echo ""
echo "================================================"
echo "  🚀 启动Agent..."
echo "================================================"
echo ""

cd "$SCRIPT_DIR"
python3 agent_app.py






