from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("result_file", default_value="data/handeye_result.yaml"),
            DeclareLaunchArgument("parent_frame", default_value=""),
            DeclareLaunchArgument("child_frame", default_value=""),
            Node(
                package="handeye_pipeline",
                executable="handeye_publish_calibration_tf_node",
                name="handeye_publish_calibration_tf",
                output="screen",
                parameters=[
                    {
                        "result_file": LaunchConfiguration("result_file"),
                        "parent_frame": LaunchConfiguration("parent_frame"),
                        "child_frame": LaunchConfiguration("child_frame"),
                    }
                ],
            ),
        ]
    )
