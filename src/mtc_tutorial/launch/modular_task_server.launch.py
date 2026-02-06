#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Launch modular MTC task server
        Node(
            package='mtc_tutorial',
            executable='modular_task_server',
            name='modular_task_server',
            output='screen',
            parameters=[
                {'task_type': 'pick'}  # Default task type
            ],
            remappings=[
                # Can add topic remappings here if needed
            ]
        ),
    ]) 