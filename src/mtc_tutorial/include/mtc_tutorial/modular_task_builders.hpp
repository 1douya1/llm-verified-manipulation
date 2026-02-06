#pragma once

#include <moveit/task_constructor/task.h>
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <optional>

namespace mtc_tutorial {

// Pick task parameters
struct PickTaskParams {
  // Target object position
  double source_x = 0.0;
  double source_y = -0.4; 
  double source_z = 0.13;
  double source_qx = 0.0;
  double source_qy = 0.0;
  double source_qz = 0.0;
  double source_qw = 1.0;
  
  // Grasp hint parameters
  double approach_min = 0.05;
  double approach_max = 0.15;
  double lift_height = 0.12;
  
  // Safe approach height (reach above grasp point first, then descend vertically)
  double safe_approach_height = 0.18;
  
  // Other options
  bool plan_only = false;
  std::string object_id = "object";
};

// Pour-only task parameters (excludes pick and place)
struct PourOnlyTaskParams {
  // Target pour position
  double target_x = 0.1;
  double target_y = -0.5;
  double target_z = 0.13;
  
  // Tilt parameters
  double tilt_start_deg = 15.0;
  double tilt_end_deg = 140.0;
  double tilt_speed_deg_s = 25.0;
  double pour_hold_sec = 2.0;
  
  // Movement parameters
  double move_to_pour_min = 0.08;
  double move_to_pour_max = 0.15;
  
  bool plan_only = false;
};


// Move-to-pour task parameters (simplified version)
struct MoveToPourTaskParams {
    // Core position parameters
    double target_x = 0.1;
    double target_y = -0.5;
    double target_z = 0.2;
    
    // Core motion parameters 
    double velocity_scaling = 0.15;     // Velocity scaling (maps to MCP speed parameter)
    double timeout_sec = 60.0;
    
    // Internal optimized parameters (user does not need to configure)
    double acceleration_scaling = 0.3;  // Auto-adjusted based on velocity
    double step_size = 0.008;           // Optimized Cartesian step size
    double min_cartesian_fraction = 0.85; // Optimized minimum Cartesian path fraction
    bool maintain_current_orientation = true; // Always maintain current orientation

    // Optional: execute simple pour sequence after reaching position
    bool pour_execute = true;          // When true, execute pouring stage
    double tilt_start_deg = 15.0;       // Pour start angle (degrees)
    double tilt_end_deg = 140.0;        // Pour end angle (degrees)
    double tilt_speed_deg_s = 25.0;     // Pour joint speed (deg/s)
    double pour_hold_sec = 2.0;         // Pour hold time (seconds), 0 means no hold
    
    // Optional: execute give-to-user action after reaching target
    bool execute_give = false;          // When true, execute give action
    double gripper_open_ratio = 1.0;    // Gripper opening ratio (0.0-1.0), 1.0 is fully open
    
    bool plan_only = false;
};

// Pre-pour task parameters
struct PrePourTaskParams {
  // Pour target point (reference for pre-pose)
  double target_x = 0.1;
  double target_y = -0.5;
  double target_z = 0.2;

  // Safe lift height (additional Z height relative to target)
  double safe_lift_z = 0.10;

  // Orientation strategy
  bool yaw_align_to_target = true;      // Align yaw towards target
  bool keep_current_roll_pitch = true;  // Maintain current roll/pitch

  // Final approach strategy
  bool use_cartesian_for_final_approach = true;

  // Planning parameters
  double velocity_scaling = 0.15;
  double acceleration_scaling = 0.3;
  double step_size = 0.008;
  double min_cartesian_fraction = 0.85;
  double ik_timeout = 5.0;
  int max_ik_solutions = 2;
  double min_solution_distance = 0.4;
  double timeout_sec = 60.0;

  // Plan only, do not execute
  bool plan_only = false;
};

// Place task parameters
struct PlaceTaskParams {
  // Target place position (optional, uses default if not set)
  std::optional<geometry_msgs::msg::Pose> target_pose = std::nullopt;
  
  // Place parameters
  double lower_min = 0.03;
  double lower_max = 0.2;
  double retreat_min = 0.05;
  double retreat_max = 0.1;
  
  bool plan_only = false;
  std::string object_id = "object";
};

// Return task parameters
struct ReturnTaskParams {
  // Target joint configuration (optional, uses "home" if not set)
  std::optional<std::map<std::string, double>> target_joints = std::nullopt;
  
  bool plan_only = false;
  double timeout_sec = 15.0;
};

// Task builder function declarations
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

// Common configuration functions (extracted from pour_task_builder.cpp)
void configure_moveit_params(const rclcpp::Node::SharedPtr& node);
void sync_robot_model_params(const rclcpp::Node::SharedPtr& node);

} // namespace mtc_tutorial 