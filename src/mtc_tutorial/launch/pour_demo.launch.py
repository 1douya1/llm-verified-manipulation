from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    add_gripper = LaunchConfiguration('add_gripper')

    xarm_moveit_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('xarm_moveit_config'),
                'launch',
                #if you want to use the real moveit, please uncomme nt this line
                'uf850_moveit_realmove.launch.py',
                # 'uf850_moveit_fake.launch.py',
            )
        ),
        launch_arguments={
            'add_gripper': add_gripper,
        }.items()
    )

    server_node = Node(
        package='mtc_tutorial',
        executable='modular_task_server',
        output='screen'
    )

#     server_node_2 = Node(
#     package='mtc_tutorial',
#     executable='execute_pour_server',  
#     output='screen'
# )

    return LaunchDescription([
        DeclareLaunchArgument('add_gripper', default_value='true', description='Attach gripper to uf850'),
        xarm_moveit_launch,
        server_node,
    ]) 