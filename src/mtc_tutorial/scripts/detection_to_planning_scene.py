#!/usr/bin/env python3
"""
检测→规划场景桥接节点
订阅 object_detection_result,将检测到的杯子批量写入MoveIt规划场景（多杯子支持）。
"""

import sys
import os
from typing import List

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from mtc_interface.msg import DetectionResult

# 便于直接导入同包脚本
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.append(_THIS_DIR)

from ros_client_tools import setup_planning_scene  # type: ignore


class DetectionToPlanningScene(Node):
    def __init__(self):
        super().__init__('detection_to_planning_scene')

        # 参数
        self.declare_parameter('topic', 'object_detection_result')
        self.declare_parameter('only_cup', False)
        self.declare_parameter('allowed_classes', ['cup', 'bowl', 'bottle'])
        self.declare_parameter('min_confidence', 0.3)
        self.declare_parameter('apply_timeout', 10.0)
        self.declare_parameter('log_added', True)

        self.topic = self.get_parameter('topic').value
        self.only_cup = bool(self.get_parameter('only_cup').value)
        self.allowed_classes = self.get_parameter('allowed_classes').value
        self.min_conf = float(self.get_parameter('min_confidence').value)
        self.apply_timeout = float(self.get_parameter('apply_timeout').value)
        self.log_added = bool(self.get_parameter('log_added').value)

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=1
        )

        self.sub = self.create_subscription(
            DetectionResult,
            self.topic,
            self.detection_callback,
            qos
        )

        self.get_logger().info(f"Bridge started. Subscribing: {self.topic}, only_cup={self.only_cup}, allowed_classes={self.allowed_classes}, min_conf={self.min_conf:.2f}")

    def _filter_objects(self, msg: DetectionResult) -> DetectionResult:
        # 复制消息并按需过滤，保留指定类别和置信度阈值的对象
        if not self.only_cup and self.min_conf <= 0.0 and len(self.allowed_classes) == 0:
            return msg
        filtered = DetectionResult()
        filtered.header = msg.header
        filtered.camera_fx = msg.camera_fx
        filtered.camera_fy = msg.camera_fy
        filtered.camera_cx = msg.camera_cx
        filtered.camera_cy = msg.camera_cy
        filtered.camera_frame = msg.camera_frame
        filtered.base_frame = msg.base_frame
        filtered.transform_available = msg.transform_available
        filtered.processing_time = msg.processing_time

        for o in msg.objects:
            # 类别过滤：只保留allowed_classes中的类别（除非only_cup为True时只保留cup）
            if self.only_cup:
                if o.class_name != 'cup':
                    continue
            else:
                if len(self.allowed_classes) > 0 and o.class_name not in self.allowed_classes:
                    continue
            # 置信度过滤
            if o.confidence < self.min_conf:
                continue
            filtered.objects.append(o)
        filtered.total_objects = len(filtered.objects)
        return filtered

    def detection_callback(self, msg: DetectionResult):
        try:
            filtered_msg = self._filter_objects(msg)
            if filtered_msg.total_objects == 0:
                self.get_logger().warn("No objects passed filter; skip scene update")
                return

            # 将 DetectionResult 直接传入，setup_planning_scene 内部会解析
            result = setup_planning_scene(
                detection_result=filtered_msg,
                only_cup=self.only_cup,  # 显式传递only_cup参数
                include_cup=False,
                include_bowl=True,
                include_bottle=True,
                add_no_go_wall=False,  # 禁用虚拟墙障碍物
                timeout_sec=self.apply_timeout
            )

            if self.log_added:
                if result.get('ok'):
                    self.get_logger().info(
                        f"Applied planning scene: cups={result.get('cup_count', 0)} {result.get('cup_ids', [])}, "
                        f"bowls={result.get('bowl_count', 0)} {result.get('bowl_ids', [])}, "
                        f"bottles={result.get('bottle_count', 0)} {result.get('bottle_ids', [])}"
                    )
                else:
                    self.get_logger().error(f"Scene apply failed: {result}")
        except Exception as e:
            self.get_logger().error(f"Bridge callback failed: {str(e)}")


def main(args=None):
    rclpy.init(args=args)
    try:
        node = DetectionToPlanningScene()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
