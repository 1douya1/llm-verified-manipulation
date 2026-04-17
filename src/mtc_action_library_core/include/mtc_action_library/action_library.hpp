#pragma once

#include "action_result.hpp"
#include "action_params.hpp"
#include "action_stats.hpp"
#include <rclcpp/rclcpp.hpp>
#include <memory>
#include <functional>
#include <vector>
#include <unordered_map>
#include <mutex>

namespace mtc_action_library {

/**
 * @brief 核心动作库类
 * 
 * 提供统一的机器人动作执行接口，支持：
 * - pick, place, move_to_pour, return_home等基础动作
 * - 执行统计和监控
 * - Debug信息收集
 * - 线程安全的执行
 */
class ActionLibrary {
public:
    /**
     * @brief 构造函数
     * @param node ROS2节点指针
     */
    explicit ActionLibrary(const rclcpp::Node::SharedPtr& node);
    
    /**
     * @brief 析构函数
     */
    ~ActionLibrary();
    
    /**
     * @brief 执行动作（同步，线程安全）
     * @param action_name 动作名称 (pick, place, move_to_pour, return_home)
     * @param params 动作参数
     * @param feedback_callback 反馈回调函数（可选）
     * @return 执行结果
     */
    ActionResult execute(
        const std::string& action_name,
        const ActionParams& params,
        std::function<void(const std::string&)> feedback_callback = nullptr
    );
    
    /**
     * @brief 获取所有可用动作列表
     * @return 动作名称列表
     */
    std::vector<std::string> getActionList() const;
    
    /**
     * @brief 获取指定动作的统计信息
     * @param action_name 动作名称
     * @return 统计信息
     */
    ActionStats getStats(const std::string& action_name) const;
    
    /**
     * @brief 获取所有动作的统计信息
     * @return 动作名称到统计信息的映射
     */
    std::unordered_map<std::string, ActionStats> getAllStats() const;
    
    /**
     * @brief 获取执行历史记录
     * @param limit 最多返回的记录数
     * @return 执行日志列表
     */
    std::vector<ExecutionLog> getHistory(size_t limit = 100) const;
    
    /**
     * @brief 导出Debug报告到文件
     * @param filepath 输出文件路径
     */
    void exportDebugReport(const std::string& filepath) const;
    
    /**
     * @brief 清除历史记录
     */
    void clearHistory();
    
    /**
     * @brief 重置所有统计信息
     */
    void resetAllStats();

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace mtc_action_library








