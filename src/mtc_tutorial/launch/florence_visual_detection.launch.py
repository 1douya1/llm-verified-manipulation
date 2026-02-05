#!/usr/bin/env python3
"""
Florence-2 Visual Detection Launch File
仅启动可视化检测节点，用于测试和查看检测效果
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Florence-2 服务参数
    detector_url_arg = DeclareLaunchArgument(
        'detector_url',
        default_value='http://localhost:4399',
        description='Florence-2 检测服务 URL'
    )
    
    target_objects_arg = DeclareLaunchArgument(
        'target_objects',
        default_value="['cup', 'bottle', 'bowl']",
        description='要检测的目标物体列表'
    )
    
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
    
    # 检测参数
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.5',
        description='检测置信度阈值'
    )
    
    # 可视化参数
    enable_display_arg = DeclareLaunchArgument(
        'enable_display',
        default_value='true',
        description='是否启用 OpenCV 可视化窗口'
    )
    
    display_scale_arg = DeclareLaunchArgument(
        'display_scale',
        default_value='1.0',
        description='显示窗口缩放比例'
    )
    
    box_thickness_arg = DeclareLaunchArgument(
        'box_thickness',
        default_value='2',
        description='边界框线条粗细'
    )
    
    font_scale_arg = DeclareLaunchArgument(
        'font_scale',
        default_value='0.6',
        description='标签字体大小'
    )
    
    show_3d_coords_arg = DeclareLaunchArgument(
        'show_3d_coords',
        default_value='true',
        description='是否在标签中显示3D坐标'
    )
    
    # 外参矩阵加载方式参数
    use_tf_extrinsics_arg = DeclareLaunchArgument(
        'use_tf_extrinsics',
        default_value='false',  # 默认使用静态参数（eye-in-hand场景）
        description='是否使用TF获取外参（false则使用静态参数）'
    )
    
    # 静态外参参数（从标定文件uf850_rs_on_hand_calibration.calib中提取）
    # 注意：数组参数在 launch 文件中需要作为字符串传递，节点会自动解析
    static_extrinsics_translation_arg = DeclareLaunchArgument(
        'static_extrinsics_translation',
        default_value='[0.06637719970480799, -0.032133912794949385, 0.02259679892714925]',
        description='默认UF850手眼标定文件中的静态外参平移 [x, y, z]（T_ee_cam的translation）'
    )
    
    static_extrinsics_rotation_arg = DeclareLaunchArgument(
        'static_extrinsics_rotation',
        default_value='[0.0013075170827278532, -0.0024892917521336377, 0.7106597907015502, 0.7035302095188808]',
        description='默认UF850手眼标定文件中的静态外参旋转四元数 [x, y, z, w]（T_ee_cam的rotation）'
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
        # 参数声明
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
        
        # 节点启动
        florence_visual_node,
    ])

