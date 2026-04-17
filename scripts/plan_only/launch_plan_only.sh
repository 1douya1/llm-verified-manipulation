#!/bin/bash
# ============================================================
#  RSS Workshop - Plan-Only Launcher
# ============================================================
#
#  Pure planning demo: MoveIt2 + MTC with fake controllers, RViz
#  shows the UF850 robot and a fixed demo scene. No hardware or
#  camera required.
#
#  Typical invocation: called from scripts/run_demo.sh --plan-only
#  You can also call this script directly after sourcing your
#  workspace install/setup.bash.
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

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
echo "    source <your_ws>/install/setup.bash"
echo "    ros2 run mtc_tutorial test_modular_tasks"
echo ""
echo "========================================================"
echo ""

exec ros2 launch mtc_tutorial plan_only_demo.launch.py add_gripper:=true
