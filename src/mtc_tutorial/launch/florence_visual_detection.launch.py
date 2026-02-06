#!/usr/bin/env python3
"""
Florence-2 Visual Detection Launch File
Only launches visual detection node for testing and viewing detection results
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Florence-2 service parameters
    detector_url_arg = DeclareLaunchArgument(
        'detector_url',
        default_value='http://localhost:4399',
        description='Florence-2 detection service URL'
    )
    
    target_objects_arg = DeclareLaunchArgument(
        'target_objects',
        default_value="['cup', 'bottle', 'bowl']",
        description='Target object list for detection'
    )
    
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
    
    # Detection parameters
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='Detection confidence threshold'
    )
    
    # Visualization parameters
    enable_display_arg = DeclareLaunchArgument(
        'enable_display',
        default_value='true',
        description='Whether to enable OpenCV visualization window'
    )
    
    display_scale_arg = DeclareLaunchArgument(
        'display_scale',
        default_value='1.0',
        description='Display window scale ratio'
    )
    
    box_thickness_arg = DeclareLaunchArgument(
        'box_thickness',
        default_value='2',
        description='Bounding box line thickness'
    )
    
    font_scale_arg = DeclareLaunchArgument(
        'font_scale',
        default_value='0.6',
        description='Label font size'
    )
    
    show_3d_coords_arg = DeclareLaunchArgument(
        'show_3d_coords',
        default_value='true',
        description='Whether to show 3D coordinates in labels'
    )
    
    # Extrinsics matrix loading method parameter
    use_tf_extrinsics_arg = DeclareLaunchArgument(
        'use_tf_extrinsics',
        default_value='false',  # Default use static parameters (eye-in-hand scenario)
        description='Whether to use TF for extrinsics (false uses static parameters)'
    )
    
    # Static extrinsics parameters (extracted from calibration file uf850_rs_on_hand_calibration.calib)
    # Note: array parameters need to be passed as strings in launch files, nodes will auto-parse
    static_extrinsics_translation_arg = DeclareLaunchArgument(
        'static_extrinsics_translation',
        default_value='[0.06637719970480799, -0.032133912794949385, 0.02259679892714925]',
        description='Static extrinsics translation from default UF850 hand-eye calibration file [x, y, z] (T_ee_cam translation)'
    )
    
    static_extrinsics_rotation_arg = DeclareLaunchArgument(
        'static_extrinsics_rotation',
        default_value='[0.0013075170827278532, -0.0024892917521336377, 0.7106597907015502, 0.7035302095188808]',
        description='Static extrinsics rotation quaternion from default UF850 hand-eye calibration file [x, y, z, w] (T_ee_cam rotation)'
    )
    
    # Florence-2 可视化检测节点
    florence_visual_node = Node(
        package='mtc_tutorial',
        executable='object_florence_visual_detection.py',
        name='florence_visual_detection',
        parameters=[{
            'detector_url': LaunchConfiguration('detector_url'),
            'target_objects': LaunchConfiguration('target_objects'),
            'color_topic': LaunchConfiguration('color_topic'),
            'depth_topic': LaunchConfiguration('depth_topic'),
            'camera_info_topic': LaunchConfiguration('camera_info_topic'),
            'camera_frame': LaunchConfiguration('camera_frame'),
            'base_frame': LaunchConfiguration('base_frame'),
            'confidence_threshold': LaunchConfiguration('confidence_threshold'),
            'enable_display': LaunchConfiguration('enable_display'),
            'display_scale': LaunchConfiguration('display_scale'),
            'box_thickness': LaunchConfiguration('box_thickness'),
            'font_scale': LaunchConfiguration('font_scale'),
            'show_3d_coords': LaunchConfiguration('show_3d_coords'),
            'use_tf_extrinsics': LaunchConfiguration('use_tf_extrinsics'),
            'static_extrinsics_translation': LaunchConfiguration('static_extrinsics_translation'),
            'static_extrinsics_rotation': LaunchConfiguration('static_extrinsics_rotation'),
        }],
        output='screen'
    )
    
    return LaunchDescription([
        # Parameter declarations
        detector_url_arg,
        target_objects_arg,
        color_topic_arg,
        depth_topic_arg,
        camera_info_topic_arg,
        camera_frame_arg,
        base_frame_arg,
        confidence_threshold_arg,
        enable_display_arg,
        display_scale_arg,
        box_thickness_arg,
        font_scale_arg,
        show_3d_coords_arg,
        use_tf_extrinsics_arg,
        static_extrinsics_translation_arg,
        static_extrinsics_rotation_arg,
        
        # Node launch
        florence_visual_node,
    ])

