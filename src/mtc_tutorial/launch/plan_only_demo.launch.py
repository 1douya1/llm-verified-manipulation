#!/usr/bin/env python3
"""
Plan-Only Demo Launch File for UF850 + MoveIt2

Launches:
  1. MoveIt2 with UF850 in fake-controller mode (from xarm_ros2)
  2. MTC modular_task_server (action server for pick/place/pour planning)
  3. spawn_demo_scene node (injects table + cup + bowl into PlanningScene)

Usage:
  ros2 launch mtc_tutorial plan_only_demo.launch.py
  ros2 launch mtc_tutorial plan_only_demo.launch.py add_gripper:=true

Requirements:
  - xarm_ros2 packages installed (provides xarm_moveit_config)
  - ros-humble-moveit-task-constructor-*
"""

import sys
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

# ---------- pre-flight check for xarm_moveit_config ----------
try:
    from ament_index_python.packages import get_package_share_directory
    _xarm_moveit_dir = get_package_share_directory('xarm_moveit_config')
except Exception:
    print("\n" + "=" * 70)
    print("ERROR: 'xarm_moveit_config' package not found!")
    print("")
    print("This demo requires xarm_ros2. Install it:")
    print("")
    print("  cd RSS_Workshop/src")
    print("  git clone https://github.com/xArm-Developer/xarm_ros2.git")
    print("  cd xarm_ros2 && git submodule sync && git submodule update --init --remote")
    print("  cd ../..    # back to RSS_Workshop (workspace root)")
    print("  colcon build --symlink-install")
    print("  source install/setup.bash")
    print("=" * 70 + "\n")
    sys.exit(1)


def generate_launch_description():
    # ---- Launch arguments ----
    add_gripper_arg = DeclareLaunchArgument(
        'add_gripper',
        default_value='true',
        description='Attach gripper to UF850 model',
    )
    add_gripper = LaunchConfiguration('add_gripper')

    # ---- 1. MoveIt2 fake-controller launch (from xarm_ros2) ----
    xarm_moveit_fake_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('xarm_moveit_config'),
                'launch',
                'uf850_moveit_fake.launch.py',
            ])
        ),
        launch_arguments={
            'add_gripper': add_gripper,
        }.items(),
    )

    # ---- 2. MTC modular_task_server ----
    mtc_server_node = Node(
        package='mtc_tutorial',
        executable='modular_task_server',
        name='modular_task_server',
        output='screen',
    )

    # ---- 3. Demo scene spawner (delayed to let MoveIt initialise) ----
    spawn_scene_node = Node(
        package='mtc_tutorial',
        executable='spawn_demo_scene.py',
        name='spawn_demo_scene',
        output='screen',
        parameters=[{
            'startup_delay': 5.0,  # seconds to wait for move_group
        }],
    )
    delayed_spawn = TimerAction(
        period=3.0,  # extra delay before even starting the node
        actions=[spawn_scene_node],
    )

    # ---- 4. User instructions ----
    instructions = LogInfo(msg="\n"
        "=================================================================\n"
        "  Plan-Only Demo is starting...\n"
        "=================================================================\n"
        "\n"
        "  Once RViz opens and you see the robot + collision objects:\n"
        "\n"
        "  Trigger a pick plan (plan-only, no execution):\n"
        "    ros2 run mtc_tutorial test_modular_tasks\n"
        "\n"
        "  Or send an action goal directly:\n"
        "    ros2 action send_goal /execute_modular_task \\\n"
        "      mtc_interface/action/ExecutePour \\\n"
        "      '{params: \"{\\\\\"task_type\\\\\": \\\\\"pick\\\\\", "
        "\\\\\"plan_only\\\\\": true}\"}'\n"
        "\n"
        "=================================================================\n"
    )

    return LaunchDescription([
        add_gripper_arg,
        instructions,
        xarm_moveit_fake_launch,
        mtc_server_node,
        delayed_spawn,
    ])
