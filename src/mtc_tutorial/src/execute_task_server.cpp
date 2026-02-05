#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <mtc_interface/mtc_interface/action/execute_task.hpp>

#include <moveit/task_constructor/task.h>
#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <mtc_tutorial/modular_task_builders.hpp>
#include <nlohmann/json.hpp>

namespace mtc = moveit::task_constructor;
using ExecuteTask = mtc_interface::action::ExecuteTask;
using GoalHandleET = rclcpp_action::ServerGoalHandle<ExecuteTask>;
using json = nlohmann::json;

class MTCTaskServer : public rclcpp::Node {
public:
    MTCTaskServer() : Node("execute_task_server") {
        server_ = rclcpp_action::create_server<ExecuteTask>(
            this, "execute_task",
            std::bind(&MTCTaskServer::handle_goal, this, std::placeholders::_1, std::placeholders::_2),
            std::bind(&MTCTaskServer::handle_cancel, this, std::placeholders::_1),
            std::bind(&MTCTaskServer::handle_accepted, this, std::placeholders::_1));
        
        RCLCPP_INFO(this->get_logger(), "MTC通用任务执行服务器已启动");
    }

private:
    rclcpp_action::Server<ExecuteTask>::SharedPtr server_;
    bool cancel_requested_ = false;

    rclcpp_action::GoalResponse handle_goal(
        const rclcpp_action::GoalUUID & uuid,
        std::shared_ptr<const ExecuteTask::Goal> goal) {
        
        RCLCPP_INFO(this->get_logger(), "收到任务执行请求: 类型=%s", goal->task_type.c_str());
        
        // 验证任务类型
        if (goal->task_type != "pick" && goal->task_type != "pour" && 
            goal->task_type != "place" && goal->task_type != "return" &&
            goal->task_type != "cartesian_pour") {
            RCLCPP_ERROR(this->get_logger(), "不支持的任务类型: %s", goal->task_type.c_str());
            return rclcpp_action::GoalResponse::REJECT;
        }
        
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    rclcpp_action::CancelResponse handle_cancel(
        const std::shared_ptr<GoalHandleET> goal_handle) {
        RCLCPP_INFO(this->get_logger(), "收到取消任务请求");
        cancel_requested_ = true;
        return rclcpp_action::CancelResponse::ACCEPT;
    }

    void handle_accepted(std::shared_ptr<GoalHandleET> goal_handle) {
        std::thread([this, goal_handle]() {
            auto goal = goal_handle->get_goal();
            auto feedback = std::make_shared<ExecuteTask::Feedback>();
            auto result = std::make_shared<ExecuteTask::Result>();
            
            cancel_requested_ = false;
            
            try {
                RCLCPP_INFO(this->get_logger(), "开始执行%s任务", goal->task_type.c_str());
                
                // 解析任务参数
                json task_params;
                try {
                    task_params = json::parse(goal->task_params_json);
                } catch (const std::exception& e) {
                    result->success = false;
                    result->error_msg = std::string("参数解析失败: ") + e.what();
                    goal_handle->abort(result);
                    return;
                }
                
                // 构建任务
                mtc::Task task;
                if (!build_task(goal->task_type, task_params, task, goal->plan_only)) {
                    result->success = false;
                    result->error_msg = "任务构建失败";
                    goal_handle->abort(result);
                    return;
                }
                
                // 发布反馈：开始规划
                feedback->stage = "planning";
                feedback->progress = 0.1f;
                feedback->current_status = "正在规划任务...";
                goal_handle->publish_feedback(feedback);
                
                // 初始化任务
                if (!task.init()) {
                    result->success = false;
                    result->error_msg = "任务初始化失败";
                    goal_handle->abort(result);
                    return;
                }
                
                // 规划任务
                feedback->stage = "planning";
                feedback->progress = 0.3f;
                feedback->current_status = "正在生成轨迹...";
                goal_handle->publish_feedback(feedback);
                
                if (!task.plan(2)) {
                    result->success = false;
                    result->error_msg = "任务规划失败";
                    goal_handle->abort(result);
                    return;
                }
                
                // 发布反馈：规划完成
                feedback->stage = "planned";
                feedback->progress = 0.5f;
                feedback->current_status = "规划完成";
                goal_handle->publish_feedback(feedback);
                
                // 检查是否仅规划
                if (goal->plan_only) {
                    result->success = true;
                    result->error_msg = "";
                    result->duration_sec = 0.0;
                    feedback->stage = "completed";
                    feedback->progress = 1.0f;
                    feedback->current_status = "规划完成（仅规划模式）";
                    goal_handle->publish_feedback(feedback);
                    goal_handle->succeed(result);
                    return;
                }
                
                // 检查取消请求
                if (cancel_requested_) {
                    result->success = false;
                    result->error_msg = "任务在执行前被取消";
                    goal_handle->canceled(result);
                    return;
                }
                
                // 执行任务
                feedback->stage = "executing";
                feedback->progress = 0.7f;
                feedback->current_status = "正在执行任务...";
                goal_handle->publish_feedback(feedback);
                
                auto start_time = std::chrono::steady_clock::now();
                const auto& solution = *task.solutions().front();
                auto exec_result = task.execute(solution);
                auto end_time = std::chrono::steady_clock::now();
                
                auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
                result->duration_sec = duration.count() / 1000.0;
                
                // 检查执行结果
                if (exec_result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
                    result->success = false;
                    result->error_msg = "任务执行失败，错误代码: " + std::to_string(exec_result.val);
                    goal_handle->abort(result);
                    return;
                }
                
                // 成功完成
                result->success = true;
                result->error_msg = "";
                feedback->stage = "completed";
                feedback->progress = 1.0f;
                feedback->current_status = "任务执行完成";
                goal_handle->publish_feedback(feedback);
                goal_handle->succeed(result);
                
                RCLCPP_INFO(this->get_logger(), "%s任务执行完成，耗时: %.2fs", 
                           goal->task_type.c_str(), result->duration_sec);
                
            } catch (const std::exception& e) {
                result->success = false;
                result->error_msg = std::string("任务执行异常: ") + e.what();
                goal_handle->abort(result);
                RCLCPP_ERROR(this->get_logger(), "任务执行异常: %s", e.what());
            }
        }).detach();
    }
    
    bool build_task(const std::string& task_type, const json& params, 
                    mtc::Task& task, bool plan_only) {
        auto node = this->shared_from_this();
        
        try {
            if (task_type == "pick") {
                mtc_tutorial::PickTaskParams pick_params;
                
                // 解析参数
                if (params.contains("source_x")) pick_params.source_x = params["source_x"];
                if (params.contains("source_y")) pick_params.source_y = params["source_y"];
                if (params.contains("source_z")) pick_params.source_z = params["source_z"];
                if (params.contains("source_qx")) pick_params.source_qx = params["source_qx"];
                if (params.contains("source_qy")) pick_params.source_qy = params["source_qy"];
                if (params.contains("source_qz")) pick_params.source_qz = params["source_qz"];
                if (params.contains("source_qw")) pick_params.source_qw = params["source_qw"];
                if (params.contains("approach_min")) pick_params.approach_min = params["approach_min"];
                if (params.contains("approach_max")) pick_params.approach_max = params["approach_max"];
                if (params.contains("lift_height")) pick_params.lift_height = params["lift_height"];
                if (params.contains("object_id")) pick_params.object_id = params["object_id"];
                pick_params.plan_only = plan_only;
                
                task = mtc_tutorial::build_pick_task(node, pick_params);
                
            } else if (task_type == "pour") {
                mtc_tutorial::PourOnlyTaskParams pour_params;
                
                if (params.contains("target_x")) pour_params.target_x = params["target_x"];
                if (params.contains("target_y")) pour_params.target_y = params["target_y"];
                if (params.contains("target_z")) pour_params.target_z = params["target_z"];
                if (params.contains("tilt_start_deg")) pour_params.tilt_start_deg = params["tilt_start_deg"];
                if (params.contains("tilt_end_deg")) pour_params.tilt_end_deg = params["tilt_end_deg"];
                if (params.contains("tilt_speed_deg_s")) pour_params.tilt_speed_deg_s = params["tilt_speed_deg_s"];
                if (params.contains("pour_hold_sec")) pour_params.pour_hold_sec = params["pour_hold_sec"];
                if (params.contains("move_to_pour_min")) pour_params.move_to_pour_min = params["move_to_pour_min"];
                if (params.contains("move_to_pour_max")) pour_params.move_to_pour_max = params["move_to_pour_max"];
                pour_params.plan_only = plan_only;
                
                task = mtc_tutorial::build_pour_only_task(node, pour_params);
                
            } else if (task_type == "cartesian_pour") {
                mtc_tutorial::CartesianPourOnlyTaskParams cartesian_pour_params;
                
                if (params.contains("target_x")) cartesian_pour_params.target_x = params["target_x"];
                if (params.contains("target_y")) cartesian_pour_params.target_y = params["target_y"];
                if (params.contains("target_z")) cartesian_pour_params.target_z = params["target_z"];
                if (params.contains("tilt_start_deg")) cartesian_pour_params.tilt_start_deg = params["tilt_start_deg"];
                if (params.contains("tilt_end_deg")) cartesian_pour_params.tilt_end_deg = params["tilt_end_deg"];
                if (params.contains("tilt_speed_deg_s")) cartesian_pour_params.tilt_speed_deg_s = params["tilt_speed_deg_s"];
                if (params.contains("pour_hold_sec")) cartesian_pour_params.pour_hold_sec = params["pour_hold_sec"];
                if (params.contains("maintain_orientation")) cartesian_pour_params.maintain_orientation = params["maintain_orientation"];
                if (params.contains("target_roll")) cartesian_pour_params.target_roll = params["target_roll"];
                if (params.contains("target_pitch")) cartesian_pour_params.target_pitch = params["target_pitch"];
                if (params.contains("target_yaw")) cartesian_pour_params.target_yaw = params["target_yaw"];
                cartesian_pour_params.plan_only = plan_only;
                
                task = mtc_tutorial::build_cartesian_pour_only_task(node, cartesian_pour_params);
                
            } else if (task_type == "place") {
                mtc_tutorial::PlaceTaskParams place_params;
                
                if (params.contains("lower_min")) place_params.lower_min = params["lower_min"];
                if (params.contains("lower_max")) place_params.lower_max = params["lower_max"];
                if (params.contains("retreat_min")) place_params.retreat_min = params["retreat_min"];
                if (params.contains("retreat_max")) place_params.retreat_max = params["retreat_max"];
                if (params.contains("object_id")) place_params.object_id = params["object_id"];
                place_params.plan_only = plan_only;
                
                // 处理目标位姿
                if (params.contains("target_pose")) {
                    geometry_msgs::msg::Pose target_pose;
                    auto pose_json = params["target_pose"];
                    if (pose_json.contains("position")) {
                        target_pose.position.x = pose_json["position"]["x"];
                        target_pose.position.y = pose_json["position"]["y"];
                        target_pose.position.z = pose_json["position"]["z"];
                    }
                    if (pose_json.contains("orientation")) {
                        target_pose.orientation.x = pose_json["orientation"]["x"];
                        target_pose.orientation.y = pose_json["orientation"]["y"];
                        target_pose.orientation.z = pose_json["orientation"]["z"];
                        target_pose.orientation.w = pose_json["orientation"]["w"];
                    }
                    place_params.target_pose = target_pose;
                }
                
                task = mtc_tutorial::build_place_task(node, place_params);
                
            } else if (task_type == "return") {
                mtc_tutorial::ReturnTaskParams return_params;
                
                if (params.contains("timeout_sec")) return_params.timeout_sec = params["timeout_sec"];
                return_params.plan_only = plan_only;
                
                // 处理目标关节
                if (params.contains("target_joints")) {
                    std::map<std::string, double> target_joints;
                    for (auto& [key, value] : params["target_joints"].items()) {
                        target_joints[key] = value;
                    }
                    return_params.target_joints = target_joints;
                }
                
                task = mtc_tutorial::build_return_task(node, return_params);
                
            } else {
                RCLCPP_ERROR(this->get_logger(), "未知的任务类型: %s", task_type.c_str());
                return false;
            }
            
            return true;
            
        } catch (const std::exception& e) {
            RCLCPP_ERROR(this->get_logger(), "构建%s任务时发生异常: %s", task_type.c_str(), e.what());
            return false;
        }
    }
};

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto server = std::make_shared<MTCTaskServer>();
    rclcpp::spin(server);
    rclcpp::shutdown();
    return 0;
} 