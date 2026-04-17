#pragma once

#include <string>
#include <unordered_map>
#include <optional>
#include <geometry_msgs/msg/pose.hpp>
#include <nlohmann/json.hpp>

namespace mtc_action_library {

/**
 * @brief 动作执行参数
 */
struct ActionParams {
    // === 基础参数 ===
    std::string object_id;
    std::optional<geometry_msgs::msg::Pose> target_pose;
    std::unordered_map<std::string, double> numeric_params;
    std::unordered_map<std::string, std::string> string_params;
    bool plan_only{false};
    
    // === Task级别参数 ===
    size_t max_solutions{1};  // 默认只找1个解（关键优化！）
    
    // === Planner级别参数 ===
    double planner_timeout{3.0};              // 规划器超时（秒），来自mtc_tutorial
    double velocity_scaling{0.3};             // 速度缩放（mtc_tutorial值）
    double acceleration_scaling{0.5};         // 加速度缩放（mtc_tutorial值）
    
    // === IK级别参数 ===
    uint32_t max_ik_solutions{2};             // 每个IK最多2个解（mtc_tutorial值）
    double min_solution_distance{0.5};        // IK解之间最小距离（mtc_tutorial值）
    double ik_timeout{8.0};                   // IK超时（mtc_tutorial值）
    
    // === Cartesian级别参数 ===
    double cartesian_step_size{0.008};        // 笛卡尔步长（mtc_tutorial值）
    double cartesian_jump_threshold{0.0};     // 跳跃阈值（mtc_tutorial值：禁用）
    
    // === Stage级别参数 ===
    double connect_timeout{15.0};             // Connect阶段超时（mtc_tutorial值）
    
    /**
     * @brief 从JSON字符串创建参数对象
     */
    static ActionParams fromJson(const std::string& json_str) {
        ActionParams params;
        try {
            auto j = nlohmann::json::parse(json_str);
            if (j.contains("object_id")) {
                params.object_id = j["object_id"].get<std::string>();
            }
            if (j.contains("plan_only")) {
                params.plan_only = j["plan_only"].get<bool>();
            }
            if (j.contains("numeric_params")) {
                params.numeric_params = j["numeric_params"].get<std::unordered_map<std::string, double>>();
            }
            if (j.contains("string_params")) {
                params.string_params = j["string_params"].get<std::unordered_map<std::string, std::string>>();
            }
        } catch (const std::exception&) {
            // 解析失败，返回默认参数
        }
        return params;
    }
    
    /**
     * @brief 转换为JSON字符串
     */
    std::string toJson() const {
        nlohmann::json j;
        j["object_id"] = object_id;
        j["plan_only"] = plan_only;
        j["numeric_params"] = numeric_params;
        j["string_params"] = string_params;
        return j.dump();
    }
    
    /**
     * @brief 获取数值参数（带默认值）
     */
    double getNumeric(const std::string& key, double default_value = 0.0) const {
        auto it = numeric_params.find(key);
        return (it != numeric_params.end()) ? it->second : default_value;
    }
    
    /**
     * @brief 获取字符串参数（带默认值）
     */
    std::string getString(const std::string& key, const std::string& default_value = "") const {
        auto it = string_params.find(key);
        return (it != string_params.end()) ? it->second : default_value;
    }
};

} // namespace mtc_action_library



