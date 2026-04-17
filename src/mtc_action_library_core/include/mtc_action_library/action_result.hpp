#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace mtc_action_library {

/**
 * @brief 动作执行结果
 */
struct ActionResult {
    bool success{false};
    double duration_sec{0.0};
    std::string error_msg;
    int error_code{0};
    
    // Debug信息
    std::vector<std::string> stage_feedback;  // 各阶段反馈
    size_t num_solutions{0};
    std::string planning_time_breakdown;      // 规划耗时分解
    
    /**
     * @brief 转换为JSON格式
     */
    nlohmann::json toJson() const {
        nlohmann::json j;
        j["success"] = success;
        j["duration_sec"] = duration_sec;
        j["error_msg"] = error_msg;
        j["error_code"] = error_code;
        j["stage_feedback"] = stage_feedback;
        j["num_solutions"] = num_solutions;
        j["planning_time_breakdown"] = planning_time_breakdown;
        return j;
    }
    
    /**
     * @brief 转换为字符串表示
     */
    std::string toString() const {
        std::string emoji = success ? "✅" : "❌";
        return emoji + " Duration: " + std::to_string(duration_sec) + "s";
    }
};

} // namespace mtc_action_library








