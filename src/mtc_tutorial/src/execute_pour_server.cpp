#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <mtc_interface/action/execute_pour.hpp>

#include <moveit/task_constructor/task.h>
#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <cmath>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <vector>
#include <map>
#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rclcpp/node.hpp>
#include <chrono>
#include <mtc_tutorial/pour_task_builder.hpp>
#include <optional>

namespace mtc = moveit::task_constructor;

using ExecutePour = mtc_interface::action::ExecutePour;
using GoalHandleEP = rclcpp_action::ServerGoalHandle<ExecutePour>;

class MTCPourServer : public rclcpp::Node {
public:
  MTCPourServer() : Node("execute_pour_server") {
    server_ = rclcpp_action::create_server<ExecutePour>(
      this, "execute_pour",
      std::bind(&MTCPourServer::handle_goal, this, std::placeholders::_1, std::placeholders::_2),
      std::bind(&MTCPourServer::handle_cancel, this, std::placeholders::_1),
      std::bind(&MTCPourServer::handle_accepted, this, std::placeholders::_1));

    // 订阅杯子位姿话题
    std::string cup_pose_topic = this->declare_parameter<std::string>("cup_pose_topic", "/cup_pose");
    sub_cup_pose_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
      cup_pose_topic, rclcpp::QoS(10),
      [this](const geometry_msgs::msg::PoseStamped& msg){ last_cup_pose_ = msg; });

    // 声明 cup_pose.* 参数，避免 set_parameter 抛出未声明异常
    this->declare_parameter<double>("cup_pose.x", 0.0);
    this->declare_parameter<double>("cup_pose.y", -0.55);
    this->declare_parameter<double>("cup_pose.z", 0.025);
    this->declare_parameter<double>("cup_pose.qx", 0.0);
    this->declare_parameter<double>("cup_pose.qy", 0.0);
    this->declare_parameter<double>("cup_pose.qz", 0.0);
    this->declare_parameter<double>("cup_pose.qw", 1.0);
    this->declare_parameter<bool>("cup_pose.valid", false);
    // 夹爪闭合比例
    this->declare_parameter<double>("gripper.close_ratio", 0.30);

    RCLCPP_INFO(get_logger(), "Action server [/execute_pour] ready; subscribing cup pose on [%s]", cup_pose_topic.c_str());
  }

private:
  rclcpp_action::Server<ExecutePour>::SharedPtr server_;
  std::atomic_bool cancel_requested_{false};
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr sub_cup_pose_;
  std::optional<geometry_msgs::msg::PoseStamped> last_cup_pose_;

  rclcpp_action::GoalResponse handle_goal(
    const rclcpp_action::GoalUUID&,
    std::shared_ptr<const ExecutePour::Goal> goal)
  {
    RCLCPP_INFO(get_logger(),
      "Goal: tilt %.1f->%.1f deg @%.2f deg/s, hold %.2fs, lift %.3fm, approach[%.3f, %.3f], plan_only=%s",
      goal->tilt_start_deg, goal->tilt_end_deg, goal->tilt_speed_deg_s,
      goal->pour_hold_sec, goal->lift_height, goal->approach_min, goal->approach_max,
      goal->plan_only ? "true":"false");
    cancel_requested_ = false;
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_cancel(std::shared_ptr<GoalHandleEP>) {
    cancel_requested_ = true;
    RCLCPP_WARN(get_logger(), "Cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_accepted(std::shared_ptr<GoalHandleEP> gh) {
    std::thread([this, gh]() {
      auto goal = gh->get_goal();
      auto feedback = std::make_shared<ExecutePour::Feedback>();
      auto result   = std::make_shared<ExecutePour::Result>();

      // 1) 将 Goal 映射为你的参数
      mtc_tutorial::PourTaskParams p{
        goal->tilt_start_deg, goal->tilt_end_deg, goal->tilt_speed_deg_s,
        goal->pour_hold_sec, goal->lift_height, goal->approach_min, goal->approach_max,
        goal->plan_only
      };

      // 1.5) 等待并写入 cup_pose 参数（供 pour_task_builder 使用）
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
      while (!last_cup_pose_.has_value() && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
      }
      if (last_cup_pose_) {
        const auto& ps = *last_cup_pose_;
        // 仅使用位置与姿态数值。假设 frame 已是 link_base（由上游节点处理）。
        this->set_parameter(rclcpp::Parameter("cup_pose.x", ps.pose.position.x));
        this->set_parameter(rclcpp::Parameter("cup_pose.y", ps.pose.position.y));
        this->set_parameter(rclcpp::Parameter("cup_pose.z", ps.pose.position.z));
        this->set_parameter(rclcpp::Parameter("cup_pose.qx", ps.pose.orientation.x));
        this->set_parameter(rclcpp::Parameter("cup_pose.qy", ps.pose.orientation.y));
        this->set_parameter(rclcpp::Parameter("cup_pose.qz", ps.pose.orientation.z));
        this->set_parameter(rclcpp::Parameter("cup_pose.qw", ps.pose.orientation.w));
        this->set_parameter(rclcpp::Parameter("cup_pose.valid", true));
        RCLCPP_INFO(this->get_logger(), "cup_pose injected: (%.3f, %.3f, %.3f)",
                    ps.pose.position.x, ps.pose.position.y, ps.pose.position.z);
      } else {
        this->set_parameter(rclcpp::Parameter("cup_pose.valid", false));
        RCLCPP_WARN(this->get_logger(), "No cup_pose received within timeout; using defaults in pour_task_builder");
      }

      // 2) 构建并运行 MTC（把“写死的常量”替换为 p.*）
      try {
        // 使用参数化版本构建任务
        auto node = this->shared_from_this();
        auto task = mtc_tutorial::build_pour_task(node, p);

        task.init();

        // 发布“planning”反馈
        feedback->stage = "planning"; feedback->progress = 0.1f; feedback->current_tilt_deg = p.tilt_start_deg;
        gh->publish_feedback(feedback);

        if (!task.plan(2)) {
          result->success = false;
          result->error_msg = "planning failed";
          gh->abort(result);
          return;
        }

        feedback->stage = "planned"; feedback->progress = 0.4f;
        gh->publish_feedback(feedback);

        if (cancel_requested_) {
          result->success = false; result->error_msg = "cancel before execute";
          gh->canceled(result); return;
        }

        if (!p.plan_only) {
          // 这里建议你把倾倒阶段的 JointInterpolation 速度/角度由 p.* 注入
          const auto& solution = *task.solutions().front();
          auto exec_res = task.execute(solution);
          if (exec_res.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
            result->success = false;
            result->error_msg = "execute failed code=" + std::to_string(exec_res.val);
            gh->abort(result); return;
          }
        }

        feedback->stage = "done"; feedback->progress = 1.0f; feedback->current_tilt_deg = p.tilt_end_deg;
        gh->publish_feedback(feedback);

        result->success = true; result->error_msg = ""; result->duration_sec = 0.0f;
        gh->succeed(result);
      } catch (const std::exception& e) {
        result->success = false; result->error_msg = e.what();
        gh->abort(result);
      }
    }).detach();
  }
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MTCPourServer>());
  rclcpp::shutdown();
  return 0;
}
