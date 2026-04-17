#!/usr/bin/env python3
"""
One-shot smoke test for the full real-robot stack.

Runs the smaller diagnostic helpers in sequence and emits a single PASS/FAIL
summary. Designed so a new operator can run ONE command before powering on
the arm and immediately see what is missing.

Order:
  1. Workspace + Python deps                    (no ROS required)
  2. /move_group + key topics                   -> diagnose_robot_env
  3. UF850 joint-acceleration limits config     -> check_joint_limits
  4. /tf for base -> camera                     -> handeye_transform_viewer --once
  5. /camera/color/image_raw publishing         (frame counter)

Run after sourcing the workspace:

    source install/setup.bash
    python3 scripts/diagnostics/system_diagnosis.py

Steps 2-5 require the corresponding ROS nodes to be running; each step
returns PASS/FAIL independently. Step 2 now exits non-zero from
`diagnose_robot_env.py` when `move_group` is not up (so the summary matches
what you see in the logs).
"""

import importlib
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def section(title):
    bar = '=' * 70
    print(f'\n{bar}\n{title}\n{bar}')


def run_step(label, fn):
    section(label)
    try:
        ok = bool(fn())
    except Exception as exc:  # noqa: BLE001
        print(f'[ERR] {label} raised: {exc}')
        ok = False
    return ok


# --------------------------------------------------------------------------- #
# 1. Workspace + Python deps
# --------------------------------------------------------------------------- #
def step_python_deps():
    required = [
        'rclpy', 'tf2_ros',
        'langchain_core', 'langchain_anthropic', 'langgraph',
        'cv2', 'numpy', 'yaml',
    ]
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
            print(f'  [OK]  {mod}')
        except ImportError:
            print(f'  [ERR] {mod} not importable')
            missing.append(mod)
    if missing:
        print('\nInstall missing Python packages first.')
        print('  See external-deps.md for the canonical pip list.')
        return False
    return True


# --------------------------------------------------------------------------- #
# 2. move_group + topics
# --------------------------------------------------------------------------- #
def step_move_group():
    script = os.path.join(HERE, 'diagnose_robot_env.py')
    if not os.path.isfile(script):
        print('[ERR] diagnose_robot_env.py missing next to this script.')
        return False
    rc = subprocess.call([sys.executable, script])
    return rc == 0


# --------------------------------------------------------------------------- #
# 3. Joint-acceleration limits
# --------------------------------------------------------------------------- #
def step_joint_limits():
    script = os.path.join(HERE, 'check_joint_limits.py')
    if not os.path.isfile(script):
        print('[ERR] check_joint_limits.py missing next to this script.')
        return False
    rc = subprocess.call([sys.executable, script])
    return rc == 0


# --------------------------------------------------------------------------- #
# 4. base -> camera TF (needs publisher running)
# --------------------------------------------------------------------------- #
def step_handeye_tf():
    script = os.path.join(HERE, 'handeye_transform_viewer.py')
    if not os.path.isfile(script):
        print('[ERR] handeye_transform_viewer.py missing next to this script.')
        return False
    rc = subprocess.call([sys.executable, script, '--once'])
    return rc == 0


# --------------------------------------------------------------------------- #
# 5. /camera/color/image_raw publishing
# --------------------------------------------------------------------------- #
def step_camera_topic():
    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import Image
    except ImportError as e:
        print(f'[ERR] rclpy/sensor_msgs not available: {e}')
        return False

    # Intel ROS2 driver often namespaces topics under /camera/camera/...
    topics = (
        '/camera/color/image_raw',
        '/camera/camera/color/image_raw',
    )

    rclpy.init()
    node = Node('camera_topic_probe')
    counter = {'n': 0, 'last_topic': ''}

    def make_cb(topic_name):
        def _cb(_msg):
            counter['n'] += 1
            counter['last_topic'] = topic_name
        return _cb

    for t in topics:
        node.create_subscription(Image, t, make_cb(t), 10)

    deadline = time.time() + 5.0
    while time.time() < deadline and counter['n'] < 5:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()

    if counter['n'] >= 5:
        print(f'  [OK]  received {counter["n"]} frames in 5s on {counter["last_topic"]!r}')
        return True
    print(f'  [ERR] only received {counter["n"]} frames in 5s on {list(topics)}')
    print('        USB 已插不等于 ROS 在发图：请先运行')
    print('          ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true enable_sync:=true')
    print('        然后用 ros2 topic list | grep image_raw 确认实际话题名。')
    return False


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def main():
    steps = [
        ('1. Python dependencies',        step_python_deps),
        ('2. move_group + key topics',    step_move_group),
        ('3. UF850 joint-limits config',  step_joint_limits),
        ('4. base -> camera TF',          step_handeye_tf),
        ('5. /camera/color/image_raw',    step_camera_topic),
    ]
    results = [(label, run_step(label, fn)) for label, fn in steps]

    section('Summary')
    overall = True
    for label, ok in results:
        flag = '[OK] ' if ok else '[FAIL]'
        print(f'  {flag} {label}')
        overall = overall and ok
    print('\n' + ('All checks passed.' if overall else 'Some checks failed - see above.'))
    print('Refer to docs/REAL_ROBOT_QUICK_START.md and docs/SAFETY_CHECKLIST.md before motion.')
    return 0 if overall else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrupted.')
        sys.exit(130)
