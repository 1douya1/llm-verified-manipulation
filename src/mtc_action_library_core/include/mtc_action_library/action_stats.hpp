#pragma once

#include <string>
#include <chrono>
#include <nlohmann/json.hpp>

namespace mtc_action_library {

/**
 * @brief 动作统计信息
 */
struct ActionStats {
    std::string action_name;
    size_t total_executions{0};
    size_t successful_executions{0};
    double total_duration_sec{0.0};
    double average_duration_sec{0.0};
    double success_rate{0.0};
    std::chrono::system_clock::time_point last_execution_time;
    
    /**
     * @brief 转换为JSON格式
     */
    nlohmann::json toJson() const {
        nlohmann::json j;
        j["action_name"] = action_name;
        j["total_executions"] = total_executions;
        j["successful_executions"] = successful_executions;
        j["total_duration_sec"] = total_duration_sec;
        j["average_duration_sec"] = average_duration_sec;
        j["success_rate"] = success_rate;
        
        // 转换时间为字符串
        auto time_t = std::chrono::system_clock::to_time_t(last_execution_time);
        j["last_execution_time"] = std::ctime(&time_t);
        
        return j;
    }
};

/**
 * @brief 执行日志记录
 */
struct ExecutionLog {
    std::chrono::system_clock::time_point timestamp;
    std::string action_name;
    bool success{false};
    double duration_sec{0.0};
    std::string error_msg;
    
    /**
     * @brief 转换为JSON格式
     */
    nlohmann::json toJson() const {
        nlohmann::json j;
        auto time_t = std::chrono::system_clock::to_time_t(timestamp);
        j["timestamp"] = std::ctime(&time_t);
        j["action_name"] = action_name;
        j["success"] = success;
        j["duration_sec"] = duration_sec;
        j["error_msg"] = error_msg;
        return j;
    }
};

} // namespace mtc_action_library








