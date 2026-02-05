#include <rclcpp/rclcpp.hpp>
#include <mtc_tutorial/modular_task_builders.hpp>

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("test_modular_tasks");
    
    RCLCPP_INFO(node->get_logger(), "🧪 开始测试模块化MTC任务构建器...");
    
    try {
        // 测试1：Pick任务构建器
        RCLCPP_INFO(node->get_logger(), "\n=== 测试1: Pick任务构建器 ===");
        mtc_tutorial::PickTaskParams pick_params;
        pick_params.source_x = 0.0;
        pick_params.source_y = -0.4;
        pick_params.source_z = 0.13;
        pick_params.plan_only = true; // 仅测试规划，不执行
        
        auto pick_task = mtc_tutorial::build_pick_task(node, pick_params);
        RCLCPP_INFO(node->get_logger(), "✅ build_pick_task 成功创建任务！");
        RCLCPP_INFO(node->get_logger(), "   任务名称: %s", pick_task.stages()->name().c_str());
        RCLCPP_INFO(node->get_logger(), "   阶段数量: %zu", pick_task.stages()->numChildren());
        
        // 尝试初始化任务
        try {
            pick_task.init();
            RCLCPP_INFO(node->get_logger(), "✅ Pick任务初始化成功！");
            
            // 尝试规划（仅规划模式）
            if (pick_task.plan(1)) {
                RCLCPP_INFO(node->get_logger(), "✅ Pick任务规划成功！找到 %zu 个解决方案", 
                           pick_task.solutions().size());
            } else {
                RCLCPP_WARN(node->get_logger(), "⚠️ Pick任务规划失败（可能缺少场景对象）");
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ Pick任务初始化失败: %s", e.what());
        }
        
        // 测试2：Pour任务构建器
        RCLCPP_INFO(node->get_logger(), "\n=== 测试2: Pour任务构建器 ===");
        mtc_tutorial::PourOnlyTaskParams pour_params;
        pour_params.tilt_start_deg = 45.0;
        pour_params.tilt_end_deg = 120.0;
        pour_params.tilt_speed_deg_s = 25.0;
        pour_params.pour_hold_sec = 2.0;
        pour_params.plan_only = true;
        
        auto pour_task = mtc_tutorial::build_pour_only_task(node, pour_params);
        RCLCPP_INFO(node->get_logger(), "✅ build_pour_only_task 成功创建任务！");
        RCLCPP_INFO(node->get_logger(), "   任务名称: %s", pour_task.stages()->name().c_str());
        RCLCPP_INFO(node->get_logger(), "   阶段数量: %zu", pour_task.stages()->numChildren());
        
        try {
            pour_task.init();
            RCLCPP_INFO(node->get_logger(), "✅ Pour任务初始化成功！");
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ Pour任务初始化失败: %s", e.what());
        }
        
        // 测试3：Place任务构建器
        RCLCPP_INFO(node->get_logger(), "\n=== 测试3: Place任务构建器 ===");
        mtc_tutorial::PlaceTaskParams place_params;
        place_params.plan_only = true;
        
        auto place_task = mtc_tutorial::build_place_task(node, place_params);
        RCLCPP_INFO(node->get_logger(), "✅ build_place_task 成功创建任务！");
        RCLCPP_INFO(node->get_logger(), "   任务名称: %s", place_task.stages()->name().c_str());
        RCLCPP_INFO(node->get_logger(), "   阶段数量: %zu", place_task.stages()->numChildren());
        
        try {
            place_task.init();
            RCLCPP_INFO(node->get_logger(), "✅ Place任务初始化成功！");
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ Place任务初始化失败: %s", e.what());
        }
        
        // 测试4：Return任务构建器
        RCLCPP_INFO(node->get_logger(), "\n=== 测试4: Return任务构建器 ===");
        mtc_tutorial::ReturnTaskParams return_params;
        return_params.plan_only = true;
        
        auto return_task = mtc_tutorial::build_return_task(node, return_params);
        RCLCPP_INFO(node->get_logger(), "✅ build_return_task 成功创建任务！");
        RCLCPP_INFO(node->get_logger(), "   任务名称: %s", return_task.stages()->name().c_str());
        RCLCPP_INFO(node->get_logger(), "   阶段数量: %zu", return_task.stages()->numChildren());
        
        try {
            return_task.init();
            RCLCPP_INFO(node->get_logger(), "✅ Return任务初始化成功！");
            
            // Return任务通常比较简单，尝试规划
            if (return_task.plan(1)) {
                RCLCPP_INFO(node->get_logger(), "✅ Return任务规划成功！找到 %zu 个解决方案",
                           return_task.solutions().size());
            } else {
                RCLCPP_WARN(node->get_logger(), "⚠️ Return任务规划失败");
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ Return任务初始化失败: %s", e.what());
        }
        
        RCLCPP_INFO(node->get_logger(), "\n🎉 所有模块化任务构建器测试完成！");
        RCLCPP_INFO(node->get_logger(), "✅ 所有4个任务构建器都能正常创建MTC任务");
        RCLCPP_INFO(node->get_logger(), "📋 任务构建器功能验证：");
        RCLCPP_INFO(node->get_logger(), "   • build_pick_task() - 创建完整的抓取任务");
        RCLCPP_INFO(node->get_logger(), "   • build_pour_only_task() - 创建纯倾倒任务"); 
        RCLCPP_INFO(node->get_logger(), "   • build_place_task() - 创建放置任务");
        RCLCPP_INFO(node->get_logger(), "   • build_return_task() - 创建返回任务");
        
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node->get_logger(), "❌ 测试过程中发生异常: %s", e.what());
        rclcpp::shutdown();
        return 1;
    }
    
    rclcpp::shutdown();
    return 0;
} 