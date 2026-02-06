#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <mtc_interface/action/execute_pour.hpp>  // Reuse existing Action interface

#include <moveit/task_constructor/task.h>
#include <mtc_tutorial/modular_task_builders.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <limits>
#include <memory>
#include <deque>

namespace mtc = moveit::task_constructor;

using ExecutePour = mtc_interface::action::ExecutePour;
using GoalHandleEP = rclcpp_action::ServerGoalHandle<ExecutePour>;

// Import types from mtc_tutorial namespace
// using mtc_tutorial::CartesianPourTaskParams;
// using mtc_tutorial::build_cartesian_pour_task;

class ModularTaskServer : public rclcpp::Node {
public:
    ModularTaskServer() : Node("modular_task_server") {
        // Create Action server - use different namespace to avoid conflict with original server
        server_ = rclcpp_action::create_server<ExecutePour>(
            this, "execute_modular_task",
            std::bind(&ModularTaskServer::handle_goal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&ModularTaskServer::handle_cancel, this, std::placeholders::_1),
            std::bind(&ModularTaskServer::handle_accepted, this, std::placeholders::_1));
        
        // Declare task type parameter
        this->declare_parameter<std::string>("task_type", "pick");
        
        // Declare: pick-related parameters (can be dynamically set by client)
        this->declare_parameter<double>("pick.safe_approach_height", 0.23);
        this->declare_parameter<bool>("pick.use_back_constraint", true);
        this->declare_parameter<double>("pick.back_region_center_y", -0.6);
        this->declare_parameter<double>("pick.back_region_size_x", 2.0);
        this->declare_parameter<double>("pick.back_region_size_y", 1.2);
        this->declare_parameter<double>("pick.back_region_size_z", 2.0);

        // New: target object IDs for pick/place
        this->declare_parameter<std::string>("pick.object_id", "object");
        this->declare_parameter<std::string>("place.object_id", "object");
        // Pre-declare origin position parameters for objects, for setup_planning_scene to write
        for (int i = 1; i <= 20; ++i) {
            std::string oid = (i == 1) ? std::string("object") : (std::string("object_") + std::to_string(i));
            this->declare_parameter<double>("place.origin." + oid + ".x", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".y", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".z", 0.0);
        }
        // Pre-declare: bowl series object origin position parameters
        for (int i = 1; i <= 20; ++i) {
            std::string oid = (i == 1) ? std::string("bowl") : (std::string("bowl_") + std::to_string(i));
            this->declare_parameter<double>("place.origin." + oid + ".x", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".y", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".z", 0.0);
        }
        // Pre-declare: bottle series object origin position parameters
        for (int i = 1; i <= 20; ++i) {
            std::string oid = (i == 1) ? std::string("bottle") : (std::string("bottle_") + std::to_string(i));
            this->declare_parameter<double>("place.origin." + oid + ".x", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".y", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".z", 0.0);
        }
        this->declare_parameter<bool>("place.return_to_origin", false);
        this->declare_parameter<double>("place.target_x", 0.0);
        this->declare_parameter<double>("place.target_y", -0.45);
        this->declare_parameter<double>("place.target_z", 0.18);
        
        // Declare: pour target position (maintain current orientation, only control position)
        this->declare_parameter<double>("pour.target_x", 0.1);
        this->declare_parameter<double>("pour.target_y", -0.5);
        this->declare_parameter<double>("pour.target_z", 0.15);
        this->declare_parameter<std::string>("pour.object_id", "");
        
        // Declare: move-to-pour related parameters (simplified version)
        this->declare_parameter<double>("move_to_pour.target_x", 0.1);
        this->declare_parameter<double>("move_to_pour.target_y", -0.5);
        this->declare_parameter<double>("move_to_pour.target_z", 0.2);
        this->declare_parameter<double>("move_to_pour.velocity_scaling", 0.15);
        this->declare_parameter<double>("move_to_pour.acceleration_scaling", 0.3);
        this->declare_parameter<double>("move_to_pour.timeout_sec", 60.0);
        // New: optional pour-related parameters
        this->declare_parameter<bool>("move_to_pour.pour_execute", false);
        this->declare_parameter<double>("move_to_pour.tilt_start_deg", 45.0);
        this->declare_parameter<double>("move_to_pour.tilt_end_deg", 120.0);
        this->declare_parameter<double>("move_to_pour.tilt_speed_deg_s", 25.0);
        this->declare_parameter<double>("move_to_pour.pour_hold_sec", 0.0);
        this->declare_parameter<std::string>("move_to_pour.object_id", "");
        
        // New: give-to-user related parameters
        this->declare_parameter<bool>("move_to_pour.execute_give", false);
        this->declare_parameter<double>("move_to_pour.gripper_open_ratio", 1.0);
        
        RCLCPP_INFO(this->get_logger(), "Modular MTC task server started");
        RCLCPP_INFO(this->get_logger(), "Supported task types: pick, pour, move_to_pour, place, return");
        RCLCPP_INFO(this->get_logger(), "Action interface: /execute_modular_task");
    }

private:
    rclcpp_action::Server<ExecutePour>::SharedPtr server_;
    bool cancel_requested_ = false;
    // Retain recent task objects for RViz Introspection service to query historical plans
    std::deque<std::shared_ptr<mtc::Task>> task_history_;
    size_t history_limit_ = 5;

    rclcpp_action::GoalResponse handle_goal(
        const rclcpp_action::GoalUUID & uuid,
        std::shared_ptr<const ExecutePour::Goal> goal) {
        
        // Specify task type via target_id; compatible with format like "pick:object_2"
        std::string task_type = goal->target_id.empty() ? "pour" : goal->target_id;
        std::string raw_target = task_type;
        auto colon_pos = task_type.find(":");
        if (colon_pos != std::string::npos) {
            task_type = task_type.substr(0, colon_pos);
        }
        
        RCLCPP_INFO(this->get_logger(), "Received modular task execution request: type=%s (raw=%s)", task_type.c_str(), raw_target.c_str());
        
        // Validate task type
        if (task_type != "pick" && task_type != "pour" && 
            task_type != "place" && task_type != "return" &&
            task_type != "move_to_pour") {
            RCLCPP_ERROR(this->get_logger(), "Unsupported task type: %s", task_type.c_str());
            return rclcpp_action::GoalResponse::REJECT;
        }
        
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse handle_cancel(
        const std::shared_ptr<GoalHandleEP> goal_handle) {
        RCLCPP_INFO(this->get_logger(), "Received task cancellation request");
        cancel_requested_ = true;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void handle_accepted(std::shared_ptr<GoalHandleEP> goal_handle) {
        std::thread([this, goal_handle]() {
            auto goal = goal_handle->get_goal();
            auto feedback = std::make_shared<ExecutePour::Feedback>();
            auto result = std::make_shared<ExecutePour::Result>();
            
            cancel_requested_ = false;
            
            try {
                // Specify task type via target_id
                std::string task_type = goal->target_id.empty() ? "pour" : goal->target_id;
                std::string goal_object_id;
                // Support composite encoding: e.g., "pick:object_2" / "place:object_2"
                auto colon_pos = task_type.find(":");
                if (colon_pos != std::string::npos) {
                    goal_object_id = task_type.substr(colon_pos + 1);
                    task_type = task_type.substr(0, colon_pos);
                }
                
                RCLCPP_INFO(this->get_logger(), "Starting modular task execution: %s", task_type.c_str());
                
                // Build task (use shared_ptr to maintain lifecycle)
                auto task_ptr = std::make_shared<mtc::Task>();
                if (!build_modular_task(task_type, goal, *task_ptr, goal_object_id)) {
                    result->success = false;
                    result->error_msg = "Task build failed";
                    goal_handle->abort(result);
                    return;
                }
                
                // Publish feedback: start planning
                feedback->stage = "planning";
                feedback->progress = 0.1f;
                feedback->current_tilt_deg = 0.0f;
                goal_handle->publish_feedback(feedback);
                
                // Initialize and plan task
                task_ptr->init();
                
                feedback->stage = "planning";
                feedback->progress = 0.3f;
                goal_handle->publish_feedback(feedback);
                
                if (!task_ptr->plan(2)) {
                    result->success = false;
                    result->error_msg = "Task planning failed";
                    goal_handle->abort(result);
                    return;
                }
                
                feedback->stage = "planned";
                feedback->progress = 0.5f;
                goal_handle->publish_feedback(feedback);
                
                // Check if plan-only mode
                if (goal->plan_only) {
                    result->success = true;
                    result->error_msg = "";
                    result->duration_sec = 0.0;
                    goal_handle->succeed(result);
                    // Save to history for RViz viewing
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // Check for cancellation request
                if (cancel_requested_) {
                    result->success = false;
                    result->error_msg = "Task cancelled before execution";
                    goal_handle->canceled(result);
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // Execute task
                feedback->stage = "executing";
                feedback->progress = 0.7f;
                goal_handle->publish_feedback(feedback);
                
                auto start_time = std::chrono::steady_clock::now();
                const auto& solution = *task_ptr->solutions().front();
                auto exec_result = task_ptr->execute(solution);
                auto end_time = std::chrono::steady_clock::now();
                
                auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
                result->duration_sec = duration.count() / 1000.0;
                
                // Check execution result
                if (exec_result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
                    result->success = false;
                    result->error_msg = "Task execution failed, error code: " + std::to_string(exec_result.val);
                    goal_handle->abort(result);
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // Success
                result->success = true;
                result->error_msg = "";
                feedback->stage = "completed";
                feedback->progress = 1.0f;
                goal_handle->publish_feedback(feedback);
                goal_handle->succeed(result);
                
                RCLCPP_INFO(this->get_logger(), "%s task completed, duration: %.2fs", 
                           task_type.c_str(), result->duration_sec);
                // Save to history for RViz viewing
                task_history_.push_back(task_ptr);
                if (task_history_.size() > history_limit_) task_history_.pop_front();
                
            } catch (const std::exception& e) {
                result->success = false;
                result->error_msg = std::string("Task execution exception: ") + e.what();
                goal_handle->abort(result);
                RCLCPP_ERROR(this->get_logger(), "Task execution exception: %s", e.what());
            }
        }).detach();
    }
    
    bool build_modular_task(const std::string& task_type, 
                            std::shared_ptr<const ExecutePour::Goal> goal,
                            mtc::Task& task,
                            const std::string& goal_object_id) {
        auto node = this->shared_from_this();
        
        try {
            if (task_type == "pick") {
                RCLCPP_INFO(this->get_logger(), "Building pick task...");
                mtc_tutorial::PickTaskParams pick_params;
                
                // Map parameters from ExecutePour Goal
                pick_params.approach_min = goal->approach_min;
                pick_params.approach_max = goal->approach_max;
                pick_params.lift_height = goal->lift_height;
                pick_params.plan_only = goal->plan_only;
                std::string pick_object_id = !goal_object_id.empty() ? goal_object_id : this->get_parameter("pick.object_id").as_string();
                pick_params.object_id = pick_object_id;
                RCLCPP_INFO(this->get_logger(), "Using pick.object_id=%s", pick_object_id.c_str());
                
                // Use default source position (can be set via parameter server)
                pick_params.source_x = 0.0;
                pick_params.source_y = -0.4;
                pick_params.source_z = 0.13;

                // Read safe approach height parameter (supports client setting via parameter server)
                double safe_h = 0.23;
                this->get_parameter_or<double>("pick.safe_approach_height", safe_h, 0.23);
                pick_params.safe_approach_height = safe_h;
                
                task = mtc_tutorial::build_pick_task(node, pick_params);
                
            } else if (task_type == "pour") {
                RCLCPP_INFO(this->get_logger(), "Building pour task...");
                mtc_tutorial::PourOnlyTaskParams pour_params;
                
                pour_params.tilt_start_deg = goal->tilt_start_deg;
                pour_params.tilt_end_deg = goal->tilt_end_deg;
                pour_params.tilt_speed_deg_s = goal->tilt_speed_deg_s;
                pour_params.pour_hold_sec = goal->pour_hold_sec;
                pour_params.move_to_pour_min = 0.08;
                pour_params.move_to_pour_max = 0.15;
                pour_params.plan_only = goal->plan_only;
                // Read: pour target position (maintain orientation, only control position)
                // Support selecting object position via pour.object_id (preferred), fallback to origin params, then static params
                try {
                    std::string p_oid = this->get_parameter("pour.object_id").as_string();
                    if (!p_oid.empty()) {
                        moveit::planning_interface::PlanningSceneInterface psi;
                        auto objs = psi.getObjects({ p_oid });
                        auto it = objs.find(p_oid);
                        if (it != objs.end() && !it->second.primitive_poses.empty()) {
                            const auto& p = it->second.primitive_poses.front();
                            pour_params.target_x = p.position.x;
                            pour_params.target_y = p.position.y;
                            pour_params.target_z = p.position.z;
                            RCLCPP_INFO(this->get_logger(), "Pour using object %s position as target (%.3f, %.3f, %.3f)", p_oid.c_str(), pour_params.target_x, pour_params.target_y, pour_params.target_z);
                        } else {
                            double ox = std::numeric_limits<double>::quiet_NaN();
                            double oy = std::numeric_limits<double>::quiet_NaN();
                            double oz = std::numeric_limits<double>::quiet_NaN();
                            this->get_parameter_or<double>("place.origin." + p_oid + ".x", ox, ox);
                            this->get_parameter_or<double>("place.origin." + p_oid + ".y", oy, oy);
                            this->get_parameter_or<double>("place.origin." + p_oid + ".z", oz, oz);
                            if (!std::isnan(ox) && !std::isnan(oy) && !std::isnan(oz)) {
                                pour_params.target_x = ox;
                                pour_params.target_y = oy;
                                pour_params.target_z = oz;
                                RCLCPP_INFO(this->get_logger(), "Pour using origin position from parameters as target (%.3f, %.3f, %.3f)", ox, oy, oz);
                            } else {
                                pour_params.target_x = this->get_parameter("pour.target_x").as_double();
                                pour_params.target_y = this->get_parameter("pour.target_y").as_double();
                                pour_params.target_z = this->get_parameter("pour.target_z").as_double();
                                RCLCPP_WARN(this->get_logger(), "pour: object %s pose/origin not found, using static parameters", p_oid.c_str());
                            }
                        }
                    } else {
                        pour_params.target_x = this->get_parameter("pour.target_x").as_double();
                        pour_params.target_y = this->get_parameter("pour.target_y").as_double();
                        pour_params.target_z = this->get_parameter("pour.target_z").as_double();
                    }
                } catch (...) {
                    pour_params.target_x = this->get_parameter("pour.target_x").as_double();
                    pour_params.target_y = this->get_parameter("pour.target_y").as_double();
                    pour_params.target_z = this->get_parameter("pour.target_z").as_double();
                }
                
                task = mtc_tutorial::build_pour_only_task(node, pour_params);               
            } else if (task_type == "place") {
                RCLCPP_INFO(this->get_logger(), "🔧 构建Place任务...");
                mtc_tutorial::PlaceTaskParams place_params;
                
                place_params.plan_only = goal->plan_only;
                std::string place_object_id = !goal_object_id.empty() ? goal_object_id : this->get_parameter("place.object_id").as_string();
                place_params.object_id = place_object_id;
                RCLCPP_INFO(this->get_logger(), "📌 使用的place.object_id=%s", place_object_id.c_str());
                
                // 读取“回到初始位置”或“指定目标位置”
                bool return_to_origin = false;
                this->get_parameter_or<bool>("place.return_to_origin", return_to_origin, false);
                // 兼容：若客户端通过Action参数传过来了 target_id=place:object_2 之外的键值，则在参数服务器里提前设置
                // 这里不做，因为 _execute_real_mtc_task 已经在客户端侧写入参数表（保持一致即可）
                if (return_to_origin) {
                    moveit::planning_interface::PlanningSceneInterface psi;
                    auto objs = psi.getObjects({ place_object_id });
                    auto it = objs.find(place_object_id);
                    if (it != objs.end() && !it->second.primitive_poses.empty()) {
                        geometry_msgs::msg::Pose origin_pose = it->second.primitive_poses.front();
                        origin_pose.position.z = 0.16; // Fixed Z=0.16
                        place_params.target_pose = origin_pose;
                        RCLCPP_INFO(this->get_logger(), "Place returning to original position (%.3f, %.3f, %.3f)",
                                   origin_pose.position.x, origin_pose.position.y, origin_pose.position.z);
                    } else {
                        // Fallback: read origin position from parameter table written by setup_planning_scene
                        double ox = std::numeric_limits<double>::quiet_NaN();
                        double oy = std::numeric_limits<double>::quiet_NaN();
                        double oz = std::numeric_limits<double>::quiet_NaN();
                        this->get_parameter_or<double>("place.origin." + place_object_id + ".x", ox, ox);
                        this->get_parameter_or<double>("place.origin." + place_object_id + ".y", oy, oy);
                        this->get_parameter_or<double>("place.origin." + place_object_id + ".z", oz, oz);
                        if (!std::isnan(ox) && !std::isnan(oy) && !std::isnan(oz)) {
                            geometry_msgs::msg::Pose p;
                            p.position.x = ox; p.position.y = oy; p.position.z = 0.161; p.orientation.w = 1.0;
                            place_params.target_pose = p;
                            RCLCPP_INFO(this->get_logger(), "Place returning to origin position from parameters (%.3f, %.3f, %.3f)", ox, oy, 0.16);
                        } else {
                            RCLCPP_WARN(this->get_logger(), "Original pose for %s not found in scene/parameters, using default place point", place_object_id.c_str());
                        }
                    }
                } else {
                    try {
                        geometry_msgs::msg::Pose p;
                        p.position.x = this->get_parameter("place.target_x").as_double();
                        p.position.y = this->get_parameter("place.target_y").as_double();
                        (void)this; // Keep interface, but force fixed to 0.16
                        p.position.z = 0.161;
                        p.orientation.w = 1.0;
                        place_params.target_pose = p; // Will be overridden by default if not set
                        RCLCPP_INFO(this->get_logger(), "Place to specified point (%.3f, %.3f, %.3f)", p.position.x, p.position.y, p.position.z);
                    } catch (...) {
                        // Keep default
                    }
                }
                
                task = mtc_tutorial::build_place_task(node, place_params);
                
            } else if (task_type == "return") {
                RCLCPP_INFO(this->get_logger(), "Building return task...");
                mtc_tutorial::ReturnTaskParams return_params;
                
                return_params.plan_only = goal->plan_only;
                return_params.timeout_sec = 15.0;
                
                task = mtc_tutorial::build_return_task(node, return_params);
                
            } else if (task_type == "move_to_pour") {
                RCLCPP_INFO(this->get_logger(), "Building simplified move-to-pour task...");
                mtc_tutorial::MoveToPourTaskParams move_to_pour_params;
                
                // Read core parameters
                move_to_pour_params.target_x = this->get_parameter("move_to_pour.target_x").as_double();
                move_to_pour_params.target_y = this->get_parameter("move_to_pour.target_y").as_double();
                move_to_pour_params.target_z = this->get_parameter("move_to_pour.target_z").as_double();
                move_to_pour_params.velocity_scaling = this->get_parameter("move_to_pour.velocity_scaling").as_double();
                move_to_pour_params.timeout_sec = this->get_parameter("move_to_pour.timeout_sec").as_double();
                
                // Auto-adjust acceleration (use client-provided acceleration parameter if available)
                try {
                    move_to_pour_params.acceleration_scaling = this->get_parameter("move_to_pour.acceleration_scaling").as_double();
                } catch (...) {
                    // Use velocity-based auto-calculation
                    move_to_pour_params.acceleration_scaling = std::min(0.5, move_to_pour_params.velocity_scaling * 2.0);
                }
                
                // If object ID specified, use object position as target
                try {
                    std::string tgt_oid = this->get_parameter("move_to_pour.object_id").as_string();
                    if (!tgt_oid.empty()) {
                        moveit::planning_interface::PlanningSceneInterface psi;
                        auto objs = psi.getObjects({ tgt_oid });
                        auto it = objs.find(tgt_oid);
                        if (it != objs.end() && !it->second.primitive_poses.empty()) {
                            const auto& p = it->second.primitive_poses.front();
                            // If PSI returns pose (0,0,0), try fallback to place.origin parameters
                            bool psi_pose_zero = (std::abs(p.position.x) < 1e-6 &&
                                                  std::abs(p.position.y) < 1e-6 &&
                                                  std::abs(p.position.z) < 1e-6);
                            if (psi_pose_zero) {
                                double ox = std::numeric_limits<double>::quiet_NaN();
                                double oy = std::numeric_limits<double>::quiet_NaN();
                                double oz = std::numeric_limits<double>::quiet_NaN();
                                this->get_parameter_or<double>("place.origin." + tgt_oid + ".x", ox, ox);
                                this->get_parameter_or<double>("place.origin." + tgt_oid + ".y", oy, oy);
                                this->get_parameter_or<double>("place.origin." + tgt_oid + ".z", oz, oz);
                                if (!std::isnan(ox) && !std::isnan(oy) && !std::isnan(oz)) {
                                    move_to_pour_params.target_x = ox;           // x unchanged
                                    move_to_pour_params.target_y = oy + 0.04;    // y increased by 0.02m
                                    move_to_pour_params.target_z = 0.26;         // z fixed to 0.25m
                                    RCLCPP_WARN(this->get_logger(),
                                                "PSI returned (0,0,0), fallback using place.origin.%s with offset -> (%.3f, %.3f, %.3f)",
                                                tgt_oid.c_str(),
                                                move_to_pour_params.target_x,
                                                move_to_pour_params.target_y,
                                                move_to_pour_params.target_z);
                                } else {
                                    // Cannot fallback, still use PSI (0,0,0) with offset
                                    move_to_pour_params.target_x = p.position.x;           // x unchanged
                                    move_to_pour_params.target_y = p.position.y + 0.01;    // y offset increased by 0.02m
                                    move_to_pour_params.target_z = 0.26;                   // z fixed to 0.26m
                                    RCLCPP_WARN(this->get_logger(),
                                                "PSI returned (0,0,0) and no place.origin.%s, continue with PSI and apply offset -> (%.3f, %.3f, %.3f)",
                                                tgt_oid.c_str(),
                                                move_to_pour_params.target_x,
                                                move_to_pour_params.target_y,
                                                move_to_pour_params.target_z);
                                }
                            } else {
                                move_to_pour_params.target_x = p.position.x;           // x unchanged
                                move_to_pour_params.target_y = p.position.y + 0.01;    // y increased by 0.002m
                                move_to_pour_params.target_z = 0.30;                   // z fixed to 0.30m
                                RCLCPP_INFO(this->get_logger(), "move_to_pour using object %s position with offset -> (%.3f, %.3f, %.3f)",
                                            tgt_oid.c_str(), move_to_pour_params.target_x,
                                            move_to_pour_params.target_y, move_to_pour_params.target_z);
                            }
                        } else {
                            // Fallback: if PSI unavailable, try using origin position from parameters
                            double ox = std::numeric_limits<double>::quiet_NaN();
                            double oy = std::numeric_limits<double>::quiet_NaN();
                            double oz = std::numeric_limits<double>::quiet_NaN();
                            this->get_parameter_or<double>("place.origin." + tgt_oid + ".x", ox, ox);
                            this->get_parameter_or<double>("place.origin." + tgt_oid + ".y", oy, oy);
                            this->get_parameter_or<double>("place.origin." + tgt_oid + ".z", oz, oz);
                            if (!std::isnan(ox) && !std::isnan(oy) && !std::isnan(oz)) {
                                move_to_pour_params.target_x = ox;
                                move_to_pour_params.target_y = oy + 0.01;
                                move_to_pour_params.target_z = 0.30;
                                RCLCPP_INFO(this->get_logger(), "move_to_pour using origin position from parameters with offset -> (%.3f, %.3f, %.3f)",
                                            move_to_pour_params.target_x,
                                            move_to_pour_params.target_y,
                                            move_to_pour_params.target_z);
                            } else {
                                RCLCPP_WARN(this->get_logger(), "move_to_pour: object %s pose/origin not found, using existing coordinates (%.3f, %.3f, %.3f)",
                                            tgt_oid.c_str(), move_to_pour_params.target_x,
                                            move_to_pour_params.target_y, move_to_pour_params.target_z);
                            }
                        }
                    }
                } catch (...) {}

                // Read: merged optional pour parameters
                move_to_pour_params.pour_execute = this->get_parameter("move_to_pour.pour_execute").as_bool();
                move_to_pour_params.tilt_start_deg = this->get_parameter("move_to_pour.tilt_start_deg").as_double();
                move_to_pour_params.tilt_end_deg = this->get_parameter("move_to_pour.tilt_end_deg").as_double();
                move_to_pour_params.tilt_speed_deg_s = this->get_parameter("move_to_pour.tilt_speed_deg_s").as_double();
                move_to_pour_params.pour_hold_sec = this->get_parameter("move_to_pour.pour_hold_sec").as_double();
                
                // Read: give-to-user related parameters
                move_to_pour_params.execute_give = this->get_parameter("move_to_pour.execute_give").as_bool();
                move_to_pour_params.gripper_open_ratio = this->get_parameter("move_to_pour.gripper_open_ratio").as_double();
                
                move_to_pour_params.plan_only = goal->plan_only;
                
                RCLCPP_INFO(this->get_logger(), "Simplified params: target(%.2f, %.2f, %.2f), velocity=%.2f, accel=%.2f, pour=%s", 
                           move_to_pour_params.target_x, move_to_pour_params.target_y, move_to_pour_params.target_z,
                           move_to_pour_params.velocity_scaling, move_to_pour_params.acceleration_scaling,
                           move_to_pour_params.pour_execute ? "true" : "false");
                
                task = mtc_tutorial::build_move_to_pour_task(node, move_to_pour_params);
                
            } else {
                RCLCPP_ERROR(this->get_logger(), "Unknown task type: %s", task_type.c_str());
                return false;
            }
            
            RCLCPP_INFO(this->get_logger(), "%s task built successfully: %s", 
                       task_type.c_str(), task.stages()->name().c_str());
            return true;
            
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "Exception building %s task: %s", task_type.c_str(), e.what());
            return false;
        }
    }
};

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto server = std::make_shared<ModularTaskServer>();
    rclcpp::spin(server);
    rclcpp::shutdown();
    return 0;
} 