#!/usr/bin/env python3
"""
Charuco位姿发布器 - 用于easy_handeye2手眼标定
基于charuco_calibration.py的检测逻辑，发布Charuco标定板的位姿到tf
"""

import numpy as np
import cv2
import yaml
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
# import tf_transformations  # 注释掉，因为numpy兼容性问题
from scipy.spatial.transform import Rotation

try:
    from cv_bridge import CvBridge
    CV_BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"cv_bridge导入失败: {e}")
    CV_BRIDGE_AVAILABLE = False

class CharucoPosePublisher(Node):
    def __init__(self):
        super().__init__('charuco_pose_publisher')
        
        # 参数声明
        self.declare_parameter('image_topic', '/camera/camera/color/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera/color/camera_info')
        self.declare_parameter('camera_frame', 'camera_color_optical_frame')
        self.declare_parameter('marker_frame', 'charuco_board')
        self.declare_parameter('calibration_file', 'realsense_calibration_opencv.yaml')
        self.declare_parameter('use_camera_info', True)  # 新增：是否使用camera_info
        self.declare_parameter('board_size_x', 7)
        self.declare_parameter('board_size_y', 9)
        self.declare_parameter('square_length', 0.025)  # 25mm
        self.declare_parameter('marker_length', 0.018)  # 18mm
        
        # 获取参数
        self.image_topic = self.get_parameter('image_topic').value
        self.camera_info_topic = self.get_parameter('camera_info_topic').value
        self.camera_frame = self.get_parameter('camera_frame').value
        self.marker_frame = self.get_parameter('marker_frame').value
        self.calibration_file = self.get_parameter('calibration_file').value
        self.use_camera_info = self.get_parameter('use_camera_info').value
        self.board_size_x = self.get_parameter('board_size_x').value
        self.board_size_y = self.get_parameter('board_size_y').value
        self.square_length = self.get_parameter('square_length').value
        self.marker_length = self.get_parameter('marker_length').value
        
        # 检查cv_bridge
        if not CV_BRIDGE_AVAILABLE:
            self.get_logger().error('cv_bridge不可用，无法启动节点')
            return
            
        self.bridge = CvBridge()
        
        # 初始化Charuco检测器
        self.setup_charuco_detector()
        
        # 相机内参标志
        self.camera_matrix = None
        self.dist_coeffs = None
        self.camera_info_received = False
        
        # TF广播器
        self.tf_broadcaster = TransformBroadcaster(self)
        
        # 订阅camera_info（如果启用）
        if self.use_camera_info:
            self.camera_info_sub = self.create_subscription(
                CameraInfo,
                self.camera_info_topic,
                self.camera_info_callback,
                10
            )
            self.get_logger().info(f'等待相机内参: {self.camera_info_topic}')
        else:
            # 加载标定文件
            self.load_camera_calibration()
        
        # 结果图像发布器
        self.result_image_publisher = self.create_publisher(
            Image,
            '/charuco/result',
            10
        )
        
        # 图像订阅
        self.image_subscription = self.create_subscription(
            Image,
            self.image_topic,
            self.image_callback,
            10
        )
        
        self.get_logger().info(f'Charuco位姿发布器已启动')
        self.get_logger().info(f'订阅话题: {self.image_topic}')
        self.get_logger().info(f'相机frame: {self.camera_frame}')
        self.get_logger().info(f'标记frame: {self.marker_frame}')
        
    def setup_charuco_detector(self):
        """设置Charuco检测器"""
        # 创建Aruco字典和Charuco板
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.charuco_board = cv2.aruco.CharucoBoard(
            (self.board_size_x, self.board_size_y),
            self.square_length,
            self.marker_length,
            self.aruco_dict
        )
        
        # 检测参数
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        
        # Charuco检测器（新API）
        try:
            self.charuco_params = cv2.aruco.CharucoParameters()
            self.charuco_detector = cv2.aruco.CharucoDetector(
                self.charuco_board, self.charuco_params, self.aruco_params
            )
            self.use_new_api = True
            self.get_logger().info("使用新版本Charuco API (OpenCV 4.7+)")
        except AttributeError:
            self.charuco_detector = None
            self.use_new_api = False
            self.get_logger().info("使用旧版本Charuco API")
    
    def camera_info_callback(self, msg):
        """从camera_info话题获取相机内参"""
        if not self.camera_info_received:
            # 提取相机内参矩阵
            self.camera_matrix = np.array(msg.k).reshape(3, 3)
            
            # 提取畸变系数
            self.dist_coeffs = np.array(msg.d)
            if len(self.dist_coeffs) < 5:
                # 补齐到5个系数
                self.dist_coeffs = np.pad(self.dist_coeffs, (0, 5 - len(self.dist_coeffs)))
            
            self.camera_info_received = True
            
            self.get_logger().info('✅ 相机内参已从camera_info获取')
            self.get_logger().info(f'   分辨率: {msg.width}x{msg.height}')
            self.get_logger().info(f'   fx={self.camera_matrix[0,0]:.2f}, fy={self.camera_matrix[1,1]:.2f}')
            self.get_logger().info(f'   cx={self.camera_matrix[0,2]:.2f}, cy={self.camera_matrix[1,2]:.2f}')
            
            # 取消订阅（只需要一次）
            self.destroy_subscription(self.camera_info_sub)
    
    def load_camera_calibration(self):
        """加载相机标定参数（从文件）"""
        try:
            with open(self.calibration_file, 'r') as f:
                calib_data = yaml.safe_load(f)
            
            # 读取相机内参和畸变系数
            self.camera_matrix = np.array(calib_data['camera_matrix'])
            self.dist_coeffs = np.array(calib_data['distortion_coefficients'])
            self.camera_info_received = True
            
            self.get_logger().info(f'📁 相机标定参数已从文件加载: {self.calibration_file}')
            self.get_logger().info(f'   相机内参:\n{self.camera_matrix}')
            
        except Exception as e:
            self.get_logger().error(f'❌ 无法加载相机标定文件 {self.calibration_file}: {e}')
            self.get_logger().error('使用默认值继续运行（精度可能较差）')
            # 使用默认值继续运行
            self.camera_matrix = np.array([[615.0, 0, 320.0],
                                         [0, 615.0, 240.0],
                                         [0, 0, 1.0]])
            self.dist_coeffs = np.zeros((5, 1))
            self.camera_info_received = True
            
    def interpolate_charuco_corners(self, marker_corners, marker_ids, image):
        """兼容不同版本OpenCV的Charuco角点插值方法"""
        if self.use_new_api and self.charuco_detector is not None:
            # 使用新版本API (OpenCV 4.7+)
            try:
                charuco_corners, charuco_ids, _, _ = self.charuco_detector.detectBoard(image)
                if charuco_corners is not None and charuco_ids is not None:
                    return len(charuco_corners), charuco_corners, charuco_ids
                else:
                    return 0, None, None
            except Exception as e:
                self.get_logger().debug(f"新API检测失败: {e}")
                return 0, None, None
        else:
            # 尝试旧版本API
            try:
                charuco_retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                    marker_corners, marker_ids, image, self.charuco_board
                )
                return charuco_retval, charuco_corners, charuco_ids
            except (AttributeError, TypeError):
                try:
                    charuco_retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                        marker_corners, marker_ids, image, self.charuco_board, 
                        cameraMatrix=None, distCoeffs=None
                    )
                    return charuco_retval, charuco_corners, charuco_ids
                except:
                    return 0, None, None

    def estimate_pose_charuco(self, charuco_corners, charuco_ids):
        """估计Charuco板的位姿"""
        try:
            # 使用新版本API
            if hasattr(cv2.aruco, 'estimatePoseCharucoBoard'):
                success, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
                    charuco_corners, charuco_ids, self.charuco_board,
                    self.camera_matrix, self.dist_coeffs, None, None
                )
            else:
                # 备用方法：使用solvePnP
                # 获取3D角点
                object_points = self.charuco_board.getChessboardCorners()[charuco_ids.flatten()]
                success, rvec, tvec = cv2.solvePnP(
                    object_points, charuco_corners, 
                    self.camera_matrix, self.dist_coeffs
                )
            
            return success, rvec, tvec
        except Exception as e:
            self.get_logger().debug(f"位姿估计失败: {e}")
            return False, None, None

    def image_callback(self, msg):
        """图像回调函数"""
        try:
            # 等待相机内参
            if not self.camera_info_received:
                return
            
            # 转换图像
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            result_image = cv_image.copy()  # 用于可视化的图像副本
            
            # 检测Aruco标记
            marker_corners, marker_ids, _ = self.detector.detectMarkers(gray)
            
            pose_detected = False
            charuco_corners_count = 0
            
            if marker_ids is not None and len(marker_ids) > 4:
                # 在图像上绘制检测到的Aruco标记
                cv2.aruco.drawDetectedMarkers(result_image, marker_corners, marker_ids)
                
                # 插值Charuco角点
                charuco_retval, charuco_corners, charuco_ids = self.interpolate_charuco_corners(
                    marker_corners, marker_ids, gray
                )
                charuco_corners_count = charuco_retval
                
                if charuco_retval > 8:  # 至少需要8个角点进行可靠的位姿估计
                    # 在图像上绘制Charuco角点
                    if charuco_corners is not None:
                        cv2.aruco.drawDetectedCornersCharuco(result_image, charuco_corners, charuco_ids)
                    
                    # 估计位姿
                    success, rvec, tvec = self.estimate_pose_charuco(charuco_corners, charuco_ids)
                    
                    if success:
                        pose_detected = True
                        # 发布TF变换
                        self.publish_transform(rvec, tvec, msg.header.stamp)
                        
                        # 在图像上绘制坐标轴（兼容不同OpenCV版本）
                        try:
                            cv2.aruco.drawAxis(result_image, self.camera_matrix, self.dist_coeffs, 
                                             rvec, tvec, self.square_length * 2)
                        except AttributeError:
                            # 对于某些OpenCV版本，使用cv2.drawFrameAxes
                            try:
                                cv2.drawFrameAxes(result_image, self.camera_matrix, self.dist_coeffs, 
                                                rvec, tvec, self.square_length * 2, 3)
                            except AttributeError:
                                # 如果都不可用，跳过坐标轴绘制
                                pass
                    else:
                        self.get_logger().debug("位姿估计失败")
                else:
                    self.get_logger().debug(f"角点数量不足: {charuco_retval}")
            else:
                self.get_logger().debug("未检测到足够的Aruco标记")
            
            # 在图像上添加状态文本
            status_text = f"Charuco Corners: {charuco_corners_count}"
            pose_text = f"Pose: {'OK' if pose_detected else 'FAILED'}"
            
            cv2.putText(result_image, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 255, 0) if charuco_corners_count > 8 else (0, 0, 255), 2)
            cv2.putText(result_image, pose_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 255, 0) if pose_detected else (0, 0, 255), 2)
            
            # 发布结果图像
            result_msg = self.bridge.cv2_to_imgmsg(result_image, 'bgr8')
            result_msg.header = msg.header
            self.result_image_publisher.publish(result_msg)
                
        except Exception as e:
            self.get_logger().error(f'图像处理错误: {e}')

    def publish_transform(self, rvec, tvec, timestamp):
        """发布TF变换"""
        try:
            # 创建变换消息
            transform = TransformStamped()
            transform.header.stamp = timestamp
            transform.header.frame_id = self.camera_frame
            transform.child_frame_id = self.marker_frame
            
            # 将旋转向量转换为旋转矩阵
            rotation_matrix, _ = cv2.Rodrigues(rvec)
            
            # ⚠️ 修复：直接使用OpenCV输出，不做额外转换
            # ROS的optical_frame和OpenCV的相机坐标系定义一致：
            # - X右, Y下, Z前（指向场景）
            # OpenCV的tvec和rvec已经在正确的坐标系中
            
            # 直接使用旋转矩阵转换为四元数
            r = Rotation.from_matrix(rotation_matrix)
            quaternion = r.as_quat()  # 返回 [x, y, z, w] 格式
            
            # 直接使用OpenCV的平移向量（无需翻转）
            transform.transform.translation.x = float(tvec[0][0])
            transform.transform.translation.y = float(tvec[1][0])  # 不翻转
            transform.transform.translation.z = float(tvec[2][0])  # 不翻转 - 修复Z负值问题！
            
            transform.transform.rotation.x = quaternion[0]
            transform.transform.rotation.y = quaternion[1]
            transform.transform.rotation.z = quaternion[2]
            transform.transform.rotation.w = quaternion[3]
            
            # 广播变换
            self.tf_broadcaster.sendTransform(transform)
            
        except Exception as e:
            self.get_logger().error(f'TF发布错误: {e}')

def main(args=None):
    rclpy.init(args=args)
    
    try:
        node = CharucoPosePublisher()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main() 