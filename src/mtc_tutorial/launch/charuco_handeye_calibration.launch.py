#!/usr/bin/env python3
"""
Charuco手眼标定Launch文件
Eye-to-hand标定配置 - 相机固定在基座上，Charuco板固定在机械臂末端
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, ExecuteProcess
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource
import os
from pathlib import Path

def generate_launch_description():
    # 参数声明
    calibration_name_arg = DeclareLaunchArgument(
        'calibration_name',
        default_value='charuco_eye_to_hand_1',
        description='手眼标定的名称标识符'
    )
    
    # 图像话题参数
    image_topic_arg = DeclareLaunchArgument(
        'image_topic',
        default_value='/camera/camera/color/image_raw',
        description='RealSense相机图像话题'
    )
    
    camera_info_topic_arg = DeclareLaunchArgument(
        'camera_info_topic',
        default_value='/camera/camera/color/camera_info',
        description='RealSense相机信息话题'
    )
    
    use_camera_info_arg = DeclareLaunchArgument(
        'use_camera_info',
        default_value='true',
        description='是否使用camera_info自动获取内参（推荐）'
    )
    
    # 相机frame参数
    camera_frame_arg = DeclareLaunchArgument(
        'camera_frame',
        default_value='camera_color_optical_frame',
        description='相机光学坐标系frame'
    )
    
    # 机器人frame参数
    robot_base_frame_arg = DeclareLaunchArgument(
        'robot_base_frame',
        default_value='link_base',  # UF850的实际基座frame
        description='机器人基座坐标系'
    )
    
    robot_effector_frame_arg = DeclareLaunchArgument(
        'robot_effector_frame',
        default_value='link_eef',  # 根据您的UF850配置调整
        description='机器人末端执行器坐标系'
    )
    
    # Charuco板参数
    charuco_frame_arg = DeclareLaunchArgument(
        'charuco_frame',
        default_value='charuco_board',
        description='Charuco标定板坐标系'
    )
    
    # Path to the camera-intrinsics YAML (OpenCV layout). Default points at the
    # repository-provided example; override with `calibration_file:=...` on the
    # launch command line when running against your own calibrated camera.
    default_calibration_file = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', 'configs',
        'realsense_calibration_opencv.example.yaml'
    )
    calibration_file_arg = DeclareLaunchArgument(
        'calibration_file',
        default_value=default_calibration_file,
        description='Path to the camera intrinsics YAML (OpenCV layout).'
    )
    
    # Charuco板几何参数
    board_size_x_arg = DeclareLaunchArgument(
        'board_size_x',
        default_value='7',
        description='Charuco板X方向格子数'
    )
    
    board_size_y_arg = DeclareLaunchArgument(
        'board_size_y',
        default_value='5',
        description='Charuco板Y方向格子数'
    )
    
    square_length_arg = DeclareLaunchArgument(
        'square_length',
        default_value='0.025',
        description='Charuco板格子边长(米)'
    )
    
    marker_length_arg = DeclareLaunchArgument(
        'marker_length',
        default_value='0.018',
        description='Charuco板ArUco标记边长(米)'
    )
    
    # Charuco位姿发布器节点
    charuco_pose_publisher = Node(
        package='mtc_tutorial',
        executable='charuco_pose_publisher.py',
        name='charuco_pose_publisher',
        parameters=[{
            'image_topic': LaunchConfiguration('image_topic'),
            'camera_info_topic': LaunchConfiguration('camera_info_topic'),
            'use_camera_info': LaunchConfiguration('use_camera_info'),
            'camera_frame': LaunchConfiguration('camera_frame'),
            'marker_frame': LaunchConfiguration('charuco_frame'),
            'calibration_file': LaunchConfiguration('calibration_file'),
            'board_size_x': LaunchConfiguration('board_size_x'),
            'board_size_y': LaunchConfiguration('board_size_y'),
            'square_length': LaunchConfiguration('square_length'),
            'marker_length': LaunchConfiguration('marker_length'),
        }],
        output='screen'
    )
    
    # easy_handeye2标定Launch文件
    easy_handeye2_calibration = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('easy_handeye2'),
                'launch',
                'calibrate.launch.py'
            ])
        ]),
        launch_arguments={
            'name': LaunchConfiguration('calibration_name'),
            'calibration_type': 'eye_on_base',  # eye-to-hand = eye_on_base
            'robot_base_frame': LaunchConfiguration('robot_base_frame'),
            'robot_effector_frame': LaunchConfiguration('robot_effector_frame'),
            'tracking_base_frame': LaunchConfiguration('camera_frame'),
            'tracking_marker_frame': LaunchConfiguration('charuco_frame'),
        }.items()
    )
    
    return LaunchDescription([
        # 参数声明
        calibration_name_arg,
        image_topic_arg,
        camera_info_topic_arg,
        use_camera_info_arg,
        camera_frame_arg,
        robot_base_frame_arg,
        robot_effector_frame_arg,
        charuco_frame_arg,
        calibration_file_arg,
        board_size_x_arg,
        board_size_y_arg,
        square_length_arg,
        marker_length_arg,
        
        # 节点启动
        charuco_pose_publisher,
        easy_handeye2_calibration,
    ])
