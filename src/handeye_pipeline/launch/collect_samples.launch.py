from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_config = PathJoinSubstitution(
        [FindPackageShare("handeye_pipeline"), "config", "uf850_realsense_eye_to_hand.yaml"]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config", default_value=default_config),
            DeclareLaunchArgument("sample_file", default_value=""),
            Node(
                package="handeye_pipeline",
                executable="handeye_collect_samples_node",
                name="handeye_collect_samples",
                output="screen",
                parameters=[
                    {
                        "config": LaunchConfiguration("config"),
                        "sample_file": LaunchConfiguration("sample_file"),
                    }
                ],
            ),
        ]
    )
