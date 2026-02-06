from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    # Declare parameters
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    
    # Declare launch argument
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time'
    )
    
    # MTC Demo node
    # Note: this node gets all necessary parameters from already-running move_group
    # No need to redeclare URDF/SRDF parameters here
    pick_place_demo = Node(
        package="mtc_tutorial",
        executable="mtc_tutorial",
        output="screen",
        parameters=[
            {'use_sim_time': use_sim_time},
        ],
        # Ensure node name matches name in C++ code
        name='mtc_tutorial_node',
        # Run in root namespace to ensure move_group can be found
        namespace='',
        # Remappings to ensure correct topic connections
        remappings=[
            ('/tf', 'tf'),
            ('/tf_static', 'tf_static'),
        ]
    )

    return LaunchDescription([
        declare_use_sim_time,
        pick_place_demo
    ])