"""
坐标变换工具函数
"""
import numpy as np


def pixel_to_3d_baselink(x_pixel, y_pixel, depth_value, intrinsics, extrinsics):
    """
    将像素坐标和深度值转换为 baselink 坐标系下的 3D 坐标
    
    Args:
        x_pixel: 像素 x 坐标
        y_pixel: 像素 y 坐标
        depth_value: 深度值（米）
        intrinsics: 相机内参矩阵 (3x3)
        extrinsics: 外参矩阵 (4x4) T_base_cam
    
    Returns:
        numpy array: [x, y, z] 在 baselink 坐标系下的 3D 坐标
    """
    fx = intrinsics[0][0]
    fy = intrinsics[1][1]
    cx = intrinsics[0][2]
    cy = intrinsics[1][2]
    
    x_cam = (x_pixel - cx) * depth_value / fx
    y_cam = (y_pixel - cy) * depth_value / fy
    z_cam = depth_value
    
    p_cam = np.array([x_cam, y_cam, z_cam, 1.0])
    T_base_cam = np.array(extrinsics)
    p_base = T_base_cam @ p_cam
    
    return p_base[:3]
