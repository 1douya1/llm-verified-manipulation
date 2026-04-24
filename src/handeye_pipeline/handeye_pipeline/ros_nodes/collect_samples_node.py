"""ROS2 node for collecting robot TF plus ChArUco board detections."""

from __future__ import annotations

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from std_srvs.srv import SetBool
from tf2_ros import Buffer, TransformListener

from cv_bridge import CvBridge

from handeye_pipeline.charuco_detector import CharucoDetector
from handeye_pipeline.config import load_config
from handeye_pipeline.sample_io import append_sample, make_sample


def _ros_transform_to_dict(transform_stamped):
    t = transform_stamped.transform.translation
    q = transform_stamped.transform.rotation
    return {
        "translation": [float(t.x), float(t.y), float(t.z)],
        "rotation": [float(q.x), float(q.y), float(q.z), float(q.w)],
    }


class CollectSamplesNode(Node):
    def __init__(self):
        super().__init__("handeye_collect_samples")
        self.declare_parameter("config", "")
        self.declare_parameter("sample_file", "")
        self.declare_parameter("min_corners", 8)

        config_path = self.get_parameter("config").value
        if not config_path:
            raise RuntimeError("Parameter 'config' is required")
        self.config = load_config(config_path)
        self.sample_file = self.get_parameter("sample_file").value or self.config.output.sample_file
        self.min_corners = int(self.get_parameter("min_corners").value)

        self.bridge = CvBridge()
        self.camera_intrinsics = None
        self.save_next_valid_detection = False
        self.detector = CharucoDetector(self.config.board)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.create_subscription(CameraInfo, self.config.camera.camera_info_topic, self.camera_info_callback, 10)
        self.create_subscription(Image, self.config.camera.rgb_topic, self.image_callback, 10)
        self.create_service(SetBool, "save_sample", self.save_sample_callback)

        self.get_logger().info(f"Collecting samples into: {self.sample_file}")
        self.get_logger().info(f"Trigger with: ros2 service call /save_sample std_srvs/srv/SetBool '{{data: true}}'")

    def camera_info_callback(self, msg: CameraInfo) -> None:
        self.camera_intrinsics = {
            "camera_matrix": list(msg.k),
            "distortion_coefficients": list(msg.d),
        }

    def save_sample_callback(self, request, response):
        self.save_next_valid_detection = bool(request.data)
        response.success = True
        response.message = "Will save next valid ChArUco detection" if request.data else "Save request cleared"
        return response

    def image_callback(self, msg: Image) -> None:
        if self.camera_intrinsics is None:
            self.get_logger().debug("Waiting for camera_info")
            return

        image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        detection = self.detector.detect(image, self.camera_intrinsics, min_corners=self.min_corners)
        if not detection.detected:
            self.get_logger().debug(detection.message)
            return
        if not self.save_next_valid_detection:
            return

        try:
            robot_tf = self.tf_buffer.lookup_transform(
                self.config.robot.base_frame,
                self.config.robot.ee_frame,
                Time(),
                timeout=Duration(seconds=0.5),
            )
        except Exception as exc:
            self.get_logger().warn(f"Cannot look up robot TF: {exc}")
            return

        sample = make_sample(
            _ros_transform_to_dict(robot_tf),
            detection.transform_camera_board,
            {
                "robot_base": self.config.robot.base_frame,
                "robot_ee": self.config.robot.ee_frame,
                "camera_optical": self.config.camera.optical_frame,
                "calibration_board": self.config.board.frame,
            },
            timestamp=str(msg.header.stamp.sec) + "." + str(msg.header.stamp.nanosec).zfill(9),
            detection_quality=detection.quality,
        )
        append_sample(self.sample_file, sample)
        self.save_next_valid_detection = False
        self.get_logger().info(
            f"Saved {sample['id']} with {detection.num_corners} corners to {self.sample_file}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = CollectSamplesNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
