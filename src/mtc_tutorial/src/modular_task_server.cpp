#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <mtc_interface/action/execute_pour.hpp>  // 复用现有的Action接口

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

// 导入mtc_tutorial命名空间中的类型
// using mtc_tutorial::CartesianPourTaskParams;
// using mtc_tutorial::build_cartesian_pour_task;

class ModularTaskServer : public rclcpp::Node {
public:
    ModularTaskServer() : Node("modular_task_server") {
        // 创建Action服务器 - 使用不同的命名空间来避免与原服务器冲突
        server_ = rclcpp_action::create_server<ExecutePour>(
            this, "execute_modular_task",
            std::bind(&ModularTaskServer::handle_goal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&ModularTaskServer::handle_cancel, this, std::placeholders::_1),
            std::bind(&ModularTaskServer::handle_accepted, this, std::placeholders::_1));
        
        // 声明任务类型参数
        this->declare_parameter<std::string>("task_type", "pick");
        
        // 声明：抓取相关参数（可由客户端动态设置）
        this->declare_parameter<double>("pick.safe_approach_height", 0.23);
        this->declare_parameter<bool>("pick.use_back_constraint", true);
        this->declare_parameter<double>("pick.back_region_center_y", -0.6);
        this->declare_parameter<double>("pick.back_region_size_x", 2.0);
        this->declare_parameter<double>("pick.back_region_size_y", 1.2);
        this->declare_parameter<double>("pick.back_region_size_z", 2.0);

        // 新增：抓取/放置的目标对象ID
        this->declare_parameter<std::string>("pick.object_id", "object");
        this->declare_parameter<std::string>("place.object_id", "object");
        // 预声明若干对象的原始位置参数，便于setup_planning_scene写入
        for (int i = 1; i <= 20; ++i) {
            std::string oid = (i == 1) ? std::string("object") : (std::string("object_") + std::to_string(i));
            this->declare_parameter<double>("place.origin." + oid + ".x", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".y", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".z", 0.0);
        }
        // 预声明：bowl 系列对象的原始位置参数
        for (int i = 1; i <= 20; ++i) {
            std::string oid = (i == 1) ? std::string("bowl") : (std::string("bowl_") + std::to_string(i));
            this->declare_parameter<double>("place.origin." + oid + ".x", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".y", 0.0);
            this->declare_parameter<double>("place.origin." + oid + ".z", 0.0);
        }
        // 预声明：bottle 系列对象的原始位置参数
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
        
        // 声明：倾倒目标位置（保持当前姿态，仅控制位置）
        this->declare_parameter<double>("pour.target_x", 0.1);
        this->declare_parameter<double>("pour.target_y", -0.5);
        this->declare_parameter<double>("pour.target_z", 0.15);
        this->declare_parameter<std::string>("pour.object_id", "");
        
        // 声明：移动到倾倒位置相关参数（简化版本）
        this->declare_parameter<double>("move_to_pour.target_x", 0.1);
        this->declare_parameter<double>("move_to_pour.target_y", -0.5);
        this->declare_parameter<double>("move_to_pour.target_z", 0.2);
        this->declare_parameter<double>("move_to_pour.velocity_scaling", 0.15);
        this->declare_parameter<double>("move_to_pour.acceleration_scaling", 0.3);
        this->declare_parameter<double>("move_to_pour.timeout_sec", 60.0);
        // 新增：可选倾倒相关参数
        this->declare_parameter<bool>("move_to_pour.pour_execute", false);
        this->declare_parameter<double>("move_to_pour.tilt_start_deg", 45.0);
        this->declare_parameter<double>("move_to_pour.tilt_end_deg", 120.0);
        this->declare_parameter<double>("move_to_pour.tilt_speed_deg_s", 25.0);
        this->declare_parameter<double>("move_to_pour.pour_hold_sec", 0.0);
        this->declare_parameter<std::string>("move_to_pour.object_id", "");
        
        // 新增：递给用户相关参数
        this->declare_parameter<bool>("move_to_pour.execute_give", false);
        this->declare_parameter<double>("move_to_pour.gripper_open_ratio", 1.0);
        
        RCLCPP_INFO(this->get_logger(), "🚀 模块化MTC任务服务器已启动");
        RCLCPP_INFO(this->get_logger(), "📋 支持的任务类型: pick, pour, move_to_pour, place, return");
        RCLCPP_INFO(this->get_logger(), "🔧 Action接口: /execute_modular_task");
    }

private:
    rclcpp_action::Server<ExecutePour>::SharedPtr server_;
    bool cancel_requested_ = false;
    // 保留最近的任务对象，供RViz的Introspection服务查询历史规划
    std::deque<std::shared_ptr<mtc::Task>> task_history_;
    size_t history_limit_ = 5;

    rclcpp_action::GoalResponse handle_goal(
        const rclcpp_action::GoalUUID & uuid,
        std::shared_ptr<const ExecutePour::Goal> goal) {
        
        // 通过target_id来指定任务类型；兼容形如 "pick:object_2"
        std::string task_type = goal->target_id.empty() ? "pour" : goal->target_id;
        std::string raw_target = task_type;
        auto colon_pos = task_type.find(":");
        if (colon_pos != std::string::npos) {
            task_type = task_type.substr(0, colon_pos);
        }
        
        RCLCPP_INFO(this->get_logger(), "收到模块化任务执行请求: 类型=%s (raw=%s)", task_type.c_str(), raw_target.c_str());
        
        // 验证任务类型
        if (task_type != "pick" && task_type != "pour" && 
            task_type != "place" && task_type != "return" &&
            task_type != "move_to_pour") {
            RCLCPP_ERROR(this->get_logger(), "不支持的任务类型: %s", task_type.c_str());
            return rclcpp_action::GoalResponse::REJECT;
        }
        
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse handle_cancel(
        const std::shared_ptr<GoalHandleEP> goal_handle) {
        RCLCPP_INFO(this->get_logger(), "收到取消任务请求");
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
                // 通过target_id来指定任务类型
                std::string task_type = goal->target_id.empty() ? "pour" : goal->target_id;
                std::string goal_object_id;
                // 支持复合编码：如 "pick:object_2" / "place:object_2"
                auto colon_pos = task_type.find(":");
                if (colon_pos != std::string::npos) {
                    goal_object_id = task_type.substr(colon_pos + 1);
                    task_type = task_type.substr(0, colon_pos);
                }
                
                RCLCPP_INFO(this->get_logger(), "开始执行模块化任务: %s", task_type.c_str());
                
                // 构建任务（使用shared_ptr保持生命周期）
                auto task_ptr = std::make_shared<mtc::Task>();
                if (!build_modular_task(task_type, goal, *task_ptr, goal_object_id)) {
                    result->success = false;
                    result->error_msg = "任务构建失败";
                    goal_handle->abort(result);
                    return;
                }
                
                // 发布反馈：开始规划
                feedback->stage = "planning";
                feedback->progress = 0.1f;
                feedback->current_tilt_deg = 0.0f;
                goal_handle->publish_feedback(feedback);
                
                // 初始化和规划任务
                task_ptr->init();
                
                feedback->stage = "planning";
                feedback->progress = 0.3f;
                goal_handle->publish_feedback(feedback);
                
                if (!task_ptr->plan(2)) {
                    result->success = false;
                    result->error_msg = "任务规划失败";
                    goal_handle->abort(result);
                    return;
                }
                
                feedback->stage = "planned";
                feedback->progress = 0.5f;
                goal_handle->publish_feedback(feedback);
                
                // 检查是否仅规划
                if (goal->plan_only) {
                    result->success = true;
                    result->error_msg = "";
                    result->duration_sec = 0.0;
                    goal_handle->succeed(result);
                    // 保存到历史，供RViz查看
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // 检查取消请求
                if (cancel_requested_) {
                    result->success = false;
                    result->error_msg = "任务在执行前被取消";
                    goal_handle->canceled(result);
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // 执行任务
                feedback->stage = "executing";
                feedback->progress = 0.7f;
                goal_handle->publish_feedback(feedback);
                
                auto start_time = std::chrono::steady_clock::now();
                const auto& solution = *task_ptr->solutions().front();
                auto exec_result = task_ptr->execute(solution);
                auto end_time = std::chrono::steady_clock::now();
                
                auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
                result->duration_sec = duration.count() / 1000.0;
                
                // 检查执行结果
                if (exec_result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
                    result->success = false;
                    result->error_msg = "任务执行失败，错误代码: " + std::to_string(exec_result.val);
                    goal_handle->abort(result);
                    task_history_.push_back(task_ptr);
                    if (task_history_.size() > history_limit_) task_history_.pop_front();
                    return;
                }
                
                // 成功完成
                result->success = true;
                result->error_msg = "";
                feedback->stage = "completed";
                feedback->progress = 1.0f;
                goal_handle->publish_feedback(feedback);
                goal_handle->succeed(result);
                
                RCLCPP_INFO(this->get_logger(), "✅ %s任务执行完成，耗时: %.2fs", 
                           task_type.c_str(), result->duration_sec);
                // 保存到历史，供RViz查看
                task_history_.push_back(task_ptr);
                if (task_history_.size() > history_limit_) task_history_.pop_front();
                
            } catch (const std::exception& e) {
                result->success = false;
                result->error_msg = std::string("任务执行异常: ") + e.what();
                goal_handle->abort(result);
                RCLCPP_ERROR(this->get_logger(), "❌ 任务执行异常: %s", e.what());
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
                RCLCPP_INFO(this->get_logger(), "🔧 构建Pick任务...");
                mtc_tutorial::PickTaskParams pick_params;
                
                // 从ExecutePour Goal映射参数
                pick_params.approach_min = goal->approach_min;
                pick_params.approach_max = goal->approach_max;
                pick_params.lift_height = goal->lift_height;
                pick_params.plan_only = goal->plan_only;
                std::string pick_object_id = !goal_object_id.empty() ? goal_object_id : this->get_parameter("pick.object_id").as_string();
                pick_params.object_id = pick_object_id;
                RCLCPP_INFO(this->get_logger(), "📌 使用的pick.object_id=%s", pick_object_id.c_str());
                
                // 使用默认源位置（可以通过参数服务器设置）
                pick_params.source_x = 0.0;
                pick_params.source_y = -0.4;
                pick_params.source_z = 0.13;

                // 读取安全高度参数（支持客户端通过参数服务器设置）
                double safe_h = 0.23;
                this->get_parameter_or<double>("pick.safe_approach_height", safe_h, 0.23);
                pick_params.safe_approach_height = safe_h;
                
                task = mtc_tutorial::build_pick_task(node, pick_params);
                
            } else if (task_type == "pour") {
                RCLCPP_INFO(this->get_logger(), "🔧 构建Pour任务...");
                mtc_tutorial::PourOnlyTaskParams pour_params;
                
                pour_params.tilt_start_deg = goal->tilt_start_deg;
                pour_params.tilt_end_deg = goal->tilt_end_deg;
                pour_params.tilt_speed_deg_s = goal->tilt_speed_deg_s;
                pour_params.pour_hold_sec = goal->pour_hold_sec;
                pour_params.move_to_pour_min = 0.08;
                pour_params.move_to_pour_max = 0.15;
                pour_params.plan_only = goal->plan_only;
                // 读取：倾倒目标位置 (保持姿态，仅控制位置)
                // 支持通过 pour.object_id 选择对象位置作为目标（优先使用），回退到参数中的 origin，再回退到静态参数
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
                            RCLCPP_INFO(this->get_logger(), "🎯 pour 使用对象 %s 的位置作为目标(%.3f, %.3f, %.3f)", p_oid.c_str(), pour_params.target_x, pour_params.target_y, pour_params.target_z);
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
                                RCLCPP_INFO(this->get_logger(), "🎯 pour 使用参数中的原始位置作为目标(%.3f, %.3f, %.3f)", ox, oy, oz);
                            } else {
                                pour_params.target_x = this->get_parameter("pour.target_x").as_double();
                                pour_params.target_y = this->get_parameter("pour.target_y").as_double();
                                pour_params.target_z = this->get_parameter("pour.target_z").as_double();
                                RCLCPP_WARN(this->get_logger(), "pour: 未找到对象 %s 位姿/原始位置，使用静态参数", p_oid.c_str());
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
                        origin_pose.position.z = 0.16; // 固定Z=0.16
                        place_params.target_pose = origin_pose;
                        RCLCPP_INFO(this->get_logger(), "📍 Place回到初始位置(%.3f, %.3f, %.3f)",
                                   origin_pose.position.x, origin_pose.position.y, origin_pose.position.z);
                    } else {
                        // 回退：从参数表读取 setup_planning_scene 写入的原始位置
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
                            RCLCPP_INFO(this->get_logger(), "Place回到参数中的原始位置(%.3f, %.3f, %.3f)", ox, oy, 0.16);
                        } else {
                            RCLCPP_WARN(this->get_logger(), "未在场景/参数中找到 %s 的原始位姿，使用默认放置点", place_object_id.c_str());
                        }
                    }
                } else {
                    try {
                        geometry_msgs::msg::Pose p;
                        p.position.x = this->get_parameter("place.target_x").as_double();
                        p.position.y = this->get_parameter("place.target_y").as_double();
                        (void)this; // 保持接口，但强制固定为0.16
                        p.position.z = 0.161;
                        p.orientation.w = 1.0;
                        place_params.target_pose = p; // 若未设置将被默认覆盖
                        RCLCPP_INFO(this->get_logger(), "📍 Place到指定点(%.3f, %.3f, %.3f)", p.position.x, p.position.y, p.position.z);
                    } catch (...) {
                        // 保持默认
                    }
                }
                
                task = mtc_tutorial::build_place_task(node, place_params);
                
            } else if (task_type == "return") {
                RCLCPP_INFO(this->get_logger(), "🔧 构建Return任务...");
                mtc_tutorial::ReturnTaskParams return_params;
                
                return_params.plan_only = goal->plan_only;
                return_params.timeout_sec = 15.0;
                
                task = mtc_tutorial::build_return_task(node, return_params);
                
            } else if (task_type == "move_to_pour") {
                RCLCPP_INFO(this->get_logger(), "🔧 构建简化MoveToPour任务...");
                mtc_tutorial::MoveToPourTaskParams move_to_pour_params;
                
                // 读取核心参数
                move_to_pour_params.target_x = this->get_parameter("move_to_pour.target_x").as_double();
                move_to_pour_params.target_y = this->get_parameter("move_to_pour.target_y").as_double();
                move_to_pour_params.target_z = this->get_parameter("move_to_pour.target_z").as_double();
                move_to_pour_params.velocity_scaling = this->get_parameter("move_to_pour.velocity_scaling").as_double();
                move_to_pour_params.timeout_sec = this->get_parameter("move_to_pour.timeout_sec").as_double();
                
                // 自动调整加速度（如果客户端提供了加速度参数则使用）
                try {
                    move_to_pour_params.acceleration_scaling = this->get_parameter("move_to_pour.acceleration_scaling").as_double();
                } catch (...) {
                    // 使用基于速度的自动计算
                    move_to_pour_params.acceleration_scaling = std::min(0.5, move_to_pour_params.velocity_scaling * 2.0);
                }
                
                // 如果指定了对象ID，则使用对象位置作为目标
                try {
                    std::string tgt_oid = this->get_parameter("move_to_pour.object_id").as_string();
                    if (!tgt_oid.empty()) {
                        moveit::planning_interface::PlanningSceneInterface psi;
                        auto objs = psi.getObjects({ tgt_oid });
                        auto it = objs.find(tgt_oid);
                        if (it != objs.end() && !it->second.primitive_poses.empty()) {
                            const auto& p = it->second.primitive_poses.front();
                            // 如果PSI返回的位姿为(0,0,0)，则尝试回退到place.origin参数
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
                                    move_to_pour_params.target_x = ox;           // x 不变
                                    move_to_pour_params.target_y = oy + 0.04;    // y 增加 0.02m
                                    move_to_pour_params.target_z = 0.26;         // z 固定为 0.25m
                                    RCLCPP_WARN(this->get_logger(),
                                                "PSI返回(0,0,0)，回退使用place.origin.%s并应用偏置 -> (%.3f, %.3f, %.3f)",
                                                tgt_oid.c_str(),
                                                move_to_pour_params.target_x,
                                                move_to_pour_params.target_y,
                                                move_to_pour_params.target_z);
                                } else {
                                    // 无法回退，仍按PSI(0,0,0)使用偏置
                                    move_to_pour_params.target_x = p.position.x;           // x 不变
                                    move_to_pour_params.target_y = p.position.y + 0.01;    // y 偏置增加 0.02m
                                    move_to_pour_params.target_z = 0.26;                   // z 固定为 0.26m
                                    RCLCPP_WARN(this->get_logger(),
                                                "PSI返回(0,0,0)，且无place.origin.%s，继续按PSI并应用偏置 -> (%.3f, %.3f, %.3f)",
                                                tgt_oid.c_str(),
                                                move_to_pour_params.target_x,
                                                move_to_pour_params.target_y,
                                                move_to_pour_params.target_z);
                                }
                            } else {
                                move_to_pour_params.target_x = p.position.x;           // x 不变
                                move_to_pour_params.target_y = p.position.y + 0.01;    // y 增加 0.002m
                                move_to_pour_params.target_z = 0.30;                   // z 固定为 0.30m
                                RCLCPP_INFO(this->get_logger(), "🎯 move_to_pour 使用对象 %s 的位置并应用偏置 -> (%.3f, %.3f, %.3f)",
                                            tgt_oid.c_str(), move_to_pour_params.target_x,
                                            move_to_pour_params.target_y, move_to_pour_params.target_z);
                            }
                        } else {
                            // 回退：若 PSI 不可用，尝试使用参数中的原始位置
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
                                RCLCPP_INFO(this->get_logger(), "🎯 move_to_pour 使用参数中的原始位置并应用偏置 -> (%.3f, %.3f, %.3f)",
                                            move_to_pour_params.target_x,
                                            move_to_pour_params.target_y,
                                            move_to_pour_params.target_z);
                            } else {
                                RCLCPP_WARN(this->get_logger(), "move_to_pour: 未找到对象 %s 的位姿/原始位置，使用现有坐标(%.3f, %.3f, %.3f)",
                                            tgt_oid.c_str(), move_to_pour_params.target_x,
                                            move_to_pour_params.target_y, move_to_pour_params.target_z);
                            }
                        }
                    }
                } catch (...) {}

                // 读取：融合后的可选倾倒参数
                move_to_pour_params.pour_execute = this->get_parameter("move_to_pour.pour_execute").as_bool();
                move_to_pour_params.tilt_start_deg = this->get_parameter("move_to_pour.tilt_start_deg").as_double();
                move_to_pour_params.tilt_end_deg = this->get_parameter("move_to_pour.tilt_end_deg").as_double();
                move_to_pour_params.tilt_speed_deg_s = this->get_parameter("move_to_pour.tilt_speed_deg_s").as_double();
                move_to_pour_params.pour_hold_sec = this->get_parameter("move_to_pour.pour_hold_sec").as_double();
                
                // 读取：递给用户相关参数
                move_to_pour_params.execute_give = this->get_parameter("move_to_pour.execute_give").as_bool();
                move_to_pour_params.gripper_open_ratio = this->get_parameter("move_to_pour.gripper_open_ratio").as_double();
                
                move_to_pour_params.plan_only = goal->plan_only;
                
                RCLCPP_INFO(this->get_logger(), "📝 简化参数: 目标(%.2f, %.2f, %.2f), 速度%.2f, 加速度%.2f, 倾倒=%s", 
                           move_to_pour_params.target_x, move_to_pour_params.target_y, move_to_pour_params.target_z,
                           move_to_pour_params.velocity_scaling, move_to_pour_params.acceleration_scaling,
                           move_to_pour_params.pour_execute ? "true" : "false");
                
                task = mtc_tutorial::build_move_to_pour_task(node, move_to_pour_params);
                
            } else {
                RCLCPP_ERROR(this->get_logger(), "未知的任务类型: %s", task_type.c_str());
                return false;
            }
            
            RCLCPP_INFO(this->get_logger(), "✅ %s任务构建成功: %s", 
                       task_type.c_str(), task.stages()->name().c_str());
            return true;
            
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "❌ 构建%s任务时发生异常: %s", task_type.c_str(), e.what());
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