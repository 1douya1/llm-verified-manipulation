#pragma once

#include <moveit/task_constructor/task.h>
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <optional>

namespace mtc_tutorial {

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
  
  // 安全高度（先到达抓取点上方的高度，再垂直下降同样距离）
  double safe_approach_height = 0.18;
  
  // 其他选项
  bool plan_only = false;
  std::string object_id = "object";
};

// 纯倾倒任务参数（不包含抓取和放置）
struct PourOnlyTaskParams {
  // 目标倾倒位置
  double target_x = 0.1;
  double target_y = -0.5;
  double target_z = 0.13;
  
  // 倾斜参数
  double tilt_start_deg = 15.0;
  double tilt_end_deg = 140.0;
  double tilt_speed_deg_s = 25.0;
  double pour_hold_sec = 2.0;
  
  // 移动参数
  double move_to_pour_min = 0.08;
  double move_to_pour_max = 0.15;
  
  bool plan_only = false;
};


// MoveToPourTaskParams - 移动到倾倒位置任务参数（简化版本）
struct MoveToPourTaskParams {
    // 核心位置参数
    double target_x = 0.1;
    double target_y = -0.5;
    double target_z = 0.2;
    
    // 核心运动参数 
    double velocity_scaling = 0.15;     // 速度缩放（直接对应MCP的speed参数）
    double timeout_sec = 60.0;
    
    // 内部优化的固定参数（用户不需要配置）
    double acceleration_scaling = 0.3;  // 自动根据速度调整
    double step_size = 0.008;           // 优化的笛卡尔步长
    double min_cartesian_fraction = 0.85; // 优化的最小笛卡尔路径比例
    bool maintain_current_orientation = true; // 总是保持当前姿态

    // 可选：在到达倾倒位置后执行简单倾倒序列
    bool pour_execute = true;          // 为 true 时，执行倾倒阶段
    double tilt_start_deg = 15.0;       // 倾倒起始角（度）
    double tilt_end_deg = 140.0;        // 倾倒结束角（度）
    double tilt_speed_deg_s = 25.0;     // 倾倒关节速度（度/秒）
    double pour_hold_sec = 2.0;         // 倾倒保持时间（秒），0 表示不保持
    
    // 可选：在到达目标位置后执行递给用户的动作
    bool execute_give = false;          // 为 true 时，执行递给用户的动作
    double gripper_open_ratio = 1.0;    // 夹爪打开比例（0.0-1.0），1.0表示完全打开
    
    bool plan_only = false;
};

// 预倒水任务参数
struct PrePourTaskParams {
  // 倒水目标点（预姿态参考点）
  double target_x = 0.1;
  double target_y = -0.5;
  double target_z = 0.2;

  // 安全抬升高度（相对目标点的额外Z高度）
  double safe_lift_z = 0.10;

  // 姿态策略
  bool yaw_align_to_target = true;      // 朝向目标点
  bool keep_current_roll_pitch = true;  // 保持当前的 roll/pitch

  // 末段靠近策略
  bool use_cartesian_for_final_approach = true;

  // 规划参数
  double velocity_scaling = 0.15;
  double acceleration_scaling = 0.3;
  double step_size = 0.008;
  double min_cartesian_fraction = 0.85;
  double ik_timeout = 5.0;
  int max_ik_solutions = 2;
  double min_solution_distance = 0.4;
  double timeout_sec = 60.0;

  // 仅规划不执行
  bool plan_only = false;
};

// 放置任务参数
struct PlaceTaskParams {
  // 放置目标位置（可选，使用默认位置）
  std::optional<geometry_msgs::msg::Pose> target_pose = std::nullopt;
  
  // 放置参数
  double lower_min = 0.03;
  double lower_max = 0.2;
  double retreat_min = 0.05;
  double retreat_max = 0.1;
  
  bool plan_only = false;
  std::string object_id = "object";
};

// 返回任务参数
struct ReturnTaskParams {
  // 目标关节配置（可选，使用"home"配置）
  std::optional<std::map<std::string, double>> target_joints = std::nullopt;
  
  bool plan_only = false;
  double timeout_sec = 15.0;
};

// 任务构建器函数声明
moveit::task_constructor::Task build_pick_task(const rclcpp::Node::SharedPtr& node, 
                                                const PickTaskParams& params);

moveit::task_constructor::Task build_pour_only_task(const rclcpp::Node::SharedPtr& node,
                                                     const PourOnlyTaskParams& params);

moveit::task_constructor::Task build_move_to_pour_task(const rclcpp::Node::SharedPtr& node,
                                                       const MoveToPourTaskParams& params);

moveit::task_constructor::Task build_pre_pour_task(const rclcpp::Node::SharedPtr& node,
                                                   const PrePourTaskParams& params);

moveit::task_constructor::Task build_place_task(const rclcpp::Node::SharedPtr& node,
                                                 const PlaceTaskParams& params);

moveit::task_constructor::Task build_return_task(const rclcpp::Node::SharedPtr& node,
                                                  const ReturnTaskParams& params);

// 通用配置函数（从pour_task_builder.cpp中提取）
void configure_moveit_params(const rclcpp::Node::SharedPtr& node);
void sync_robot_model_params(const rclcpp::Node::SharedPtr& node);

} // namespace mtc_tutorial 