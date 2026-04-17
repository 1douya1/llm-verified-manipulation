#!/usr/bin/env python3
"""
Print the camera<->robot extrinsic transforms that are currently being
broadcast on /tf and /tf_static.

Useful when you want to confirm:
  * easy_handeye2 (or your static_transform_publisher) is publishing
    the link you expect (camera_color_optical_frame, link_eef, etc.).
  * The translation / rotation roughly matches what configs/handeye_*.yaml
    contains.

Run with the workspace sourced AND with the publisher already running:

    source install/setup.bash
    python3 scripts/diagnostics/handeye_transform_viewer.py \
        --base link_base \
        --camera camera_color_optical_frame

Pass --once to print a single snapshot and exit. Default polls every 1 s.
"""

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener, TransformException


def fmt_transform(tf):
    t = tf.transform.translation
    r = tf.transform.rotation
    return (
        f"  translation: x={t.x:+.4f} y={t.y:+.4f} z={t.z:+.4f}\n"
        f"  rotation:    x={r.x:+.4f} y={r.y:+.4f} z={r.z:+.4f} w={r.w:+.4f}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='link_base',
                        help='Base / parent frame (default: link_base).')
    parser.add_argument('--camera', default='camera_color_optical_frame',
                        help='Camera / child frame (default: camera_color_optical_frame).')
    parser.add_argument('--ee', default='link_eef',
                        help='End-effector frame for cross-check (default: link_eef).')
    parser.add_argument('--once', action='store_true',
                        help='Print one snapshot and exit.')
    parser.add_argument('--rate', type=float, default=1.0,
                        help='Poll rate in Hz when not --once (default: 1.0).')
    args = parser.parse_args()

    rclpy.init()
    node = Node('handeye_transform_viewer')
    buf = Buffer()
    TransformListener(buf, node)

    try:
        period = 1.0 / max(args.rate, 0.1)
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            print('=' * 60)
            print(f'Snapshot @ {time.strftime("%H:%M:%S")}')
            print('=' * 60)
            for parent, child, label in (
                (args.base, args.camera, 'base -> camera'),
                (args.base, args.ee, 'base -> ee'),
                (args.ee, args.camera, 'ee -> camera (eye-in-hand)'),
            ):
                try:
                    tf = buf.lookup_transform(parent, child, rclpy.time.Time())
                    print(f'\n{label}  ({parent} -> {child}):')
                    print(fmt_transform(tf))
                except TransformException as e:
                    print(f'\n{label}  ({parent} -> {child}): NOT AVAILABLE')
                    print(f'  ({e})')
            print()
            if args.once:
                break
            time.sleep(period)
    except KeyboardInterrupt:
        print('\nInterrupted.')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
