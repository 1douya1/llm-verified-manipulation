#!/usr/bin/env python3
"""
Single-shot Object Detection Node
YOLO-based object detection with coordinate transformation to base frame (m units)
Run once and exit after detection and visualization
"""

import cv2
import numpy as np
import time
import os
from datetime import datetime
import threading
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import Point, Vector3, TransformStamped, PointStamped
from std_msgs.msg import Header
from tf2_ros import TransformListener, Buffer
from tf2_geometry_msgs import do_transform_point
import tf2_ros

try:
    from cv_bridge import CvBridge
    CV_BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"cv_bridge import failed: {e}")
    CV_BRIDGE_AVAILABLE = False

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError as e:
    print(f"YOLO import failed: {e}")
    YOLO_AVAILABLE = False

from mtc_interface.msg import DetectedObject, DetectionResult
from geometry_msgs.msg import Quaternion

# 导入点云拟合模块
try:
    from pointcloud_geometry_fitter import PointCloudGeometryFitter
    POINTCLOUD_FITTER_AVAILABLE = True
except ImportError as e:
    print(f"PointCloud fitter import failed: {e}")
    POINTCLOUD_FITTER_AVAILABLE = False

class SingleShotDetection(Node):
    def __init__(self):
        super().__init__('object_single_shot_detection')
        
        # Parameter declarations
        self.declare_parameter('color_topic', '/camera/camera/color/image_raw')
        self.declare_parameter('depth_topic', '/camera/camera/aligned_depth_to_color/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera/color/camera_info')
        self.declare_parameter('camera_frame', 'camera_color_optical_frame')
        self.declare_parameter('base_frame', 'link_base')
        self.declare_parameter('yolo_model', 'yolov8s.pt')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('bowl_confidence_threshold', 0.25)  # bowl阈值略降，提升稳定识别
        self.declare_parameter('depth_scale', 0.001)  # RealSense depth unit conversion
        self.declare_parameter('allowed_classes', ['person', 'cup', 'bottle', 'bowl', 'orange', 'apple'])
        self.declare_parameter('save_images', False)  # Save captured images
        self.declare_parameter('image_save_path', '/tmp/detection_results')  # Image save path
        self.declare_parameter('capture_timeout', 10.0)  # Capture timeout in seconds
        self.declare_parameter('scene_id_prefix', 'object')
        self.declare_parameter('max_detections', 50)  # 添加最大检测数量限制
        self.declare_parameter('verbose_logging', False)  # Control detailed logging output
        self.declare_parameter('display_scale', 1.5)  # UI: enlarge display window content
        self.declare_parameter('enable_display', True)  # 是否启用图像显示
        self.declare_parameter('simple_visualization', False)  # 超简化可视化模式（仅边界框）
        # 新参数：目标物体坐标显示开关
        self.declare_parameter('show_target_coordinates', True)  # 是否显示目标物体(cup/bowl/orange/apple)坐标
        # 兼容旧参数名（deprecated）
        self.declare_parameter('show_cup_coordinates', True)  # 兼容别名：建议改用 show_target_coordinates
        self.declare_parameter('enable_6d_pose', True)  # 是否启用6D姿态估计（点云拟合）
        self.declare_parameter('pose_quality_threshold', 0.6)  # 6D姿态拟合质量阈值
        
        # Get parameters
        self.color_topic = self.get_parameter('color_topic').value
        self.depth_topic = self.get_parameter('depth_topic').value
        self.camera_info_topic = self.get_parameter('camera_info_topic').value
        self.camera_frame = self.get_parameter('camera_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        self.yolo_model = self.get_parameter('yolo_model').value
        self.confidence_threshold = self.get_parameter('confidence_threshold').value
        self.bowl_confidence_threshold = self.get_parameter('bowl_confidence_threshold').value
        self.depth_scale = self.get_parameter('depth_scale').value
        self.allowed_classes = self.get_parameter('allowed_classes').value
        self.save_images = self.get_parameter('save_images').value
        self.image_save_path = self.get_parameter('image_save_path').value
        self.capture_timeout = self.get_parameter('capture_timeout').value
        self.scene_id_prefix = self.get_parameter('scene_id_prefix').value
        self.verbose_logging = self.get_parameter('verbose_logging').value
        self.display_scale = float(self.get_parameter('display_scale').value)
        self.max_detections = int(self.get_parameter('max_detections').value)  # 最大检测数量限制
        self.enable_display = self.get_parameter('enable_display').value
        self.simple_visualization = self.get_parameter('simple_visualization').value
        show_target_coordinates = bool(self.get_parameter('show_target_coordinates').value)
        show_cup_coordinates_legacy = bool(self.get_parameter('show_cup_coordinates').value)
        # 兼容策略：
        # - 默认优先使用新参数 show_target_coordinates
        # - 若用户仅设置了旧参数为 False（新参数保持默认 True），则沿用旧值并提示弃用
        if show_target_coordinates and (not show_cup_coordinates_legacy):
            self.show_target_coordinates = False
            self.get_logger().warn(
                "Parameter 'show_cup_coordinates' is deprecated. "
                "Please use 'show_target_coordinates' instead."
            )
        else:
            self.show_target_coordinates = show_target_coordinates
        self.enable_6d_pose = self.get_parameter('enable_6d_pose').value
        self.pose_quality_threshold = self.get_parameter('pose_quality_threshold').value
        
        # Create image save directory
        if self.save_images:
            os.makedirs(self.image_save_path, exist_ok=True)
            self.get_logger().info(f"Image save path: {self.image_save_path}")
        
        # Initialize components
        if not CV_BRIDGE_AVAILABLE:
            self.get_logger().error("cv_bridge not available, cannot process images")
            return
            
        if not YOLO_AVAILABLE:
            self.get_logger().error("YOLO not available, cannot perform object detection")
            return
            
        self.bridge = CvBridge()
        
        # Initialize YOLO model
        try:
            self.model = YOLO(self.yolo_model)
            self.get_logger().info(f"YOLO model loaded successfully: {self.yolo_model}")
        except Exception as e:
            self.get_logger().error(f"YOLO model loading failed: {e}")
            return
        
        # TF listener
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        # Initialize pointcloud fitter for 6D pose estimation
        self.pointcloud_fitter = None
        if self.enable_6d_pose and POINTCLOUD_FITTER_AVAILABLE:
            try:
                self.pointcloud_fitter = PointCloudGeometryFitter(logger=self.get_logger())
                if self.pointcloud_fitter.available:
                    self.get_logger().info("6D pose estimation enabled (Open3D + Scipy)")
                else:
                    self.get_logger().warn("6D pose estimation dependencies missing, falling back to basic method")
                    self.pointcloud_fitter = None
            except Exception as e:
                self.get_logger().warn(f"Failed to initialize pointcloud fitter: {e}")
                self.pointcloud_fitter = None
        else:
            if self.enable_6d_pose:
                self.get_logger().warn("6D pose estimation requested but pointcloud_fitter not available")
            else:
                self.get_logger().info("6D pose estimation disabled")
        
        # Camera intrinsics
        self.camera_matrix = None
        self.camera_info_received = False
        
        # Data capture state
        self.captured_color_image = None
        self.captured_depth_image = None
        self.capture_timestamp = None
        self.data_lock = threading.Lock()
        self.capture_complete = threading.Event()
        self.detection_finished = False
        
        # First capture flags for logging control
        self.first_color_captured = False
        self.first_depth_captured = False
        self.first_capture_complete = False
        
        # QoS configuration
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=1
        )
        
        # Subscribers
        self.color_sub = self.create_subscription(
            Image,
            self.color_topic,
            self.color_callback,
            qos_profile
        )
        
        self.depth_sub = self.create_subscription(
            Image,
            self.depth_topic,
            self.depth_callback,
            qos_profile
        )
        
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            self.camera_info_topic,
            self.camera_info_callback,
            qos_profile
        )
        
        # Publisher
        self.detection_pub = self.create_publisher(
            DetectionResult,
            'object_detection_result',
            10
        )
        
        # Color configurations
        self.colors = {
            'person': (0, 255, 0),      # Green
            'cup': (0, 0, 255),         # Red
            'bottle': (255, 255, 0),    # Cyan
            'bowl': (255, 0, 255),      # Magenta
            'orange': (0, 165, 255),    # Orange
            'apple': (0, 0, 200),       # Dark Red
            'default': (252, 119, 30)   # Orange
        }
        
        # Cup color variants
        self.cup_colors = [
            (0, 0, 255),      # Red
            (0, 205, 205),    # Yellow
            (255, 0, 255),    # Magenta
            (255, 255, 0),    # Cyan
            (128, 0, 128),    # Purple
            (0, 128, 255),    # Orange
        ]
        
        # Bottle color variants
        self.bottle_colors = [
            (255, 255, 0),    # Cyan (default bottle color)
            (0, 255, 255),    # Yellow
            (128, 255, 0),    # Lime
            (255, 128, 0),    # Orange
            (0, 255, 128),    # Spring Green
            (255, 0, 128),    # Deep Pink
        ]
        
        self.get_logger().info("Single-shot detection node initialized")
        self.get_logger().info(f"Listening to topics:")
        self.get_logger().info(f"  Color image: {self.color_topic}")
        self.get_logger().info(f"  Depth image: {self.depth_topic}")
        self.get_logger().info(f"  Camera info: {self.camera_info_topic}")
        self.get_logger().info(f"Coordinate transformation: {self.camera_frame} -> {self.base_frame} (m)")
        if not self.verbose_logging:
            self.get_logger().info("Verbose logging disabled - only essential messages will be shown")
        self.get_logger().info("Waiting for data capture...")
    
    def color_callback(self, msg):
        """Color image callback"""
        if self.detection_finished:
            return
            
        with self.data_lock:
            try:
                self.captured_color_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
                self.capture_timestamp = msg.header.stamp
                
                    
                self.check_capture_complete()
            except Exception as e:
                self.get_logger().error(f"Color image conversion failed: {e}")
    
    def depth_callback(self, msg):
        """Depth image callback"""
        if self.detection_finished:
            return
            
        with self.data_lock:
            try:
                self.captured_depth_image = self.bridge.imgmsg_to_cv2(msg, "16UC1")
                

                    
                self.check_capture_complete()
            except Exception as e:
                self.get_logger().error(f"Depth image conversion failed: {e}")
    
    def check_capture_complete(self):
        """Check if capture is complete"""
        if (self.captured_color_image is not None and 
            self.captured_depth_image is not None and 
            self.camera_info_received and 
            not self.detection_finished):
            
            self.capture_complete.set()
        
    
    def camera_info_callback(self, msg):
        """Camera info callback"""
        if not self.camera_info_received:
            self.camera_matrix = np.array(msg.k).reshape(3, 3)
            self.fx = self.camera_matrix[0, 0]
            self.fy = self.camera_matrix[1, 1]
            self.cx = self.camera_matrix[0, 2]
            self.cy = self.camera_matrix[1, 2]
            self.camera_info_received = True
            self.get_logger().info(f"Camera intrinsics received: fx={self.fx:.2f}, fy={self.fy:.2f}, cx={self.cx:.2f}, cy={self.cy:.2f}")
            
            # Check if capture can be completed
            with self.data_lock:
                self.check_capture_complete()
    
    def wait_for_data(self):
        """Wait for all required data"""
        self.get_logger().info("Waiting for camera data...")
        
        if self.capture_complete.wait(timeout=self.capture_timeout):
            self.get_logger().info("All data received successfully")
            return True
        else:
            self.get_logger().error(f"Data capture timeout ({self.capture_timeout}s)")
            
            # Log what's missing
            missing = []
            if self.captured_color_image is None:
                missing.append("color image")
            if self.captured_depth_image is None:
                missing.append("depth image")
            if not self.camera_info_received:
                missing.append("camera info")
                
            self.get_logger().error(f"Missing data: {', '.join(missing)}")
            return False
    
    def save_captured_images(self):
        """Save captured images"""
        try:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save color image
            color_filename = os.path.join(self.image_save_path, f"color_{timestamp_str}.jpg")
            cv2.imwrite(color_filename, self.captured_color_image)
            
            # Save depth image
            depth_filename = os.path.join(self.image_save_path, f"depth_{timestamp_str}.png")
            cv2.imwrite(depth_filename, self.captured_depth_image)
            
            self.get_logger().info(f"Images saved: {color_filename}, {depth_filename}")
            
        except Exception as e:
            self.get_logger().error(f"Failed to save images: {e}")
    
    def pixel_to_3d(self, x, y, depth):
        """Convert pixel coordinates to 3D coordinates (camera frame)"""
        if depth <= 0 or not self.camera_info_received:
            return None
            
        # Calculate offset from camera center
        x_offset = (x - self.cx) / self.fx
        y_offset = (y - self.cy) / self.fy
        
        # Calculate 3D coordinates (camera frame)
        z = depth * self.depth_scale  # Convert to meters
        x_3d = x_offset * z
        y_3d = y_offset * z
        
        return np.array([x_3d, y_3d, z])
    
    def get_object_3d_position(self, x1, y1, x2, y2, depth_image):
        """Get object's 3D position information"""
        # Calculate bounding box center
        center_x = int((x1 + x2) / 2)
        center_y = int((y1 + y2) / 2)
        
        # Extract depth ROI
        roi_depth = depth_image[y1:y2, x1:x2]
        
        # Filter invalid depth values
        valid_depths = roi_depth[roi_depth > 0]
        
        if len(valid_depths) == 0:
            return None
            
        # Use median depth value
        median_depth = np.median(valid_depths)
        
        # Convert to 3D coordinates
        position_3d = self.pixel_to_3d(center_x, center_y, median_depth)
        
        if position_3d is None:
            return None
        
        # Calculate object dimensions (camera frame)
        depth_meters = median_depth * self.depth_scale
        width_3d = (x2 - x1) * depth_meters / self.fx
        height_3d = (y2 - y1) * depth_meters / self.fy
        
        # Estimate depth (assume 50% of width)
        depth_3d = width_3d * 0.5
        
        # Calculate volume
        volume_3d = width_3d * height_3d * depth_3d
        
        return {
            'position': position_3d,
            'size_3d': (width_3d, height_3d, depth_3d),
            'volume_3d': volume_3d,
            'center_2d': (center_x, center_y)
        }
    
    def get_object_6d_pose(self, x1, y1, x2, y2, depth_image, color_image, mask=None):
        """
        获取物体的完整6D姿态（位置+朝向）和真实尺寸
        
        Args:
            x1, y1, x2, y2: 边界框坐标
            depth_image: 深度图像
            color_image: 彩色图像
            mask: 分割mask（可选，来自YOLO）
            
        Returns:
            包含6D姿态信息的字典，失败返回None
        """
        # 先调用原有方法获取基础3D信息（作为fallback）
        basic_3d = self.get_object_3d_position(x1, y1, x2, y2, depth_image)
        if basic_3d is None:
            return None
        
        # 如果没有启用6D姿态估计或拟合器不可用，返回基础信息
        if not self.enable_6d_pose or self.pointcloud_fitter is None:
            return {
                **basic_3d,
                'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0},
                'geometry_fitted': False
            }
        
        # 尝试点云拟合
        try:
            camera_intrinsics = {
                'fx': self.fx, 'fy': self.fy,
                'cx': self.cx, 'cy': self.cy
            }
            
            # 处理mask（如果有的话）
            mask_np = None
            if mask is not None:
                try:
                    # mask可能是torch tensor，需要转换为numpy
                    if hasattr(mask, 'cpu'):
                        mask_np = mask.cpu().numpy()
                    else:
                        mask_np = np.array(mask)
                    
                    # 确保mask是2D的
                    if len(mask_np.shape) > 2:
                        mask_np = mask_np.squeeze()
                    
                    # 确保mask大小与图像匹配
                    if mask_np.shape != depth_image.shape:
                        mask_np = cv2.resize(
                            mask_np.astype(np.uint8), 
                            (depth_image.shape[1], depth_image.shape[0]),
                            interpolation=cv2.INTER_NEAREST
                        ).astype(bool)
                except Exception as e:
                    if self.verbose_logging:
                        self.get_logger().warn(f"Failed to process mask: {e}")
                    mask_np = None
            
            fitted_result = self.pointcloud_fitter.fit_cylinder_6d_pose(
                depth_image, color_image, 
                bbox=(x1, y1, x2, y2),
                mask=mask_np,
                camera_intrinsics=camera_intrinsics,
                depth_scale=self.depth_scale,
                quality_threshold=self.pose_quality_threshold
            )
            
            if fitted_result and fitted_result.get('inlier_ratio', 0) > self.pose_quality_threshold:
                # 拟合成功，使用拟合结果
                # 注意：拟合结果的position是相机坐标系，需要后续转换到base
                return {
                    **basic_3d,  # 保留基础信息（作为备份）
                    'position': fitted_result['position'],  # 用拟合的位置替换
                    'orientation': fitted_result['orientation'],
                    'fitted_height': fitted_result['height'],
                    'fitted_radius': fitted_result['radius'],
                    'geometry_fitted': True,
                    'fit_quality': fitted_result['inlier_ratio']
                }
            else:
                if self.verbose_logging:
                    quality = fitted_result.get('inlier_ratio', 0) if fitted_result else 0
                    self.get_logger().warn(
                        f"Cylinder fitting quality too low: {quality:.2f} < {self.pose_quality_threshold}"
                    )
        except Exception as e:
            if self.verbose_logging:
                self.get_logger().warn(f"Cylinder fitting failed: {e}, using basic method")
        
        # 拟合失败，使用默认姿态
        return {
            **basic_3d,
            'orientation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0},
            'geometry_fitted': False
        }
    
    def transform_to_base_frame(self, point_camera):
        """Transform camera frame point to base frame (m units)"""
        try:
            # Lookup transform
            now = rclpy.time.Time()
            transform = self.tf_buffer.lookup_transform(
                self.base_frame,
                self.camera_frame,
                now,
                timeout=rclpy.duration.Duration(seconds=1.0)
            )
            
            # Create point message
            point_stamped = PointStamped()
            point_stamped.header.frame_id = self.camera_frame
            point_stamped.point.x = float(point_camera[0])
            point_stamped.point.y = float(point_camera[1])
            point_stamped.point.z = float(point_camera[2])
            
            # Transform coordinates
            transformed_point = do_transform_point(point_stamped, transform)
            
            # Return meters
            return np.array([
                transformed_point.point.x,
                transformed_point.point.y,
                transformed_point.point.z
            ]), True
            
        except Exception as e:
            self.get_logger().warn(f"Coordinate transformation failed: {e}")
            # If transformation fails, return camera coordinates in meters
            return point_camera, False
    
    def perform_detection(self):
        """Perform object detection"""
        start_time = time.time()
        
        with self.data_lock:
            color_image = self.captured_color_image.copy()
            depth_image = self.captured_depth_image.copy()
        
        # YOLO detection
        results = self.model(color_image)
        
        # Process detection results
        detected_objects = []
        cup_counter = 0
        bottle_counter = 0
        bowl_counter = 0
        
        # Check TF transform availability
        transform_available = False
        try:
            now = rclpy.time.Time()
            self.tf_buffer.lookup_transform(
                self.base_frame,
                self.camera_frame,
                now,
                timeout=rclpy.duration.Duration(seconds=0.1)
            )
            transform_available = True
            self.get_logger().info(f"Hand-eye transform available: {self.camera_frame} -> {self.base_frame}")
        except Exception as e:
            self.get_logger().warn(f"Hand-eye transform unavailable: {e}")
        
        accepted_index = 0  # for generating display IDs in the same order as message
        detection_stopped_early = False
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
                
            for box in boxes:
                # 应用最大检测数量限制
                if accepted_index >= self.max_detections:
                    self.get_logger().warn(f"达到最大检测数量限制 {self.max_detections}，停止处理更多物体")
                    detection_stopped_early = True
                    break
                
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                confidence = box.conf[0].cpu().numpy()
                class_id = box.cls[0].cpu().numpy()
                
                # Per-class threshold (bowl may use a lower threshold)
                class_name = self.model.names[int(class_id)]
                if class_name == 'bowl':
                    threshold = float(self.bowl_confidence_threshold)
                    if self.verbose_logging:
                        self.get_logger().info(f"检测到bowl，置信度={confidence:.3f}，阈值={threshold:.3f}")
                else:
                    threshold = float(self.confidence_threshold)
                
                if confidence < threshold:
                    if self.verbose_logging:
                        self.get_logger().debug(f"跳过 {class_name} (置信度{confidence:.3f} < 阈值{threshold:.3f})")
                    continue
                
                # Only process specified classes
                if class_name not in self.allowed_classes:
                    continue
                
                # Get 6D pose information (position + orientation + size)
                # Extract mask if available
                box_mask = None
                if hasattr(result, 'masks') and result.masks is not None:
                    try:
                        masks_data = result.masks.data
                        if len(masks_data) > 0:
                            # Get the mask corresponding to this box
                            box_idx = list(boxes).index(box)
                            if box_idx < len(masks_data):
                                box_mask = masks_data[box_idx]
                    except Exception as e:
                        if self.verbose_logging:
                            self.get_logger().warn(f"Failed to extract mask: {e}")
                
                object_3d = self.get_object_6d_pose(
                    x1, y1, x2, y2, 
                    depth_image, color_image,
                    mask=box_mask
                )
                
                if object_3d is not None:
                    # Transform to base frame (m units)
                    position_base_m, transform_valid = self.transform_to_base_frame(object_3d['position'])
                    
                    # Create detected object message
                    detected_obj = DetectedObject()
                    detected_obj.class_name = class_name
                    detected_obj.confidence = float(confidence)
                    
                    # 2D bounding box
                    detected_obj.bbox_x1 = int(x1)
                    detected_obj.bbox_y1 = int(y1)
                    detected_obj.bbox_x2 = int(x2)
                    detected_obj.bbox_y2 = int(y2)
                    
                    # 3D information in camera frame (meters)
                    detected_obj.position_camera = Point()
                    detected_obj.position_camera.x = float(object_3d['position'][0])
                    detected_obj.position_camera.y = float(object_3d['position'][1])
                    detected_obj.position_camera.z = float(object_3d['position'][2])
                    
                    detected_obj.size_3d = Vector3()
                    detected_obj.size_3d.x = float(object_3d['size_3d'][0])
                    detected_obj.size_3d.y = float(object_3d['size_3d'][1])
                    detected_obj.size_3d.z = float(object_3d['size_3d'][2])
                    
                    detected_obj.volume_3d = float(object_3d['volume_3d'])
                    
                    # 3D information in base frame (meters)
                    detected_obj.position_base = Point()
                    detected_obj.position_base.x = float(position_base_m[0])
                    detected_obj.position_base.y = float(position_base_m[1])
                    detected_obj.position_base.z = float(position_base_m[2])
                    
                    detected_obj.transform_valid = transform_valid and transform_available
                    
                    # 新增：填充6D姿态信息
                    if 'orientation' in object_3d:
                        detected_obj.orientation_base = Quaternion()
                        detected_obj.orientation_base.x = float(object_3d['orientation']['x'])
                        detected_obj.orientation_base.y = float(object_3d['orientation']['y'])
                        detected_obj.orientation_base.z = float(object_3d['orientation']['z'])
                        detected_obj.orientation_base.w = float(object_3d['orientation']['w'])
                        detected_obj.orientation_valid = object_3d.get('geometry_fitted', False)
                    else:
                        detected_obj.orientation_base = Quaternion()
                        detected_obj.orientation_base.w = 1.0
                        detected_obj.orientation_valid = False
                    
                    # 新增：填充真实尺寸信息
                    detected_obj.fitted_height = float(object_3d.get('fitted_height', 0.0))
                    detected_obj.fitted_radius = float(object_3d.get('fitted_radius', 0.0))
                    detected_obj.geometry_fitted = object_3d.get('geometry_fitted', False)
                    detected_obj.fit_quality = float(object_3d.get('fit_quality', 0.0))
                    
                    # 如果成功拟合几何，记录日志
                    if detected_obj.geometry_fitted and self.verbose_logging:
                        self.get_logger().info(
                            f"{class_name} geometry fitted: "
                            f"h={detected_obj.fitted_height:.3f}m, "
                            f"r={detected_obj.fitted_radius:.3f}m, "
                            f"quality={detected_obj.fit_quality:.2%}"
                        )
                    
                    detected_objects.append(detected_obj)
                    # ID consistent with planning scene generator order: object, object_2, ...
                    accepted_index += 1
                    display_id = self.scene_id_prefix if accepted_index == 1 else f"{self.scene_id_prefix}_{accepted_index}"
                    
                    # Print detection information (show base frame only to reduce clutter)
                    self.print_detection_info(detected_obj, display_id)
                    
                    # Count objects by type
                    if class_name == 'cup':
                        cup_counter += 1
                    elif class_name == 'bottle':
                        bottle_counter += 1
                    elif class_name == 'bowl':
                        bowl_counter += 1
                
                if detection_stopped_early:
                    break
        
        # Create detection result message
        detection_result = DetectionResult()
        detection_result.header = Header()
        detection_result.header.stamp = self.get_clock().now().to_msg()
        detection_result.header.frame_id = self.camera_frame
        
        # Camera intrinsics
        detection_result.camera_fx = float(self.fx)
        detection_result.camera_fy = float(self.fy)
        detection_result.camera_cx = float(self.cx)
        detection_result.camera_cy = float(self.cy)
        
        # Coordinate frame information
        detection_result.camera_frame = self.camera_frame
        detection_result.base_frame = self.base_frame
        detection_result.transform_available = transform_available
        
        # Detection results
        detection_result.objects = detected_objects
        detection_result.total_objects = len(detected_objects)
        detection_result.processing_time = float(time.time() - start_time)
        
        # Log detection statistics by type
        type_stats = []
        if cup_counter > 0:
            type_stats.append(f"cups={cup_counter}")
        if bottle_counter > 0:
            type_stats.append(f"bottles={bottle_counter}")
        if bowl_counter > 0:
            type_stats.append(f"bowls={bowl_counter}")
        
        stats_str = f" ({', '.join(type_stats)})" if type_stats else ""
        limit_str = f", 限制到{self.max_detections}个" if detection_stopped_early else ""
        self.get_logger().info(f"Detection completed: Found {len(detected_objects)} objects{stats_str}{limit_str}, processing time: {detection_result.processing_time:.3f}s")
        
        return detection_result, color_image
    
    def print_detection_info(self, obj, display_id: str = ""):
        """Print detection information - base frame only for readability"""
        display_name = f"{obj.class_name}"
        id_line = f"  ID: {display_id}" if display_id else None
         
        self.get_logger().info(f"=== {display_name.upper()} (Confidence: {obj.confidence:.2f}) ===")
        self.get_logger().info(f"  2D BBox: ({obj.bbox_x1}, {obj.bbox_y1}) -> ({obj.bbox_x2}, {obj.bbox_y2})")
        if id_line:
            self.get_logger().info(id_line)
        
        if obj.transform_valid:
            self.get_logger().info(f"  Base Coord(m): X={obj.position_base.x:.3f}, Y={obj.position_base.y:.3f}, Z={obj.position_base.z:.3f}")
        else:
            self.get_logger().warn(f"  Base Coord(m): Transform failed or unavailable")
        
        # 显示拟合状态和质量
        if obj.geometry_fitted:
            quality_emoji = "🟢" if obj.fit_quality >= 0.8 else ("🟡" if obj.fit_quality >= 0.6 else "🔴")
            self.get_logger().info(f"  {quality_emoji} 点云拟合: 成功 (质量: {obj.fit_quality:.2%})")
            self.get_logger().info(f"  拟合尺寸(m): 高度={obj.fitted_height:.3f}, 半径={obj.fitted_radius:.3f}")
        else:
            self.get_logger().warn(f"  ⚠️  点云拟合: 失败或跳过 (使用边界框估计)")
            
        self.get_logger().info(f"  3D Size(m): W={obj.size_3d.x:.3f}, H={obj.size_3d.y:.3f}, D={obj.size_3d.z:.3f}")
        self.get_logger().info(f"  Volume(m³): {obj.volume_3d:.6f}")
    
    def collect_target_coordinates(self, detection_result, target_classes=None):
        """收集指定类别物体的link_base坐标信息
        
        Args:
            detection_result: DetectionResult消息
            
        Returns:
            list: 包含目标物体坐标信息的字典列表
        """
        if target_classes is None:
            target_classes = {'cup', 'bowl', 'orange', 'apple'}

        object_coordinates = []
        class_counters = {}
        
        for obj in detection_result.objects:
            if obj.class_name in target_classes:
                class_counters[obj.class_name] = class_counters.get(obj.class_name, 0) + 1
                class_idx = class_counters[obj.class_name]
                display_id = f"{obj.class_name}_{class_idx}" if class_idx > 1 else obj.class_name
                
                coord_info = {
                    "id": display_id,
                    "confidence": float(obj.confidence),
                    "transform_valid": bool(obj.transform_valid),
                }
                
                if obj.transform_valid:
                    coord_info.update({
                        "x": float(obj.position_base.x),
                        "y": float(obj.position_base.y), 
                        "z": float(obj.position_base.z),
                        "coordinates_text": f"X={obj.position_base.x:.3f}, Y={obj.position_base.y:.3f}, Z={obj.position_base.z:.3f}"
                    })
                else:
                    coord_info.update({
                        "x": None,
                        "y": None,
                        "z": None,
                        "coordinates_text": "坐标转换失败"
                    })
                
                coord_info["class_name"] = obj.class_name
                object_coordinates.append(coord_info)
        
        return object_coordinates
    
    def collect_cup_coordinates(self, detection_result):
        """向后兼容接口：仅收集cup坐标信息"""
        return self.collect_target_coordinates(detection_result, target_classes={'cup'})

    def print_target_coordinates_summary(self, detection_result, target_classes=None):
        """打印目标物体坐标信息总结"""
        target_coords = self.collect_target_coordinates(
            detection_result, target_classes=target_classes
        )
        
        if target_coords:
            self.get_logger().info("=" * 50)
            self.get_logger().info("📍 检测到的目标物体坐标总结 (link_base坐标系)")
            self.get_logger().info("=" * 50)
            
            for i, obj in enumerate(target_coords, 1):
                self.get_logger().info(f"{obj['class_name']} #{i} (ID: {obj['id']}):")
                self.get_logger().info(f"  置信度: {obj['confidence']:.3f}")
                if obj['transform_valid']:
                    self.get_logger().info(f"  坐标: {obj['coordinates_text']}")
                    self.get_logger().info(f"  可用于机器人规划: ✅")
                else:
                    self.get_logger().info(f"  坐标: {obj['coordinates_text']}")
                    self.get_logger().info(f"  可用于机器人规划: ❌")
                self.get_logger().info("")
            
            self.get_logger().info("=" * 50)
        else:
            self.get_logger().info("📍 未检测到任何目标物体")
        
        return target_coords

    def print_cup_coordinates_summary(self, detection_result):
        """向后兼容接口：仅打印cup坐标总结"""
        return self.print_target_coordinates_summary(detection_result, target_classes={'cup'})
    
    def visualize_results(self, color_image, detection_result):
        """Visualize detection results with clearer, non-overlapping labels"""
        try:
            self.get_logger().info(f"开始可视化检测结果，检测到 {detection_result.total_objects} 个物体")
            
            vis_image = color_image.copy()
            cup_counter = 0
            bottle_counter = 0
            
            # 🚀 超简化模式：仅绘制边界框，跳过所有标签处理
            if self.simple_visualization:
                self.get_logger().info("🚀 使用超简化可视化模式（仅边界框）")
                
                # 收集目标物体（cup/bowl/orange/apple）坐标信息用于显示
                target_coords_info = []
                
                for i, obj in enumerate(detection_result.objects[:self.max_detections]):
                    if obj.class_name == 'cup':
                        color = (0, 0, 255)  # 红色
                    elif obj.class_name == 'bottle':
                        color = (255, 255, 0)  # 青色
                    elif obj.class_name == 'bowl':
                        color = (255, 0, 255)  # 品红色
                    elif obj.class_name == 'orange':
                        color = (0, 165, 255)  # 橙色
                    elif obj.class_name == 'apple':
                        color = (0, 0, 200)  # 深红色
                    else:
                        color = (0, 255, 0)  # 绿色

                    if obj.class_name in ('cup', 'bowl', 'orange', 'apple'):
                        if obj.transform_valid:
                            coord_info = (
                                f"{obj.class_name}({i+1}): X={obj.position_base.x:.3f}, "
                                f"Y={obj.position_base.y:.3f}, Z={obj.position_base.z:.3f}"
                            )
                            target_coords_info.append(coord_info)
                            self.get_logger().info(f"📍 {coord_info}")
                        else:
                            coord_info = f"{obj.class_name}({i+1}): Transform failed"
                            target_coords_info.append(coord_info)
                            self.get_logger().warn(f"⚠️ {coord_info}")
                    
                    # 只绘制边界框，无标签
                    cv2.rectangle(vis_image, (obj.bbox_x1, obj.bbox_y1), (obj.bbox_x2, obj.bbox_y2), color, 3)
                
                # 简单统计（包含目标物体坐标信息）
                stats_text = f"Objects: {min(len(detection_result.objects), self.max_detections)}"
                cv2.putText(vis_image, stats_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                
                # 在图像上显示目标物体坐标信息
                if target_coords_info:
                    y_offset = 70  # 起始Y位置
                    for i, coord_text in enumerate(target_coords_info[:5]):  # 最多显示5个目标物体坐标
                        cv2.putText(vis_image, coord_text, (10, y_offset + i * 25), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                
                # 直接显示，跳过复杂处理
                if self.enable_display:
                    try:
                        cv2.imshow("Simple Detection View", vis_image)
                        cv2.waitKey(0)
                        cv2.destroyAllWindows()
                        self.get_logger().info("✅ 超简化显示成功")
                        
                        # 在日志中再次总结目标物体坐标
                        if target_coords_info:
                            self.get_logger().info("📍 检测到的目标物体坐标总结(link_base):")
                            for coord_info in target_coords_info:
                                self.get_logger().info(f"   {coord_info}")
                        
                    except Exception as e:
                        self.get_logger().error(f"❌ 超简化显示也失败: {e}")
                return
            
            # 检查是否有检测结果
            if detection_result.total_objects == 0:
                self.get_logger().warn("没有检测到任何物体，将显示原始图像")
                # 在图像上添加"无检测结果"文本
                h, w = vis_image.shape[:2]
                cv2.rectangle(vis_image, (10, h - 80), (400, h - 10), (0, 0, 0), -1)
                cv2.putText(vis_image, "No objects detected", (15, h - 45), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            # 🚀 大幅简化的标签绘制 - 最小化复杂度
            accepted_index = 0
            for obj in detection_result.objects:
                # 防止处理过多物体
                if accepted_index >= self.max_detections:
                    break
                
                # 选择颜色（简化）
                if obj.class_name == 'cup':
                    color = self.cup_colors[cup_counter % len(self.cup_colors)]
                    cup_counter += 1
                elif obj.class_name == 'bottle':
                    color = self.bottle_colors[bottle_counter % len(self.bottle_colors)]
                    bottle_counter += 1
                else:
                    color = self.colors.get(obj.class_name, self.colors['default'])
                
                # 绘制边界框
                cv2.rectangle(vis_image, (obj.bbox_x1, obj.bbox_y1), (obj.bbox_x2, obj.bbox_y2), color, 2)
                
                # 🎯 极简标签：只显示类别和ID，放在框的左上角
                accepted_index += 1
                display_id = self.scene_id_prefix if accepted_index == 1 else f"{self.scene_id_prefix}_{accepted_index}"
                
                # 拟合质量指示器
                fit_indicator = ""
                if obj.geometry_fitted:
                    # 使用ASCII字符代替emoji，兼容性更好
                    if obj.fit_quality >= 0.8:
                        fit_indicator = "[FIT:GOOD]"
                    elif obj.fit_quality >= 0.6:
                        fit_indicator = "[FIT:OK]"
                    else:
                        fit_indicator = "[FIT:LOW]"
                
                # 根据物体类型添加不同的标签信息
                if obj.class_name in ('cup', 'bowl', 'orange', 'apple'):
                    # 关键目标物体：可选是否在标签中显示坐标
                    if self.show_target_coordinates:
                        if obj.transform_valid:
                            simple_label = f"{obj.class_name}_{display_id} {fit_indicator} (X:{obj.position_base.x:.3f},Y:{obj.position_base.y:.3f},Z:{obj.position_base.z:.3f})"
                            # 同时在日志中输出坐标
                            self.get_logger().info(
                                f"📍 {obj.class_name}坐标 {display_id}: "
                                f"X={obj.position_base.x:.3f}, Y={obj.position_base.y:.3f}, Z={obj.position_base.z:.3f}"
                            )
                        else:
                            simple_label = f"{obj.class_name}_{display_id} {fit_indicator} (坐标转换失败)"
                            self.get_logger().warn(f"⚠️ {obj.class_name} {display_id}: 坐标转换失败")
                    else:
                        simple_label = f"{obj.class_name}_{display_id} {fit_indicator}"
                else:
                    # 其他物体显示类别、ID和拟合状态
                    simple_label = f"{obj.class_name}_{display_id} {fit_indicator}"
                
                # 简单定位：固定在边界框左上角偏移处，不做重叠检测
                label_x = max(5, obj.bbox_x1)
                label_y = max(20, obj.bbox_y1 - 5)

                # orange/apple/bowl 使用更大字号和同类颜色背景，提升可读性
                emphasized = obj.class_name in ("orange", "apple", "bowl")
                label_font_scale = 0.68 if emphasized else 0.48
                label_thickness = 2 if emphasized else 1
                label_pad = 4 if emphasized else 2
                label_bg = color if emphasized else (0, 0, 0)

                (text_w, text_h), baseline = cv2.getTextSize(
                    simple_label, cv2.FONT_HERSHEY_SIMPLEX, label_font_scale, label_thickness
                )
                cv2.rectangle(
                    vis_image,
                    (label_x - label_pad, label_y - text_h - baseline - label_pad),
                    (label_x + text_w + label_pad, label_y + label_pad),
                    label_bg,
                    -1,
                )

                # 绘制白色文字（抗锯齿）
                cv2.putText(
                    vis_image,
                    simple_label,
                    (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    label_font_scale,
                    (255, 255, 255),
                    label_thickness,
                    cv2.LINE_AA,
                )
            
            # 🚀 极简统计信息
            simple_stats = f"Objects: {accepted_index}"
            h, w = vis_image.shape[:2]
            stats_x, stats_y = 10, h - 22
            # 左下角统计文字放大并加描边，提升清晰度
            cv2.putText(
                vis_image,
                simple_stats,
                (stats_x, stats_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis_image,
                simple_stats,
                (stats_x, stats_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            
            self.get_logger().info(f"🎨 简化可视化完成: 显示 {accepted_index}/{detection_result.total_objects} 个物体")
            
            # Save visualization result
            if self.save_images:
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                result_filename = os.path.join(self.image_save_path, f"detection_result_{timestamp_str}.jpg")
                cv2.imwrite(result_filename, vis_image)
                self.get_logger().info(f"Detection result saved: {result_filename}")
            
            # 🚀 简化显示：取消复杂的缩放操作
            
            # Display image with minimal processing
            if self.enable_display:
                try:
                    self.get_logger().info("📸 准备显示检测结果图像...")
                    cv2.namedWindow("Detection Results", cv2.WINDOW_AUTOSIZE)  # 简化窗口类型
                    cv2.imshow("Detection Results", vis_image)  # 直接显示，不缩放
                    self.get_logger().info("✅ Detection results displayed. Press any key to close...")
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                    self.get_logger().info("🔒 图像窗口已关闭")
                except Exception as display_error:
                    self.get_logger().error(f"❌ 图像显示失败: {display_error}")
                    # 🆘 最后的备用方案：尝试最简单的显示
                    try:
                        cv2.imshow("Simple View", color_image)  # 显示原图
                        cv2.waitKey(1000)  # 等1秒自动关闭
                        cv2.destroyAllWindows()
                        self.get_logger().info("🆘 备用显示模式成功")
                    except:
                        self.get_logger().error("💥 所有显示方式都失败了")
            else:
                self.get_logger().info("⏭️ 图像显示已禁用，跳过可视化步骤")
                
        except Exception as viz_error:
            self.get_logger().error(f"可视化过程发生错误: {viz_error}")
            # 即使可视化失败，也尝试显示原始图像
            if self.enable_display:
                try:
                    cv2.imshow("Original Image (Visualization Failed)", color_image)
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                except:
                    self.get_logger().error("连原始图像都无法显示，请检查系统环境")
            else:
                self.get_logger().warn("图像显示已禁用，跳过可视化步骤。")
    
    def run_detection(self):
        """Run single detection cycle"""
        self.get_logger().info("Starting single-shot object detection...")
        
        # Wait for all required data
        if not self.wait_for_data():
            self.get_logger().error("Failed to capture required data")
            return False
        
        # Save images if enabled
        if self.save_images:
            self.save_captured_images()
        
        # Perform detection
        try:
            self.get_logger().info("开始执行物体检测...")
            detection_result, color_image = self.perform_detection()
            
            # 检查检测结果
            if detection_result is None:
                self.get_logger().error("检测结果为空")
                return False
            
            if color_image is None:
                self.get_logger().error("彩色图像为空")
                return False
            
            # Publish results
            self.detection_pub.publish(detection_result)
            self.get_logger().info("Detection results published")
            
            # 📍 输出目标物体（cup/bowl/orange/apple）坐标信息总结（如果启用）
            if self.show_target_coordinates:
                target_coords = self.print_target_coordinates_summary(detection_result)
            else:
                target_coords = self.collect_target_coordinates(detection_result)  # 仅收集，不打印详细信息
                if target_coords:
                    self.get_logger().info(
                        f"📍 检测到 {len(target_coords)} 个目标物体(cup/bowl/orange/apple)，"
                        "使用 show_target_coordinates=true 查看详细坐标"
                    )
            
            # Visualize results - 添加额外检查
            if self.enable_display:
                self.get_logger().info("准备进行可视化...")
            else:
                self.get_logger().info("跳过可视化步骤（显示已禁用）")
            
            self.visualize_results(color_image, detection_result)
            
            self.detection_finished = True
            return True
            
        except Exception as e:
            self.get_logger().error(f"Detection process failed: {e}")
            import traceback
            self.get_logger().error(f"详细错误信息: {traceback.format_exc()}")
            return False


def main(args=None):
    rclpy.init(args=args)
    
    try:
        node = SingleShotDetection()
        
        # Check critical components
        if not CV_BRIDGE_AVAILABLE or not YOLO_AVAILABLE:
            node.get_logger().error("Critical components unavailable, node cannot run properly")
            return
        
        # Run detection in a separate thread to allow ROS callbacks
        detection_thread = threading.Thread(target=node.run_detection)
        detection_thread.daemon = True
        detection_thread.start()
        
        # Spin until detection is finished
        while rclpy.ok() and not node.detection_finished:
            rclpy.spin_once(node, timeout_sec=0.1)
        
        # Wait for detection thread to complete - 增加等待时间
        detection_thread.join(timeout=10.0)  # 从1秒增加到10秒
        
        if node.detection_finished:
            node.get_logger().info("Detection completed successfully!")
        else:
            node.get_logger().error("Detection did not complete")
            node.get_logger().warn("可能原因：GUI环境问题、数据获取超时、或检测过程异常")
            
    except KeyboardInterrupt:
        print("Detection interrupted by user")
    except Exception as e:
        print(f"Node execution failed: {e}")
    finally:
        cv2.destroyAllWindows()
        rclpy.shutdown()


if __name__ == '__main__':
    main()