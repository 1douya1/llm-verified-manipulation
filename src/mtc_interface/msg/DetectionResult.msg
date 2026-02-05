# 完整的检测结果
std_msgs/Header header                      # 时间戳和坐标系信息

# 相机内参信息
float32 camera_fx                           # 相机焦距fx
float32 camera_fy                           # 相机焦距fy
float32 camera_cx                           # 相机主点cx
float32 camera_cy                           # 相机主点cy

# 转换信息
string camera_frame                         # 相机坐标系名称
string base_frame                           # 基座坐标系名称
bool transform_available                    # 手眼转换是否可用

# 检测到的物体列表
DetectedObject[] objects                    # 检测到的所有物体

# 统计信息
int32 total_objects                         # 检测到的物体总数
float32 processing_time                     # 处理时间（秒） 