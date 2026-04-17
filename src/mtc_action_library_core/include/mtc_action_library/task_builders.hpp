#pragma once

#include <moveit/task_constructor/task.h>
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <optional>
#include <map>
#include "action_params.hpp"

namespace mtc_action_library {

// 抓取任务参数
struct PickTaskParams {
  // 目标物体位置
  double source_x = 0.0;
  double source_y = -0.4; 
  double source_z = 0.13;
  double source_qx = 0.0;
  double source_qy = 0.0;
  double source_qz = 0.0;
  double source_qw = 1.0;
  
  // 抓取提示
  double approach_min = 0.05;
  double approach_max = 0.15;
  double lift_height = 0.12;
  double safe_approach_height = 0.18;
  
  // 其他选项
  bool plan_only = false;
  std::string object_id = "object";
  
  // 新增：规划参数配置
  ActionParams params;
};

// 移动到倾倒位置任务参数
struct MoveToPourTaskParams {
    // 被夹持的对象ID（用于release后更新planning scene）
    std::string object_id;

    // 核心位置参数
    double target_x = 0.1;
    double target_y = -0.5;
    double target_z = 0.2;
    // 可选目标姿态（默认单位四元数）
    double target_qx = 0.0;
    double target_qy = 0.0;
    double target_qz = 0.0;
    double target_qw = 1.0;
    
    // 核心运动参数 
    double velocity_scaling = 0.15;
    double timeout_sec = 60.0;
    
    // 内部优化的固定参数
    double acceleration_scaling = 0.3;
    double step_size = 0.008;
    double min_cartesian_fraction = 0.85;
    bool maintain_current_orientation = true;
    bool cartesian_only = false;

    // 可选：在到达倾倒位置后执行简单倾倒序列
    bool pour_execute = true;
    double tilt_start_deg = 15.0;
    double tilt_end_deg = 140.0;
    double tilt_speed_deg_s = 25.0;
    double pour_hold_sec = 2.0;
    
    // 可选：在到达目标位置后执行递给用户的动作
    bool execute_give = false;
    double gripper_open_ratio = 1.0;
    
    bool plan_only = false;
    
    // 新增：规划参数配置
    ActionParams params;
};

// 放置任务参数
struct PlaceTaskParams {
  // 放置目标位置（可选）
  std::optional<geometry_msgs::msg::Pose> target_pose = std::nullopt;
  
  // 放置参数
  double lower_min = 0.03;
  double lower_max = 0.2;
  double retreat_min = 0.05;
  double retreat_max = 0.1;
  
  bool plan_only = false;
  std::string object_id = "object";
  
  // 新增：规划参数配置
  ActionParams params;
};

// 返回任务参数
struct ReturnTaskParams {
  // 目标关节配置（可选，使用"home"配置）
  std::optional<std::map<std::string, double>> target_joints = std::nullopt;
  
  bool plan_only = false;
  double timeout_sec = 15.0;
  
  // 新增：规划参数配置
  ActionParams params;
};

// 任务构建器函数声明
moveit::task_constructor::Task build_pick_task(const rclcpp::Node::SharedPtr& node, 
                                                const PickTaskParams& params);

moveit::task_constructor::Task build_move_to_pour_task(const rclcpp::Node::SharedPtr& node,
                                                       const MoveToPourTaskParams& params);

moveit::task_constructor::Task build_place_task(const rclcpp::Node::SharedPtr& node,
                                                 const PlaceTaskParams& params);

moveit::task_constructor::Task build_return_task(const rclcpp::Node::SharedPtr& node,
                                                  const ReturnTaskParams& params);

// 通用配置函数
void configure_moveit_params(const rclcpp::Node::SharedPtr& node);

} // namespace mtc_action_library



