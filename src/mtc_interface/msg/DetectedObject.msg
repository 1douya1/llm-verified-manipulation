# 单个检测物体的信息
string class_name                     # 物体类别名称
float32 confidence                    # 检测置信度

# 2D边界框信息
int32 bbox_x1                         # 边界框左上角x坐标
int32 bbox_y1                         # 边界框左上角y坐标  
int32 bbox_x2                         # 边界框右下角x坐标
int32 bbox_y2                         # 边界框右下角y坐标

# 3D信息 - 相机坐标系
geometry_msgs/Point position_camera   # 在相机坐标系下的3D位置
geometry_msgs/Vector3 size_3d         # 3D尺寸 (width, height, depth)
float32 volume_3d                     # 3D体积

# 3D信息 - 基座坐标系
geometry_msgs/Point position_base     # 在基座坐标系下的3D位置
bool transform_valid                  # 坐标转换是否有效

# 6D姿态信息 - 基座坐标系
geometry_msgs/Quaternion orientation_base    # 在基座坐标系下的姿态（四元数）
bool orientation_valid                       # 姿态估计是否有效

# 从点云拟合得到的真实几何尺寸
float32 fitted_height                        # 拟合的圆柱高度（米）
float32 fitted_radius                        # 拟合的圆柱半径（米）
bool geometry_fitted                         # 是否成功拟合几何体
float32 fit_quality                          # 拟合质量（inlier_ratio，0.0-1.0） 