from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    # 声明参数
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    
    # 声明launch参数
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time'
    )
    
    # MTC Demo node
    # 注意：这个节点会从已经运行的move_group获取所有必要的参数
    # 不需要在这里重复声明URDF/SRDF等参数
    pick_place_demo = Node(
        package="mtc_tutorial",
        executable="mtc_tutorial",
        output="screen",
        parameters=[
            {'use_sim_time': use_sim_time},
        ],
        # 确保节点名称与C++代码中的名称一致
        name='mtc_tutorial_node',
        # 在根命名空间运行，确保能找到move_group
        namespace='',
        # 重映射以确保正确的话题连接
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
        ]
    )

    return LaunchDescription([
        declare_use_sim_time,
        pick_place_demo
    ])