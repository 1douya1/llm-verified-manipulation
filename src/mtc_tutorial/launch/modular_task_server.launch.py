#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # 启动模块化MTC任务服务器
        Node(
            package='mtc_tutorial',
            executable='modular_task_server',
            name='modular_task_server',
            output='screen',
            parameters=[
                {'task_type': 'pick'}  # 默认任务类型
            ],
            remappings=[
                # 可以在这里添加话题重映射如果需要的话
            ]
        ),
    ]) 