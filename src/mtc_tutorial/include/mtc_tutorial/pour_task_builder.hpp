#pragma once

#include <rclcpp/rclcpp.hpp>
#include <moveit/task_constructor/task.h>

namespace mtc_tutorial
{
struct PourTaskParams {
  double tilt_start_deg;
  double tilt_end_deg;
  double tilt_speed_deg_s;
  double pour_hold_sec;
  double lift_height;
  double approach_min;
  double approach_max;
  bool plan_only;
};

// 新的笛卡尔倾倒任务参数，支持目标位置控制
struct CartesianPourTaskParams {
  // 倾倒动作参数
  double tilt_start_deg;
  double tilt_end_deg;
  double tilt_speed_deg_s;
  double pour_hold_sec;
  bool plan_only;
  
  // 目标位置参数 (base_link坐标系)
  double target_x;
  double target_y;
  double target_z;
  
  // 可选：保持当前姿势还是使用指定姿势
  bool maintain_orientation;
  double target_roll;   // 仅在maintain_orientation=false时使用
  double target_pitch;  // 仅在maintain_orientation=false时使用
  double target_yaw;    // 仅在maintain_orientation=false时使用
};

// 从 /move_group 同步 robot_description / SRDF 至 node
void sync_robot_model_params(const rclcpp::Node::SharedPtr& node);

// 声明与同步一组关键 MoveIt 参数（规划管线/执行/kinematics/joint_limits），尽量从 /move_group 获取，失败则填充安全默认
void configure_moveit_params(const rclcpp::Node::SharedPtr& node);

// 基于参数构建倒水任务
moveit::task_constructor::Task build_pour_task(const rclcpp::Node::SharedPtr& node,
                                                const PourTaskParams& p);

// 基于参数构建笛卡尔倾倒任务（支持目标位置控制）
moveit::task_constructor::Task build_cartesian_pour_task(const rclcpp::Node::SharedPtr& node,
                                                        const CartesianPourTaskParams& p);
}  // namespace mtc_tutorial 