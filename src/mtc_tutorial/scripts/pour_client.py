#!/usr/bin/env python3
import sys
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from mtc_interface.action import ExecutePour


class PourClient(Node):
    def __init__(self):
        super().__init__('pour_client')
        self._ac = ActionClient(self, ExecutePour, 'execute_pour')

    def send(self, **kw):
        goal = ExecutePour.Goal()
        goal.target_id = kw.get('target_id', '')
        goal.tilt_start_deg = float(kw.get('tilt_start_deg', 45.0))
        goal.tilt_end_deg = float(kw.get('tilt_end_deg', 120.0))
        goal.tilt_speed_deg_s = float(kw.get('tilt_speed_deg_s', 30.0))
        goal.pour_hold_sec = float(kw.get('pour_hold_sec', 2.0))
        goal.lift_height = float(kw.get('lift_height', 0.12))
        goal.approach_min = float(kw.get('approach_min', 0.05))
        goal.approach_max = float(kw.get('approach_max', 0.15))
        goal.plan_only = bool(kw.get('plan_only', False))

        self.get_logger().info(
            f"Send goal: tilt {goal.tilt_start_deg}->{goal.tilt_end_deg} deg @ {goal.tilt_speed_deg_s} deg/s, "
            f"hold {goal.pour_hold_sec}s, lift {goal.lift_height} m, approach[{goal.approach_min}, {goal.approach_max}], "
            f"plan_only={goal.plan_only}")

        if not self._ac.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Action server not available: /execute_pour')
            return None

        send_future = self._ac.send_goal_async(goal, feedback_callback=self._on_feedback)
        rclpy.spin_until_future_complete(self, send_future)
        gh = send_future.result()
        if gh is None:
            self.get_logger().error('Failed to get goal handle')
            return None
        if not gh.accepted:
            self.get_logger().warn('Goal rejected')
            return None

        self.get_logger().info('Goal accepted')
        res_future = gh.get_result_async()
        rclpy.spin_until_future_complete(self, res_future)
        res = res_future.result().result
        self.get_logger().info(f"Result: success={res.success}, duration={res.duration_sec:.3f}s, error='{res.error_msg}'")
        return res

    def _on_feedback(self, msg):
        fb = msg.feedback
        self.get_logger().info(f"[{fb.stage}] progress={fb.progress:.2f}, tilt={fb.current_tilt_deg:.1f}")


def main(argv=None):
    rclpy.init(args=argv)
    node = PourClient()
    try:
        # 默认先只规划
        node.send(
            tilt_start_deg=45,
            tilt_end_deg=120,
            tilt_speed_deg_s=25,
            pour_hold_sec=2.0,
            lift_height=0.12,
            approach_min=0.05,
            approach_max=0.12,
            plan_only=True,
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main(sys.argv) 