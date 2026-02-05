#!/usr/bin/env python3
"""
Spawn Demo Scene – inject collision objects into the MoveIt PlanningScene.

Reads a YAML file (default: config/demo_scene.yaml from this package) and
publishes CollisionObject messages so that objects appear in RViz and are
available for MTC planning.

No dependency on cameras, YOLO, Florence, or any perception pipeline.

Usage (standalone):
    ros2 run mtc_tutorial spawn_demo_scene.py
    ros2 run mtc_tutorial spawn_demo_scene.py --ros-args -p scene_file:=/path/to/scene.yaml

Usage (from launch file):
    Included automatically by plan_only_demo.launch.py
"""

import os
import sys
import time
import yaml

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy

from moveit_msgs.msg import CollisionObject, PlanningScene
from shape_msgs.msg import SolidPrimitive
from geometry_msgs.msg import Pose
from std_msgs.msg import ColorRGBA


class SpawnDemoScene(Node):
    def __init__(self):
        super().__init__('spawn_demo_scene')

        # ---------- parameters ----------
        # Default scene file: <mtc_tutorial_share>/config/demo_scene.yaml
        try:
            from ament_index_python.packages import get_package_share_directory
            default_scene = os.path.join(
                get_package_share_directory('mtc_tutorial'),
                'config', 'demo_scene.yaml',
            )
        except Exception:
            default_scene = ''

        self.declare_parameter('scene_file', default_scene)
        self.declare_parameter('startup_delay', 5.0)
        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('republish_interval', 0.0)  # 0 = publish once

        self.scene_file = self.get_parameter('scene_file').value
        self.startup_delay = self.get_parameter('startup_delay').value
        self.frame_id = self.get_parameter('frame_id').value
        self.republish_interval = self.get_parameter('republish_interval').value

        # ---------- publisher ----------
        latching_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.scene_pub = self.create_publisher(PlanningScene, '/planning_scene', latching_qos)
        self.color_pub = self.create_publisher(
            PlanningScene, '/planning_scene', latching_qos)

        self.get_logger().info(f'Scene file : {self.scene_file}')
        self.get_logger().info(f'Startup delay: {self.startup_delay:.1f}s')

        # Wait for move_group (gives MoveIt time to start)
        self.get_logger().info('Waiting for MoveIt to initialise...')
        self.timer = self.create_timer(self.startup_delay, self._on_startup)

    # ------------------------------------------------------------------ #
    def _on_startup(self):
        """Called once after the startup delay."""
        self.timer.cancel()
        self._publish_scene()

        if self.republish_interval > 0:
            self.get_logger().info(
                f'Will republish every {self.republish_interval:.1f}s')
            self.create_timer(self.republish_interval, self._publish_scene)
        else:
            self.get_logger().info('Scene published. Node stays alive for latched topic.')

    # ------------------------------------------------------------------ #
    def _publish_scene(self):
        """Load YAML and publish PlanningScene with CollisionObjects."""
        if not self.scene_file or not os.path.isfile(self.scene_file):
            self.get_logger().error(f'Scene file not found: {self.scene_file}')
            return

        with open(self.scene_file, 'r') as f:
            data = yaml.safe_load(f)

        objects_data = data.get('objects', [])
        if not objects_data:
            self.get_logger().warn('No objects defined in scene file.')
            return

        scene_msg = PlanningScene()
        scene_msg.is_diff = True

        for obj in objects_data:
            co = self._make_collision_object(obj)
            if co is not None:
                scene_msg.world.collision_objects.append(co)

                # Set object colour via object_colors
                rgba = obj.get('color', [0.5, 0.5, 0.5, 1.0])
                oc = PlanningScene().object_colors  # just for type hint
                color_msg = ColorRGBA()
                color_msg.r = float(rgba[0])
                color_msg.g = float(rgba[1])
                color_msg.b = float(rgba[2])
                color_msg.a = float(rgba[3]) if len(rgba) > 3 else 1.0
                # PlanningScene uses moveit_msgs/ObjectColor
                from moveit_msgs.msg import ObjectColor
                oc_msg = ObjectColor()
                oc_msg.id = co.id
                oc_msg.color = color_msg
                scene_msg.object_colors.append(oc_msg)

                self.get_logger().info(
                    f'  + {co.id:12s}  type={obj["type"]:8s}  '
                    f'pos=({obj["position"][0]:.3f}, {obj["position"][1]:.3f}, {obj["position"][2]:.3f})')

        self.scene_pub.publish(scene_msg)
        self.get_logger().info(
            f'Published {len(scene_msg.world.collision_objects)} collision objects.')

    # ------------------------------------------------------------------ #
    def _make_collision_object(self, obj: dict) -> CollisionObject:
        """Convert a YAML dict entry into a CollisionObject message."""
        co = CollisionObject()
        co.header.frame_id = self.frame_id
        co.id = obj['id']
        co.operation = CollisionObject.ADD

        primitive = SolidPrimitive()
        obj_type = obj.get('type', 'box')
        dims = obj.get('dimensions', [0.05, 0.05, 0.05])

        if obj_type == 'box':
            primitive.type = SolidPrimitive.BOX
            primitive.dimensions = [float(d) for d in dims[:3]]
        elif obj_type == 'cylinder':
            primitive.type = SolidPrimitive.CYLINDER
            # YAML: [radius, height]  ->  MoveIt: [height, radius]
            if len(dims) >= 2:
                primitive.dimensions = [float(dims[1]), float(dims[0])]
            else:
                primitive.dimensions = [0.1, 0.03]
        elif obj_type == 'sphere':
            primitive.type = SolidPrimitive.SPHERE
            primitive.dimensions = [float(dims[0])]
        else:
            self.get_logger().warn(f'Unknown primitive type "{obj_type}" for {obj["id"]}')
            return None

        pose = Pose()
        pos = obj.get('position', [0, 0, 0])
        pose.position.x = float(pos[0])
        pose.position.y = float(pos[1])
        pose.position.z = float(pos[2])
        ori = obj.get('orientation', [0, 0, 0, 1])
        pose.orientation.x = float(ori[0])
        pose.orientation.y = float(ori[1])
        pose.orientation.z = float(ori[2])
        pose.orientation.w = float(ori[3])

        co.primitives.append(primitive)
        co.primitive_poses.append(pose)
        return co


def main(args=None):
    rclpy.init(args=args)
    node = SpawnDemoScene()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
