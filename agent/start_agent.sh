#!/bin/bash
# Natural-language agent launcher.
#
# Works whether RSS_Workshop is itself the colcon workspace (Layout A) or
# is nested inside a wrapper workspace under src/ (Layout B). See
# scripts/run_demo.sh for the same workspace-detection contract.

echo "================================================"
echo "  Launching natural-language robot agent"
echo "================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Detect colcon workspace root: prefer the repo itself if it contains
# src/mtc_*; otherwise walk up looking for a parent that holds src/.
detect_workspace_root() {
    if [ -f "$REPO_DIR/src/mtc_interface/package.xml" ] || \
       [ -f "$REPO_DIR/src/mtc_tutorial/package.xml" ]; then
        echo "$REPO_DIR"
        return
    fi
    local dir="$REPO_DIR"
    while [ "$dir" != "/" ]; do
        local parent="$(dirname "$dir")"
        local grandparent="$(dirname "$parent")"
        if [ "$(basename "$parent")" = "src" ]; then
            echo "$grandparent"
            return
        fi
        dir="$parent"
    done
    echo "$REPO_DIR"
}

WORKSPACE_DIR="$(detect_workspace_root)"

echo ""
echo "Workspace root: $WORKSPACE_DIR"
echo "Agent dir:      $SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo ""
    echo "[WARN] No .env file found at $SCRIPT_DIR/.env"
    echo "       Create one with your Anthropic API key, e.g.:"
    echo "         echo 'ANTHROPIC_API_KEY=your-key' > $SCRIPT_DIR/.env"
    echo ""
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Sourcing ROS2 workspace..."
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    # shellcheck disable=SC1091
    source "$WORKSPACE_DIR/install/setup.bash"
    echo "[OK] $WORKSPACE_DIR/install/setup.bash"
else
    echo "[ERR] $WORKSPACE_DIR/install/setup.bash not found."
    echo "      Build the workspace first:"
    echo "        cd $WORKSPACE_DIR && colcon build --symlink-install"
    exit 1
fi

echo ""
echo "Checking move_group..."
if ros2 node list 2>/dev/null | grep -q "move_group"; then
    echo "[OK] move_group is running"
else
    echo "[WARN] move_group is not running."
    echo "       In another terminal launch one of:"
    echo "         ros2 launch xarm_moveit_config uf850_moveit_fake.launch.py    # plan-only"
    echo "         ros2 launch xarm_moveit_config uf850_moveit_realmove.launch.py robot_ip:=<IP>  # real robot"
    echo ""
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Checking Python dependencies..."
if python3 -c "import langchain_core, langchain_anthropic, langgraph" 2>/dev/null; then
    echo "[OK] langchain / langgraph installed"
else
    echo "[ERR] Missing Python deps. Install with:"
    echo "      pip install -r $SCRIPT_DIR/simple_requirements.txt"
    exit 1
fi

echo ""
echo "================================================"
echo "  Starting agent (Ctrl+C to stop)"
echo "================================================"
echo ""

cd "$SCRIPT_DIR"
python3 agent_app.py "$@"






