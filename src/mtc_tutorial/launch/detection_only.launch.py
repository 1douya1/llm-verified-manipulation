#!/usr/bin/env python3
"""
Detection-only launch file
Only launches object detection and marker publisher, does not launch camera and hand-eye calibration
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition
from launch_ros.actions import Node


def generate_launch_description():
    # Camera topic parameters
    color_topic_arg = DeclareLaunchArgument(
        'color_topic',
        default_value='/camera/camera/color/image_raw',
        description='Color image topic'
    )
    
    depth_topic_arg = DeclareLaunchArgument(
        'depth_topic',
        default_value='/camera/camera/aligned_depth_to_color/image_raw',
        description='Depth image topic'
    )
    
    camera_info_topic_arg = DeclareLaunchArgument(
        'camera_info_topic',
        default_value='/camera/camera/color/camera_info',
        description='Camera info topic'
    )
    
    # Frame parameters
    camera_frame_arg = DeclareLaunchArgument(
        'camera_frame',
        default_value='camera_color_optical_frame',
        description='Camera optical frame'
    )
    
    base_frame_arg = DeclareLaunchArgument(
        'base_frame',
        default_value='link_base',
        description='Robot base frame'
    )
    
    # YOLO parameters
    yolo_model_arg = DeclareLaunchArgument(
        'yolo_model',
        default_value='yolov8s.pt',
        description='YOLO model file path'
    )
    
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='Detection confidence threshold'
    )
    
    # Allowed detection object classes
    allowed_classes_arg = DeclareLaunchArgument(
        'allowed_classes',
        default_value="['person', 'cup', 'bottle', 'bowl']",
        description='Allowed object class list for detection'
    )
    
    # Depth unit parameters
    depth_scale_arg = DeclareLaunchArgument(
        'depth_scale',
        default_value='0.001',
        description='Depth unit conversion scale (RealSense typically 0.001)'
    )
    
    # Marker parameters
    marker_lifetime_arg = DeclareLaunchArgument(
        'marker_lifetime',
        default_value='3000.0',
        description='RViz marker lifetime (seconds)'
    )
    
    use_base_frame_arg = DeclareLaunchArgument(
        'use_base_frame',
        default_value='true',
        description='Whether to prefer using base frame for marker display'
    )

    # Bridge parameters
    enable_scene_bridge_arg = DeclareLaunchArgument(
        'enable_scene_bridge',
        default_value='true',
        description='Whether to launch detection_to_planning_scene in this launch file'
    )
    bridge_only_cup_arg = DeclareLaunchArgument(
        'bridge_only_cup',
        default_value='false',
        description='Whether bridge node only forwards cups'
    )
    bridge_min_conf_arg = DeclareLaunchArgument(
        'bridge_min_confidence',
        default_value='0.3',
        description='Bridge node minimum confidence filter threshold'
    )
    
    bridge_allowed_classes_arg = DeclareLaunchArgument(
        'bridge_allowed_classes',
        default_value="['cup', 'bowl', 'bottle']",
        description='Bridge node allowed object classes'
    )
    
    # One-shot object detection node
    oneshot_detection_node = Node(
        package='mtc_tutorial',
        executable='object_single_shot_detection.py',
        name='oneshot_object_detection',
        parameters=[{
            'color_topic': LaunchConfiguration('color_topic'),
            'depth_topic': LaunchConfiguration('depth_topic'),
            'camera_info_topic': LaunchConfiguration('camera_info_topic'),
            'camera_frame': LaunchConfiguration('camera_frame'),
            'base_frame': LaunchConfiguration('base_frame'),
            'yolo_model': LaunchConfiguration('yolo_model'),
            'confidence_threshold': LaunchConfiguration('confidence_threshold'),
            'depth_scale': LaunchConfiguration('depth_scale'),
            'allowed_classes': LaunchConfiguration('allowed_classes'),
            'verbose_logging': True,  # Enable verbose logging for debugging pointcloud fitting
            'enable_6d_pose': True,   # Ensure 6D pose estimation is enabled
        }],
        output='screen'
    )
    
    # Object marker publisher node
    marker_publisher_node = Node(
        package='mtc_tutorial',
        executable='object_marker_publisher.py',
        name='object_marker_publisher',
        parameters=[{
            'use_base_frame': LaunchConfiguration('use_base_frame'),
            'marker_lifetime': LaunchConfiguration('marker_lifetime'),
            'marker_scale': 0.01,
        }],
        output='screen'
    )

    # Detection → planning scene bridge node
    detection_to_scene_node = Node(
        package='mtc_tutorial',
        executable='detection_to_planning_scene.py',
        name='detection_to_planning_scene',
        condition=IfCondition(LaunchConfiguration('enable_scene_bridge')),
        parameters=[{
            'topic': 'object_detection_result',
            'only_cup': LaunchConfiguration('bridge_only_cup'),
            'allowed_classes': LaunchConfiguration('bridge_allowed_classes'),
            'min_confidence': LaunchConfiguration('bridge_min_confidence'),
            'apply_timeout': 10.0,
            'log_added': True,
        }],
        output='screen'
    )
    
    return LaunchDescription([
        # Parameter declarations
        color_topic_arg,
        depth_topic_arg,
        camera_info_topic_arg,
        camera_frame_arg,
        base_frame_arg,
        yolo_model_arg,
        confidence_threshold_arg,
        allowed_classes_arg,
        depth_scale_arg,
        marker_lifetime_arg,
        use_base_frame_arg,
        enable_scene_bridge_arg,
        bridge_only_cup_arg,
        bridge_min_conf_arg,
        bridge_allowed_classes_arg,
        
        # Node launches
        oneshot_detection_node,
        marker_publisher_node,
        detection_to_scene_node,
    ])
