#!/bin/bash
# ============================================================
#  RSS Workshop - Plan-Only Demo Launcher
# ============================================================
#
#  Default behaviour: launch MoveIt2 + MTC for UF850 in
#  fake-controller mode, open RViz, inject demo collision
#  objects, and let the reviewer trigger planning.
#
#  Usage:
#    ./scripts/run_demo.sh              # interactive mode select
#    ./scripts/run_demo.sh --plan-only  # skip menu, go straight
#    ./scripts/run_demo.sh --help
#
# ============================================================

set -e

# ---------- paths ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$WORKSPACE_DIR/agent"

# ---------- colours / helpers ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "  ${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "  ${RED}[ERR]${NC} $*"; }

# ---------- argument parsing ----------
MODE=""
for arg in "$@"; do
    case "$arg" in
        --plan-only) MODE="plan-only" ;;
        --agent)     MODE="agent" ;;
        --help|-h)
            echo "Usage: $0 [--plan-only | --agent | --help]"
            echo ""
            echo "  --plan-only   Launch MoveIt2 + RViz + MTC demo (default)"
            echo "  --agent       Launch with LLM agent (requires Python deps)"
            echo "  --help        Show this message"
            exit 0
            ;;
    esac
done

echo ""
echo "========================================================"
echo "   RSS Workshop - AI-Driven Robot Manipulation Demo"
echo "========================================================"
echo ""
echo "  Workspace : $WORKSPACE_DIR"
echo ""

# ============================================================
#  1. Environment checks
# ============================================================

echo "--- Checking environment ---"
echo ""

# 1a. ROS2 sourced?
if [ -z "$ROS_DISTRO" ]; then
    if [ -f /opt/ros/humble/setup.bash ]; then
        err "ROS2 not sourced. Run first:"
        echo "      source /opt/ros/humble/setup.bash"
    else
        err "ROS2 Humble not found at /opt/ros/humble/setup.bash"
        echo "      Install: https://docs.ros.org/en/humble/Installation.html"
    fi
    exit 1
fi

# 1b. Humble?
if [ "$ROS_DISTRO" != "humble" ]; then
    err "Expected ROS2 Humble but found: $ROS_DISTRO"
    exit 1
fi
ok "ROS2 Humble"

# 1c. MoveIt Task Constructor
if ! ros2 pkg list 2>/dev/null | grep -q "moveit_task_constructor_core"; then
    err "MoveIt Task Constructor not found."
    echo "      sudo apt install ros-humble-moveit-task-constructor-*"
    exit 1
fi
ok "MoveIt Task Constructor"

# 1d. xarm_moveit_config
if ! ros2 pkg list 2>/dev/null | grep -q "xarm_moveit_config"; then
    err "xarm_moveit_config not found (from xarm_ros2)."
    echo ""
    echo "      Install xarm_ros2 from source:"
    echo "        cd <your_workspace>/src"
    echo "        git clone https://github.com/xArm-Developer/xarm_ros2.git"
    echo "        cd .. && colcon build --symlink-install"
    echo "        source install/setup.bash"
    echo ""
    echo "      Or build in a separate workspace and source it before this script."
    exit 1
fi
ok "xarm_moveit_config (UF850 MoveIt config)"

# ============================================================
#  2. Build workspace if needed
# ============================================================

if [ ! -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    echo ""
    warn "Workspace not yet built. Building now..."
    echo ""
    (cd "$WORKSPACE_DIR" && colcon build --symlink-install)
    echo ""
fi

# Source workspace overlay
source "$WORKSPACE_DIR/install/setup.bash"
ok "Workspace sourced"

# Verify our packages
if ! ros2 pkg list 2>/dev/null | grep -q "mtc_tutorial"; then
    err "mtc_tutorial package not found after sourcing."
    echo "      Try: cd $WORKSPACE_DIR && colcon build --symlink-install"
    exit 1
fi
ok "mtc_tutorial + mtc_interface packages"
echo ""

# ============================================================
#  3. Mode selection
# ============================================================

if [ -z "$MODE" ]; then
    echo "========================================================"
    echo "  Select Demo Mode"
    echo "========================================================"
    echo ""
    echo "  1) Plan-Only (DEFAULT) - MoveIt2 + RViz + MTC planning"
    echo "     No robot hardware required. Opens RViz with UF850."
    echo ""
    echo "  2) Agent Dry-Run - LLM agent integration test"
    echo "     Requires Python deps + API key."
    echo ""
    echo "  3) Cancel"
    echo ""
    read -rp "  Enter choice [1]: " CHOICE
    CHOICE=${CHOICE:-1}
    echo ""

    case $CHOICE in
        1) MODE="plan-only" ;;
        2) MODE="agent" ;;
        3) echo "Cancelled."; exit 0 ;;
        *) err "Invalid choice: $CHOICE"; exit 1 ;;
    esac
fi

# ============================================================
#  4. Launch
# ============================================================

case $MODE in
    plan-only)
        echo "========================================================"
        echo "  Launching Plan-Only Demo"
        echo "========================================================"
        echo ""
        echo "  This will:"
        echo "    - Start MoveIt2 for UF850 with fake controllers"
        echo "    - Open RViz with robot model + planning scene"
        echo "    - Inject demo collision objects (table, cup, bowl)"
        echo "    - Start MTC modular_task_server"
        echo ""
        echo "  After RViz opens, trigger a plan with:"
        echo "    ros2 run mtc_tutorial test_modular_tasks"
        echo ""
        echo "========================================================"
        echo ""

        ros2 launch mtc_tutorial plan_only_demo.launch.py add_gripper:=true
        ;;

    agent)
        # Check agent deps
        if ! python3 -c "import langchain_core, langchain_anthropic, langgraph" 2>/dev/null; then
            err "Python agent dependencies not installed."
            echo "      pip install -r $AGENT_DIR/simple_requirements.txt"
            exit 1
        fi

        if [ ! -f "$AGENT_DIR/.env" ]; then
            warn "No .env file. Create one:"
            echo "      echo 'ANTHROPIC_API_KEY=sk-...' > $AGENT_DIR/.env"
        fi

        echo "========================================================"
        echo "  Launching Agent Dry-Run"
        echo "========================================================"
        echo ""
        cd "$AGENT_DIR"
        export AGENT_DRY_RUN=true
        python3 agent_app.py --dry-run
        ;;
esac

echo ""
echo "Demo finished. Thank you for trying RSS Workshop!"
