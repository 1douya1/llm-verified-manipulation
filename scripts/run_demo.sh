#!/bin/bash
# ============================================================
#  RSS Workshop - Plan-Only Demo Launcher
# ============================================================
#
#  Supports TWO workspace layouts:
#
#  Layout A (RSS_Workshop IS the workspace root):
#    RSS_Workshop/            <- colcon build here
#      src/
#        mtc_interface/
#        mtc_tutorial/
#        xarm_ros2/
#      scripts/run_demo.sh
#
#  Layout B (wrapper workspace):
#    my_ws/                   <- colcon build here
#      src/
#        RSS_Workshop/        <- this repo
#          src/mtc_interface/ ...
#          scripts/run_demo.sh
#        xarm_ros2/
#
#  Usage:
#    ./scripts/run_demo.sh               # interactive mode menu
#    ./scripts/run_demo.sh --plan-only   # MoveIt2 + RViz + MTC (no hardware)
#    ./scripts/run_demo.sh --agent       # plan-only + LLM agent dry-run
#    ./scripts/run_demo.sh --real-robot  # real-robot launch plan (needs hw)
#    ./scripts/run_demo.sh --help
#
# ============================================================

set -e

# ---------- paths ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"     # always the RSS_Workshop repo dir
AGENT_DIR="$REPO_DIR/agent"

# Detect workspace root: find the nearest ancestor that has src/ as a child
# and is suitable for colcon build.
detect_workspace_root() {
    # If RSS_Workshop/src/ contains ROS packages directly, it IS the workspace
    if [ -f "$REPO_DIR/src/mtc_interface/package.xml" ] || \
       [ -f "$REPO_DIR/src/mtc_tutorial/package.xml" ]; then
        echo "$REPO_DIR"
        return
    fi
    # Otherwise walk up: the repo is inside some_ws/src/RSS_Workshop/
    local dir="$REPO_DIR"
    while [ "$dir" != "/" ]; do
        local parent="$(dirname "$dir")"
        local grandparent="$(dirname "$parent")"
        # Check if parent is "src" and grandparent looks like a workspace
        if [ "$(basename "$parent")" = "src" ]; then
            echo "$grandparent"
            return
        fi
        dir="$parent"
    done
    # Fallback
    echo "$REPO_DIR"
}

WS_ROOT="$(detect_workspace_root)"

# ---------- colours / helpers ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "  ${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "  ${RED}[ERR]${NC} $*"; }
info() { echo -e "  ${CYAN}[..]${NC} $*"; }

# ---------- argument parsing ----------
MODE=""
for arg in "$@"; do
    case "$arg" in
        --plan-only)   MODE="plan-only" ;;
        --agent)       MODE="agent" ;;
        --real-robot)  MODE="real-robot" ;;
        --help|-h)
            echo "Usage: $0 [--plan-only | --agent | --real-robot | --help]"
            echo ""
            echo "  --plan-only    MoveIt2 + RViz + MTC demo (no hardware)"
            echo "  --agent        Plan-only pipeline + LLM agent dry-run"
            echo "  --real-robot   Print the guided real-robot launch plan"
            echo "                 (see docs/REAL_ROBOT_QUICK_START.md)"
            echo "  --help         Show this message"
            exit 0
            ;;
    esac
done

# ---------- early-exit for real-robot: delegate to the real_robot helper ----------
if [ "$MODE" = "real-robot" ]; then
    exec "$SCRIPT_DIR/real_robot/start_hardware.sh" --ws "$REPO_DIR"
fi

echo ""
echo "========================================================"
echo "   RSS Workshop - AI-Driven Robot Manipulation Demo"
echo "========================================================"
echo ""
echo "  Repo dir  : $REPO_DIR"
echo "  Workspace : $WS_ROOT"
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

# 1d. xarm_ros2 -- check if xarm_moveit_config is available
XARM_AVAILABLE=false
if ros2 pkg list 2>/dev/null | grep -q "xarm_moveit_config"; then
    XARM_AVAILABLE=true
fi

# Preferred location is the submodule inside this repo ($REPO_DIR/src/xarm_ros2).
# Fall back to a sibling clone in the workspace if the user arranged it that way.
XARM_SRC=""
XARM_SUBMODULE_DIR="$REPO_DIR/src/xarm_ros2"
for candidate in "$XARM_SUBMODULE_DIR" "$WS_ROOT/src/xarm_ros2"; do
    if [ -f "$candidate/xarm_moveit_config/package.xml" ]; then
        XARM_SRC="$candidate"
        break
    fi
done

# Submodule directory exists but is empty (submodule not initialized)
if [ -z "$XARM_SRC" ] && [ -d "$XARM_SUBMODULE_DIR" ] && [ -z "$(ls -A "$XARM_SUBMODULE_DIR" 2>/dev/null)" ]; then
    err "src/xarm_ros2 is an empty submodule directory."
    echo ""
    echo "      Initialize the submodules first:"
    echo ""
    echo "        cd $REPO_DIR"
    echo "        git submodule update --init --recursive"
    echo ""
    echo "      Then re-run this script."
    exit 1
fi

if [ "$XARM_AVAILABLE" = false ] && [ -n "$XARM_SRC" ]; then
    warn "xarm_ros2 source found at $XARM_SRC but not built yet."
    info "Will build below."
elif [ "$XARM_AVAILABLE" = false ]; then
    err "xarm_moveit_config not found (from xarm_ros2)."
    echo ""
    echo "      This repo ships xarm_ros2 as a git submodule. Initialize it:"
    echo ""
    echo "        cd $REPO_DIR"
    echo "        git submodule update --init --recursive"
    echo ""
    echo "      Then re-run this script."
    exit 1
fi

if [ "$XARM_AVAILABLE" = true ]; then
    ok "xarm_moveit_config (UF850 MoveIt config)"
fi

# ============================================================
#  2. Build workspace if needed
# ============================================================

# Check if mtc_tutorial is already built and available
MTC_BUILT=false
if [ -f "$WS_ROOT/install/setup.bash" ]; then
    # Temporarily source to check
    (source "$WS_ROOT/install/setup.bash" && ros2 pkg list 2>/dev/null | grep -q "mtc_tutorial") && MTC_BUILT=true
fi

if [ "$MTC_BUILT" = false ]; then
    echo ""
    info "Building required packages (mtc_tutorial and dependencies)..."
    echo "      workspace: $WS_ROOT"
    echo ""
    echo "      Using: colcon build --symlink-install --packages-up-to mtc_tutorial"
    echo "      (This skips unneeded packages like realsense_gazebo_plugin)"
    echo ""
    (cd "$WS_ROOT" && colcon build --symlink-install --packages-up-to mtc_tutorial)
    echo ""
    if [ ! -f "$WS_ROOT/install/setup.bash" ]; then
        err "Build failed. Check the output above for errors."
        echo ""
        echo "      Common fix for xarm_ros2 nested-submodule errors:"
        echo "        cd $REPO_DIR && git submodule update --init --recursive"
        echo "        cd $WS_ROOT && colcon build --symlink-install --packages-up-to mtc_tutorial"
        exit 1
    fi
fi

# Source workspace overlay
source "$WS_ROOT/install/setup.bash"
ok "Workspace sourced ($WS_ROOT/install/setup.bash)"

# Verify our packages
if ! ros2 pkg list 2>/dev/null | grep -q "mtc_tutorial"; then
    err "mtc_tutorial package not found after sourcing."
    echo "      Try: cd $WS_ROOT && colcon build --symlink-install --packages-up-to mtc_tutorial"
    exit 1
fi
ok "mtc_tutorial + mtc_interface packages"

if ! ros2 pkg list 2>/dev/null | grep -q "xarm_moveit_config"; then
    err "xarm_moveit_config still not available after build."
    echo "      Common fix:"
    echo "        cd $REPO_DIR && git submodule update --init --recursive"
    echo "        cd $WS_ROOT && colcon build --symlink-install --packages-up-to mtc_tutorial"
    exit 1
fi
ok "xarm_moveit_config"
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
    echo "  3) Real Robot - Print the guided launch plan for hardware"
    echo "     Requires UF850 + RealSense D435i + completed calibration."
    echo "     See docs/REAL_ROBOT_QUICK_START.md."
    echo ""
    echo "  4) Cancel"
    echo ""
    read -rp "  Enter choice [1]: " CHOICE
    CHOICE=${CHOICE:-1}
    echo ""

    case $CHOICE in
        1) MODE="plan-only" ;;
        2) MODE="agent" ;;
        3) exec "$SCRIPT_DIR/real_robot/start_hardware.sh" --ws "$WS_ROOT" ;;
        4) echo "Cancelled."; exit 0 ;;
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
        echo "  After RViz opens, trigger a plan in a NEW terminal:"
        echo ""
        echo "    cd $WS_ROOT"
        echo "    source install/setup.bash"
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
