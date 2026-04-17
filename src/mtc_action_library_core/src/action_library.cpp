#include "mtc_action_library/action_library.hpp"
#include "mtc_action_library/task_builders.hpp"
#include <moveit/task_constructor/task.h>
#include <fstream>
#include <chrono>
#include <limits>
#include <cmath>

namespace mtc = moveit::task_constructor;

namespace mtc_action_library {

// =============================================================================
// ActionLibrary Implementation (Pimpl Pattern)
// =============================================================================

class ActionLibrary::Impl {
public:
    explicit Impl(const rclcpp::Node::SharedPtr& node)
        : node_(node)
    {
        RCLCPP_INFO(node_->get_logger(), "Initializing Action Library");
        
        // 注册所有可用动作
        available_actions_ = {"pick", "place", "move_to_pour", "return_home"};
        
        // 初始化统计
        for (const auto& action : available_actions_) {
            ActionStats stats;
            stats.action_name = action;
            stats_[action] = stats;
        }
        
        RCLCPP_INFO(node_->get_logger(), "Action Library initialized with %zu actions", 
                    available_actions_.size());
    }
    
    ActionResult execute(
        const std::string& action_name,
        const ActionParams& params,
        std::function<void(const std::string&)> feedback_callback)
    {
        auto start_time = std::chrono::steady_clock::now();
        ActionResult result;
        result.success = false;
        
        // 检查动作是否存在
        if (std::find(available_actions_.begin(), available_actions_.end(), action_name) == available_actions_.end()) {
            result.error_msg = "Unknown action: " + action_name;
            result.error_code = -1;
            result.duration_sec = 0.0;
            return result;
        }
        
        try {
            // 发送反馈
            if (feedback_callback) {
                feedback_callback("Starting " + action_name + " action");
            }
            
            // 构建任务
            mtc::Task task;
            bool task_built = false;
            
            if (action_name == "pick") {
                task = buildPickTask(params, feedback_callback);
                task_built = true;
            } else if (action_name == "move_to_pour") {
                task = buildMoveToPourTask(params, feedback_callback);
                task_built = true;
            } else if (action_name == "place") {
                task = buildPlaceTask(params, feedback_callback);
                task_built = true;
            } else if (action_name == "return_home") {
                task = buildReturnTask(params, feedback_callback);
                task_built = true;
            }
            
            if (!task_built) {
                result.error_msg = "Failed to build task for action: " + action_name;
                result.error_code = -2;
                auto end_time = std::chrono::steady_clock::now();
                result.duration_sec = std::chrono::duration<double>(end_time - start_time).count();
                logExecution(action_name, result);
                return result;
            }
            
            // 规划
            if (feedback_callback) {
                feedback_callback("Planning " + action_name);
            }
            
            try {
                task.init();
            } catch (const std::exception& e) {
                result.error_msg = std::string("Task initialization failed: ") + e.what();
                result.error_code = -3;
                auto end_time = std::chrono::steady_clock::now();
                result.duration_sec = std::chrono::duration<double>(end_time - start_time).count();
                logExecution(action_name, result);
                return result;
            }
            
            if (feedback_callback) {
                feedback_callback("Task initialized, planning...");
            }
            
            // 使用params中的max_solutions参数进行规划（关键性能优化）
            auto plan_result = task.plan(params.max_solutions);
            if (!plan_result) {
                result.error_msg = "Planning failed";
                result.error_code = plan_result.val;
                auto end_time = std::chrono::steady_clock::now();
                result.duration_sec = std::chrono::duration<double>(end_time - start_time).count();
                logExecution(action_name, result);
                return result;
            }
            
            result.num_solutions = task.numSolutions();
            result.stage_feedback.push_back("Planning succeeded with " + std::to_string(result.num_solutions) + " solutions");
            
            // 执行（如果不是plan_only模式）
            if (!params.plan_only) {
                if (feedback_callback) {
                    feedback_callback("Executing " + action_name);
                }
                
                // 获取第一个解决方案并执行
                if (result.num_solutions > 0) {
                    auto solution = task.solutions().front();
                    auto exec_result = task.execute(*solution);
                    if (exec_result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
                        result.error_msg = "Execution failed";
                        result.error_code = exec_result.val;
                        result.success = false;
                    } else {
                        result.success = true;
                        result.stage_feedback.push_back("Execution succeeded");
                    }
                } else {
                    result.error_msg = "No solutions available for execution";
                    result.error_code = -4;
                    result.success = false;
                }
            } else {
                result.success = true;
                result.stage_feedback.push_back("Plan-only mode: execution skipped");
            }
            
        } catch (const std::exception& e) {
            result.error_msg = std::string("Exception: ") + e.what();
            result.error_code = -999;
            result.success = false;
        }
        
        // 计算执行时间
        auto end_time = std::chrono::steady_clock::now();
        result.duration_sec = std::chrono::duration<double>(end_time - start_time).count();
        
        // 记录执行日志
        logExecution(action_name, result);
        
        // 更新统计
        updateStats(action_name, result);
        
        if (feedback_callback) {
            if (result.success) {
                feedback_callback(action_name + " completed successfully");
            } else {
                feedback_callback(action_name + " failed: " + result.error_msg);
            }
        }
        
        return result;
    }
    
    std::vector<std::string> getActionList() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return available_actions_;
    }
    
    ActionStats getStats(const std::string& action_name) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = stats_.find(action_name);
        if (it != stats_.end()) {
            return it->second;
        }
        return ActionStats();
    }
    
    std::unordered_map<std::string, ActionStats> getAllStats() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return stats_;
    }
    
    std::vector<ExecutionLog> getHistory(size_t limit) const {
        std::lock_guard<std::mutex> lock(mutex_);
        size_t start = (execution_log_.size() > limit) ? (execution_log_.size() - limit) : 0;
        return std::vector<ExecutionLog>(execution_log_.begin() + start, execution_log_.end());
    }
    
    void exportDebugReport(const std::string& filepath) const {
        std::lock_guard<std::mutex> lock(mutex_);
        
        nlohmann::json report;
        report["export_time"] = std::chrono::system_clock::now().time_since_epoch().count();
        
        // 统计信息
        nlohmann::json stats_json;
        for (const auto& [name, stats] : stats_) {
            stats_json[name] = stats.toJson();
        }
        report["stats"] = stats_json;
        
        // 执行历史
        nlohmann::json history_json = nlohmann::json::array();
        for (const auto& log : execution_log_) {
            history_json.push_back(log.toJson());
        }
        report["execution_history"] = history_json;
        
        // 写入文件
        std::ofstream file(filepath);
        file << report.dump(2);
        file.close();
        
        RCLCPP_INFO(node_->get_logger(), "Debug report exported to: %s", filepath.c_str());
    }
    
    void clearHistory() {
        std::lock_guard<std::mutex> lock(mutex_);
        execution_log_.clear();
        RCLCPP_INFO(node_->get_logger(), "Execution history cleared");
    }
    
    void resetAllStats() {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& [name, stats] : stats_) {
            stats = ActionStats();
            stats.action_name = name;
        }
        RCLCPP_INFO(node_->get_logger(), "All statistics reset");
    }

private:
    mtc::Task buildPickTask(const ActionParams& params, std::function<void(const std::string&)> /* feedback */) {
        PickTaskParams p;
        if (!params.object_id.empty()) {
            p.object_id = params.object_id;
        }
        p.plan_only = params.plan_only;
        p.params = params;  // 传递完整的params配置
        return build_pick_task(node_, p);
    }
    
    mtc::Task buildMoveToPourTask(const ActionParams& params, std::function<void(const std::string&)> /* feedback */) {
        MoveToPourTaskParams p;
        if (!params.object_id.empty()) {
            p.object_id = params.object_id;
        }
        const auto getNumericOrString = [&](const std::string& key, double default_value) {
            auto itn = params.numeric_params.find(key);
            if (itn != params.numeric_params.end()) return itn->second;
            auto its = params.string_params.find(key);
            if (its != params.string_params.end()) {
                try { return std::stod(its->second); } catch (...) {}
            }
            return default_value;
        };
        const bool has_target_qx = params.numeric_params.find("target_qx") != params.numeric_params.end();
        const bool has_target_qy = params.numeric_params.find("target_qy") != params.numeric_params.end();
        const bool has_target_qz = params.numeric_params.find("target_qz") != params.numeric_params.end();
        const bool has_target_qw = params.numeric_params.find("target_qw") != params.numeric_params.end();
        const bool has_any_target_quat = has_target_qx || has_target_qy || has_target_qz || has_target_qw;
        p.target_x = getNumericOrString("target_x", p.target_x);
        p.target_y = getNumericOrString("target_y", p.target_y);
        p.target_z = getNumericOrString("target_z", p.target_z);
        p.target_qx = getNumericOrString("target_qx", p.target_qx);
        p.target_qy = getNumericOrString("target_qy", p.target_qy);
        p.target_qz = getNumericOrString("target_qz", p.target_qz);
        p.target_qw = getNumericOrString("target_qw", p.target_qw);
        p.maintain_current_orientation = !has_any_target_quat;
        p.cartesian_only = getNumericOrString("cartesian_only", 0.0) > 0.5;
        p.velocity_scaling = params.getNumeric("velocity_scaling", 0.15);
        p.timeout_sec = params.getNumeric("timeout_sec", p.timeout_sec);
        p.acceleration_scaling = params.getNumeric("acceleration_scaling", p.acceleration_scaling);
        p.min_cartesian_fraction = params.getNumeric("min_cartesian_fraction", p.min_cartesian_fraction);
        p.tilt_start_deg = params.getNumeric("tilt_start_deg", p.tilt_start_deg);
        p.tilt_end_deg = params.getNumeric("tilt_end_deg", p.tilt_end_deg);
        p.tilt_speed_deg_s = params.getNumeric("tilt_speed_deg_s", p.tilt_speed_deg_s);
        p.pour_hold_sec = params.getNumeric("pour_hold_sec", p.pour_hold_sec);
        p.pour_execute = params.getNumeric("pour_execute", 1.0) > 0.5;
        p.execute_give = params.getNumeric("execute_give", 0.0) > 0.5;
        p.gripper_open_ratio = params.getNumeric("gripper_open_ratio", p.gripper_open_ratio);
        p.plan_only = params.plan_only;
        p.params = params;  // 传递完整的params配置
        RCLCPP_INFO(
            node_->get_logger(),
            "move_to_pour params resolved: target=(%.3f, %.3f, %.3f) cartesian_only=%s numeric_params=%zu string_params=%zu",
            p.target_x, p.target_y, p.target_z, p.cartesian_only ? "true" : "false",
            params.numeric_params.size(), params.string_params.size());
        return build_move_to_pour_task(node_, p);
    }
    
    mtc::Task buildPlaceTask(const ActionParams& params, std::function<void(const std::string&)> /* feedback */) {
        PlaceTaskParams p;
        const auto getNumericOrString = [&](const std::string& key, double default_value) {
            auto itn = params.numeric_params.find(key);
            if (itn != params.numeric_params.end()) return itn->second;
            auto its = params.string_params.find(key);
            if (its != params.string_params.end()) {
                try { return std::stod(its->second); } catch (...) {}
            }
            return default_value;
        };

        if (!params.object_id.empty()) {
            p.object_id = params.object_id;
        }
        const bool return_to_origin = getNumericOrString("return_to_origin", 0.0) > 0.5;

        // 1) 优先使用显式的target_x/y/z
        const double tx = getNumericOrString("target_x", std::numeric_limits<double>::quiet_NaN());
        const double ty = getNumericOrString("target_y", std::numeric_limits<double>::quiet_NaN());
        const double tz = getNumericOrString("target_z", std::numeric_limits<double>::quiet_NaN());
        if (!std::isnan(tx) && !std::isnan(ty) && !std::isnan(tz)) {
            geometry_msgs::msg::Pose pose;
            pose.position.x = tx;
            pose.position.y = ty;
            pose.position.z = tz;
            pose.orientation.w = 1.0;
            p.target_pose = pose;
            RCLCPP_INFO(node_->get_logger(),
                        "place params resolved: explicit target=(%.3f, %.3f, %.3f)",
                        tx, ty, tz);
        } else if (return_to_origin && !p.object_id.empty()) {
            // 2) 否则在return_to_origin模式下使用 place.origin.<object_id>.*
            const std::string prefix = "place.origin." + p.object_id + ".";
            double ox = std::numeric_limits<double>::quiet_NaN();
            double oy = std::numeric_limits<double>::quiet_NaN();
            double oz = std::numeric_limits<double>::quiet_NaN();
            node_->get_parameter_or<double>(prefix + "x", ox, ox);
            node_->get_parameter_or<double>(prefix + "y", oy, oy);
            node_->get_parameter_or<double>(prefix + "z", oz, oz);
            if (!std::isnan(ox) && !std::isnan(oy) && !std::isnan(oz)) {
                geometry_msgs::msg::Pose pose;
                pose.position.x = ox;
                pose.position.y = oy;
                pose.position.z = oz;
                pose.orientation.w = 1.0;
                p.target_pose = pose;
                RCLCPP_INFO(node_->get_logger(),
                            "place params resolved: return_to_origin from %s -> (%.3f, %.3f, %.3f)",
                            prefix.c_str(), ox, oy, oz);
            } else {
                RCLCPP_WARN(node_->get_logger(),
                            "place return_to_origin requested but %s{x,y,z} not found; fallback to default place pose",
                            prefix.c_str());
            }
        }
        p.plan_only = params.plan_only;
        p.params = params;  // 传递完整的params配置
        return build_place_task(node_, p);
    }
    
    mtc::Task buildReturnTask(const ActionParams& params, std::function<void(const std::string&)> /* feedback */) {
        ReturnTaskParams p;
        p.plan_only = params.plan_only;
        p.params = params;  // 传递完整的params配置
        return build_return_task(node_, p);
    }
    
    void logExecution(const std::string& action_name, const ActionResult& result) {
        ExecutionLog log;
        log.timestamp = std::chrono::system_clock::now();
        log.action_name = action_name;
        log.success = result.success;
        log.duration_sec = result.duration_sec;
        log.error_msg = result.error_msg;
        
        execution_log_.push_back(log);
        
        // 限制历史大小
        if (execution_log_.size() > max_log_size_) {
            execution_log_.erase(execution_log_.begin());
        }
    }
    
    void updateStats(const std::string& action_name, const ActionResult& result) {
        auto& stats = stats_[action_name];
        stats.total_executions++;
        stats.total_duration_sec += result.duration_sec;
        stats.average_duration_sec = stats.total_duration_sec / stats.total_executions;
        
        if (result.success) {
            stats.successful_executions++;
        }
        
        stats.success_rate = static_cast<double>(stats.successful_executions) / stats.total_executions;
        stats.last_execution_time = std::chrono::system_clock::now();
    }
    
    rclcpp::Node::SharedPtr node_;
    std::vector<std::string> available_actions_;
    std::unordered_map<std::string, ActionStats> stats_;
    std::vector<ExecutionLog> execution_log_;
    size_t max_log_size_{1000};
    mutable std::mutex mutex_;
};

// =============================================================================
// ActionLibrary Public Interface
// =============================================================================

ActionLibrary::ActionLibrary(const rclcpp::Node::SharedPtr& node)
    : impl_(std::make_unique<Impl>(node))
{
}

ActionLibrary::~ActionLibrary() = default;

ActionResult ActionLibrary::execute(
    const std::string& action_name,
    const ActionParams& params,
    std::function<void(const std::string&)> feedback_callback)
{
    return impl_->execute(action_name, params, feedback_callback);
}

std::vector<std::string> ActionLibrary::getActionList() const {
    return impl_->getActionList();
}

ActionStats ActionLibrary::getStats(const std::string& action_name) const {
    return impl_->getStats(action_name);
}

std::unordered_map<std::string, ActionStats> ActionLibrary::getAllStats() const {
    return impl_->getAllStats();
}

std::vector<ExecutionLog> ActionLibrary::getHistory(size_t limit) const {
    return impl_->getHistory(limit);
}

void ActionLibrary::exportDebugReport(const std::string& filepath) const {
    impl_->exportDebugReport(filepath);
}

void ActionLibrary::clearHistory() {
    impl_->clearHistory();
}

void ActionLibrary::resetAllStats() {
    impl_->resetAllStats();
}

} // namespace mtc_action_library

