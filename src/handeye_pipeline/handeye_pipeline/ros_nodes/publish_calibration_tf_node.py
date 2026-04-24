"""ROS2 static TF publisher for solved hand-eye calibration YAML."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import StaticTransformBroadcaster

from handeye_pipeline.tf_export import load_result_yaml


class PublishCalibrationTfNode(Node):
    def __init__(self):
        super().__init__("handeye_publish_calibration_tf")
        self.declare_parameter("result_file", "")
        self.declare_parameter("parent_frame", "")
        self.declare_parameter("child_frame", "")

        result_file = self.get_parameter("result_file").value
        if not result_file:
            raise RuntimeError("Parameter 'result_file' is required")
        result = load_result_yaml(result_file)
        parent = self.get_parameter("parent_frame").value or result.get("parent_frame")
        child = self.get_parameter("child_frame").value or result.get("child_frame")
        if not parent or not child:
            raise RuntimeError("parent_frame and child_frame must be provided by params or result YAML")

        transform = result["transform"]
        msg = TransformStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = parent
        msg.child_frame_id = child
        msg.transform.translation.x = float(transform["translation"][0])
        msg.transform.translation.y = float(transform["translation"][1])
        msg.transform.translation.z = float(transform["translation"][2])
        msg.transform.rotation.x = float(transform["rotation"][0])
        msg.transform.rotation.y = float(transform["rotation"][1])
        msg.transform.rotation.z = float(transform["rotation"][2])
        msg.transform.rotation.w = float(transform["rotation"][3])

        self.broadcaster = StaticTransformBroadcaster(self)
        self.broadcaster.sendTransform(msg)
        self.get_logger().info(f"Publishing static TF {parent} -> {child} from {result_file}")


def main(args=None):
    rclpy.init(args=args)
    node = PublishCalibrationTfNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
