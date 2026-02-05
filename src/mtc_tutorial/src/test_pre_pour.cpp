#include <rclcpp/rclcpp.hpp>
#include <mtc_tutorial/modular_task_builders.hpp>
#include <moveit/task_constructor/stage.h>

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("test_pre_pour");

    RCLCPP_INFO(node->get_logger(), "🧪 测试预倒水任务构建器...");

    try {
        mtc_tutorial::PrePourTaskParams params;
        // 可通过参数覆盖默认目标点
        node->declare_parameter<double>("target_x", params.target_x);
        node->declare_parameter<double>("target_y", params.target_y);
        node->declare_parameter<double>("target_z", params.target_z);
        node->declare_parameter<double>("safe_lift_z", params.safe_lift_z);
        node->declare_parameter<bool>("yaw_align_to_target", params.yaw_align_to_target);
        node->declare_parameter<bool>("keep_current_roll_pitch", params.keep_current_roll_pitch);
        node->declare_parameter<bool>("use_cartesian_for_final_approach", params.use_cartesian_for_final_approach);
        node->declare_parameter<double>("velocity_scaling", params.velocity_scaling);
        node->declare_parameter<double>("acceleration_scaling", params.acceleration_scaling);
        node->declare_parameter<double>("step_size", params.step_size);
        node->declare_parameter<double>("min_cartesian_fraction", params.min_cartesian_fraction);
        node->declare_parameter<double>("ik_timeout", params.ik_timeout);
        node->declare_parameter<int>("max_ik_solutions", params.max_ik_solutions);
        node->declare_parameter<double>("min_solution_distance", params.min_solution_distance);
        node->declare_parameter<double>("timeout_sec", params.timeout_sec);
        node->declare_parameter<bool>("plan_only", true);

        node->get_parameter("target_x", params.target_x);
        node->get_parameter("target_y", params.target_y);
        node->get_parameter("target_z", params.target_z);
        node->get_parameter("safe_lift_z", params.safe_lift_z);
        node->get_parameter("yaw_align_to_target", params.yaw_align_to_target);
        node->get_parameter("keep_current_roll_pitch", params.keep_current_roll_pitch);
        node->get_parameter("use_cartesian_for_final_approach", params.use_cartesian_for_final_approach);
        node->get_parameter("velocity_scaling", params.velocity_scaling);
        node->get_parameter("acceleration_scaling", params.acceleration_scaling);
        node->get_parameter("step_size", params.step_size);
        node->get_parameter("min_cartesian_fraction", params.min_cartesian_fraction);
        node->get_parameter("ik_timeout", params.ik_timeout);
        node->get_parameter("max_ik_solutions", params.max_ik_solutions);
        node->get_parameter("min_solution_distance", params.min_solution_distance);
        node->get_parameter("timeout_sec", params.timeout_sec);
        node->get_parameter("plan_only", params.plan_only);

        auto task = mtc_tutorial::build_pre_pour_task(node, params);
        RCLCPP_INFO(node->get_logger(), "✅ 任务创建完成: %s | 阶段数: %zu", task.stages()->name().c_str(), task.stages()->numChildren());

        try {
            task.init();
            RCLCPP_INFO(node->get_logger(), "✅ 任务初始化成功");
        } catch (const moveit::task_constructor::InitStageException& e) {
            std::ostringstream oss; oss << e;
            RCLCPP_ERROR(node->get_logger(), "InitStageException detail:\n%s", oss.str().c_str());
            rclcpp::shutdown();
            return 2;
        }

        // 快速规划一次
        const size_t max_solutions = 1;
        if (task.plan(max_solutions)) {
            RCLCPP_INFO(node->get_logger(), "✅ 规划成功，solutions=%zu", task.solutions().size());
        } else {
            RCLCPP_WARN(node->get_logger(), "⚠️ 规划失败（可能需要先加载规划场景或调整目标）");
        }

        if (!params.plan_only && !task.solutions().empty()) {
            RCLCPP_INFO(node->get_logger(), "▶️ 执行第一条解...");
            task.introspection().publishSolution(*task.solutions().front());
            task.execute(*task.solutions().front());
            RCLCPP_INFO(node->get_logger(), "✅ 执行完成");
        } else if (params.plan_only) {
            RCLCPP_INFO(node->get_logger(), "ℹ️ plan_only=true，跳过执行");
        }
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node->get_logger(), "❌ 测试程序异常: %s", e.what());
        rclcpp::shutdown();
        return 1;
    }

    rclcpp::shutdown();
    return 0;
} 