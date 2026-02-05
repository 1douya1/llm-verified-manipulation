#!/usr/bin/env python3
"""
物体标记发布器
将检测结果转换为RViz可视化标记
"""

import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point, Vector3
from std_msgs.msg import ColorRGBA
from mtc_interface.msg import DetectionResult

class ObjectMarkerPublisher(Node):
    def __init__(self):
        super().__init__('object_marker_publisher')
        
        # 参数
        self.declare_parameter('use_base_frame', True)
        self.declare_parameter('marker_lifetime', 30.0)  # 标记持续时间（秒）
        self.declare_parameter('marker_scale', 0.02)     # 标记大小
        
        self.use_base_frame = self.get_parameter('use_base_frame').value
        self.marker_lifetime = self.get_parameter('marker_lifetime').value
        self.marker_scale = self.get_parameter('marker_scale').value
        
        # 订阅检测结果
        self.detection_sub = self.create_subscription(
            DetectionResult,
            'object_detection_result',
            self.detection_callback,
            10
        )
        
        # 发布标记
        self.marker_pub = self.create_publisher(
            MarkerArray,
            'object_markers',
            10
        )
        
        # 颜色配置
        self.colors = {
            'person': ColorRGBA(r=0.0, g=1.0, b=0.0, a=0.8),    # 绿色
            'cup': ColorRGBA(r=1.0, g=0.0, b=0.0, a=0.8),       # 红色
            'bottle': ColorRGBA(r=0.0, g=1.0, b=1.0, a=0.8),    # 青色
            'bowl': ColorRGBA(r=1.0, g=0.0, b=1.0, a=0.8),      # 品红色
            'default': ColorRGBA(r=1.0, g=0.5, b=0.0, a=0.8)    # 橙色
        }
        
        # 杯子颜色变体
        self.cup_colors = [
            ColorRGBA(r=1.0, g=0.0, b=0.0, a=0.8),    # 红色
            ColorRGBA(r=1.0, g=1.0, b=0.0, a=0.8),    # 黄色
            ColorRGBA(r=1.0, g=0.0, b=1.0, a=0.8),    # 品红色
            ColorRGBA(r=0.0, g=1.0, b=1.0, a=0.8),    # 青色
            ColorRGBA(r=0.5, g=0.0, b=0.5, a=0.8),    # 紫色
            ColorRGBA(r=1.0, g=0.5, b=0.0, a=0.8),    # 橙色
        ]
        
        self.get_logger().info("物体标记发布器初始化完成")
        if self.use_base_frame:
            self.get_logger().info("使用基座坐标系发布标记 (单位: m)")
        else:
            self.get_logger().info("使用相机坐标系发布标记 (单位: m)")
    
    def detection_callback(self, msg):
        """检测结果回调"""
        self.get_logger().info(f"接收到检测结果: {msg.total_objects} 个物体")
        
        # 创建标记数组
        marker_array = MarkerArray()
        cup_counter = 0
        
        for i, obj in enumerate(msg.objects):
            # 决定使用哪个坐标系的位置
            if self.use_base_frame and obj.transform_valid and msg.transform_available:
                position = obj.position_base
                frame_id = msg.base_frame
                coord_info = "基座坐标系"
                self.get_logger().info(f"物体{i}: 使用基座坐标系(m) - X={position.x:.3f}, Y={position.y:.3f}, Z={position.z:.3f}")
            else:
                position = obj.position_camera
                frame_id = msg.camera_frame
                coord_info = "相机坐标系"
                self.get_logger().warn(f"物体{i}: 使用相机坐标系(m) (transform_valid={obj.transform_valid}, transform_available={msg.transform_available})")
                self.get_logger().info(f"物体{i}: 相机坐标(m) - X={position.x:.3f}, Y={position.y:.3f}, Z={position.z:.3f}")
            
            # 创建位置标记（球体）
            position_marker = self.create_position_marker(
                i * 3,  # ID
                position,
                obj.class_name,
                obj.confidence,
                frame_id,
                cup_counter if obj.class_name == 'cup' else -1
            )
            marker_array.markers.append(position_marker)
            
            # 创建边界框标记（立方体）
            bbox_marker = self.create_bbox_marker(
                i * 3 + 1,  # ID
                position,
                obj.size_3d,
                obj.class_name,
                frame_id,
                cup_counter if obj.class_name == 'cup' else -1
            )
            marker_array.markers.append(bbox_marker)
            
            # 创建文本标记
            text_marker = self.create_text_marker(
                i * 3 + 2,  # ID
                position,
                obj,
                frame_id,
                coord_info,
                cup_counter if obj.class_name == 'cup' else -1,
                i  # 添加物体索引用于偏移计算
            )
            marker_array.markers.append(text_marker)
            
            if obj.class_name == 'cup':
                cup_counter += 1
        
        # 发布标记
        self.marker_pub.publish(marker_array)
        self.get_logger().info(f"发布了 {len(marker_array.markers)} 个标记")
    
    def create_position_marker(self, marker_id, position, class_name, confidence, frame_id, cup_index=-1):
        """创建位置标记（球体）"""
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "object_positions"
        marker.id = marker_id
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        
        # 位置
        marker.pose.position.x = position.x
        marker.pose.position.y = position.y
        marker.pose.position.z = position.z
        marker.pose.orientation.w = 1.0
        
        # 大小 - 根据置信度调整大小
        base_scale = self.marker_scale * 1.5  # 稍微小一点的基础大小
        confidence_scale = 0.5 + 0.5 * confidence  # 根据置信度调整 (0.5-1.0)
        marker.scale.x = base_scale * confidence_scale
        marker.scale.y = base_scale * confidence_scale
        marker.scale.z = base_scale * confidence_scale
        
        # 颜色
        if class_name == 'cup' and cup_index >= 0:
            marker.color = self.cup_colors[cup_index % len(self.cup_colors)]
        else:
            marker.color = self.colors.get(class_name, self.colors['default'])
        
        # 透明度根据置信度调整
        marker.color.a = 0.4 + 0.4 * confidence  # 0.4 - 0.8
        
        # 生命周期
        marker.lifetime = rclpy.duration.Duration(seconds=self.marker_lifetime).to_msg()
        
        return marker
    
    def create_bbox_marker(self, marker_id, position, size_3d, class_name, frame_id, cup_index=-1):
        """创建边界框标记（立方体）"""
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "object_bboxes"
        marker.id = marker_id
        marker.type = Marker.CUBE
        marker.action = Marker.ADD
        
        # 位置
        marker.pose.position.x = position.x
        marker.pose.position.y = position.y
        marker.pose.position.z = position.z
        marker.pose.orientation.w = 1.0
        
        # 大小
        marker.scale.x = max(size_3d.x, 0.01)  # 避免零尺寸
        marker.scale.y = max(size_3d.y, 0.01)
        marker.scale.z = max(size_3d.z, 0.01)
        
        # 颜色
        if class_name == 'cup' and cup_index >= 0:
            marker.color = self.cup_colors[cup_index % len(self.cup_colors)]
        else:
            marker.color = self.colors.get(class_name, self.colors['default'])
        
        # 透明度 - 更低的透明度，不会太显眼
        marker.color.a = 0.15
        
        # 生命周期
        marker.lifetime = rclpy.duration.Duration(seconds=self.marker_lifetime).to_msg()
        
        return marker
    
    def create_text_marker(self, marker_id, position, obj, frame_id, coord_info, cup_index=-1, obj_index=0):
        """创建文本标记"""
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "object_labels"
        marker.id = marker_id
        marker.type = Marker.TEXT_VIEW_FACING
        marker.action = Marker.ADD
        
        # 位置（在物体上方，根据物体索引智能偏移避免重叠）
        text_offset_height = max(obj.size_3d.z / 2, 0.02) + 0.08  # 动态高度偏移
        
        # 根据物体索引添加不同的偏移，形成整齐的排列
        x_offset = (obj_index % 3 - 1) * 0.03  # -0.03, 0, 0.03 的循环偏移
        y_offset = (obj_index // 3) * 0.04     # 每3个物体增加Y偏移
        
        marker.pose.position.x = position.x + x_offset
        marker.pose.position.y = position.y + y_offset
        marker.pose.position.z = position.z + text_offset_height
        marker.pose.orientation.w = 1.0
        
        # 大小 - 更小的文字
        marker.scale.z = 0.025  # 稍微小一点的文字
        
        # 简化的文本内容
        display_name = obj.class_name
        if obj.class_name == 'cup' and cup_index >= 0:
            display_name = f"cup_{cup_index}"
        
        # 只显示关键信息：名称、置信度和坐标（更紧凑的格式）
        marker.text = f"{display_name} {obj.confidence:.2f}\n({position.x:.2f}, {position.y:.2f}, {position.z:.2f})"
        
        # 颜色
        marker.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)  # 白色文字
        
        # 生命周期
        marker.lifetime = rclpy.duration.Duration(seconds=self.marker_lifetime).to_msg()
        
        return marker

def main(args=None):
    rclpy.init(args=args)
    
    try:
        node = ObjectMarkerPublisher()
        node.get_logger().info("物体标记发布器运行中...")
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"节点运行出错: {e}")
    finally:
        rclpy.shutdown()

if __name__ == '__main__':
    main() 