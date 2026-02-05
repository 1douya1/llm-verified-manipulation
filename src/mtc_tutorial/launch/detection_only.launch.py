#!/usr/bin/env python3
"""
仅检测节点启动文件
只启动物体检测和标记发布器，不启动相机和手眼标定
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 相机话题参数
    color_topic_arg = DeclareLaunchArgument(
        'color_topic',
        default_value='/camera/camera/color/image_raw',
        description='彩色图像话题'
    )
    
    depth_topic_arg = DeclareLaunchArgument(
        'depth_topic',
        default_value='/camera/camera/aligned_depth_to_color/image_raw',
        description='深度图像话题'
    )
    
    camera_info_topic_arg = DeclareLaunchArgument(
        'camera_info_topic',
        default_value='/camera/camera/color/camera_info',
        description='相机信息话题'
    )
    
    # 坐标系参数
    camera_frame_arg = DeclareLaunchArgument(
        'camera_frame',
        default_value='camera_color_optical_frame',
        description='相机光学坐标系frame'
    )
    
    base_frame_arg = DeclareLaunchArgument(
        'base_frame',
        default_value='link_base',
        description='机器人基座坐标系frame'
    )
    
    # YOLO参数
    yolo_model_arg = DeclareLaunchArgument(
        'yolo_model',
        default_value='yolov8s.pt',
        description='YOLO模型文件路径'
    )
    
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='检测置信度阈值'
    )
    
    # 允许检测的物体类别
    allowed_classes_arg = DeclareLaunchArgument(
        'allowed_classes',
        default_value="['person', 'cup', 'bottle', 'bowl']",
        description='允许检测的物体类别列表'
    )
    
    # 深度单位参数
    depth_scale_arg = DeclareLaunchArgument(
        'depth_scale',
        default_value='0.001',
        description='深度单位转换比例 (RealSense通常为0.001)'
    )
    
    # 标记参数
    marker_lifetime_arg = DeclareLaunchArgument(
        'marker_lifetime',
        default_value='3000.0',
        description='RViz标记持续时间（秒）'
    )
    
    use_base_frame_arg = DeclareLaunchArgument(
        'use_base_frame',
        default_value='true',
        description='是否优先使用基座坐标系显示标记'
    )

    # 桥接参数
    bridge_only_cup_arg = DeclareLaunchArgument(
        'bridge_only_cup',
        default_value='false',
        description='桥接节点是否仅转发杯子'
    )
    bridge_min_conf_arg = DeclareLaunchArgument(
        'bridge_min_confidence',
        default_value='0.3',
        description='桥接节点的最小置信度过滤阈值'
    )
    
    bridge_allowed_classes_arg = DeclareLaunchArgument(
        'bridge_allowed_classes',
        default_value="['cup', 'bowl', 'bottle']",
        description='桥接节点允许的物体类别'
    )
    
    # One-shot物体检测节点
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
            'verbose_logging': True,  # 启用详细日志以调试点云拟合
            'enable_6d_pose': True,   # 确保6D姿态估计已启用
        }],
        output='screen'
    )
    
    # 物体标记发布器节点
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

    # 检测→规划场景桥接节点
    detection_to_scene_node = Node(
        package='mtc_tutorial',
        executable='detection_to_planning_scene.py',
        name='detection_to_planning_scene',
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
        # 参数声明
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
        bridge_only_cup_arg,
        bridge_min_conf_arg,
        bridge_allowed_classes_arg,
        
        # 节点启动
        oneshot_detection_node,
        marker_publisher_node,
        detection_to_scene_node,
    ]) 