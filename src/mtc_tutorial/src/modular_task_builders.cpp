#include <mtc_tutorial/modular_task_builders.hpp>
#include <mtc_tutorial/pour_task_builder.hpp>  // Reuse common configuration functions

#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rclcpp/node.hpp>
#include <chrono>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>

namespace mtc = moveit::task_constructor;

namespace mtc_tutorial {

static double clamp(double v, double lo, double hi) { 
    return std::max(lo, std::min(hi, v)); 
}

// =============================================================================
// 1. 抓取任务构建器 (pick_container)
// =============================================================================

mtc::Task build_pick_task(const rclcpp::Node::SharedPtr& node, const PickTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 pick container task");
    task.loadRobotModel(node);

    // 读取夹爪闭合比例参数
    double gripper_close_ratio = 0.30;
    node->get_parameter_or<double>("gripper.close_ratio", gripper_close_ratio, 0.30);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper"; 
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // 创建规划器
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(3.0);
    pipeline_planner->setMaxVelocityScalingFactor(0.3);
    pipeline_planner->setMaxAccelerationScalingFactor(0.5);
    pipeline_planner->setPlannerId("RRTConnect");  // 优化：使用快速的RRTConnect算法

    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(0.3);
    cartesian_planner->setMaxAccelerationScalingFactor(0.5);
    cartesian_planner->setStepSize(0.008);
    cartesian_planner->setJumpThreshold(0.0);

    // 阶段1：获取当前状态
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // 阶段2：打开夹爪
    {
        auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper", 
                                      std::make_shared<mtc::solvers::JointInterpolationPlanner>());
        stage->setGroup(hand_group_name);
        stage->setGoal("open");
        task.add(std::move(stage));
    }

    // 阶段3：连接到抓取位置
    {
        auto stage = std::make_unique<mtc::stages::Connect>("move to pick location",
            mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, pipeline_planner } });
        stage->setTimeout(15.0);
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }

    // 阶段4：抓取序列
    {
        auto grasp = std::make_unique<mtc::SerialContainer>("grasp container");
        task.properties().exposeTo(grasp->properties(), { "eef", "group", "ik_frame" });
        grasp->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 4.1 接近物体（使用安全高度的垂直接近）
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("approach container", cartesian_planner);
            stage->properties().set("marker_ns", "approach_container");
            stage->properties().set("link", hand_frame);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.safe_approach_height, p.safe_approach_height);
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";  // 使用世界坐标系
            vec.vector.z = -1.0;                 // 垂直向下
            stage->setDirection(vec);
            grasp->insert(std::move(stage));
        }

        // 4.2 生成抓取姿态（优化版本）
        {
            auto stage = std::make_unique<mtc::stages::GenerateGraspPose>("generate grasp pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "grasp_pose");
            stage->setPreGraspPose("open");
            stage->setObject(p.object_id);
            stage->setAngleDelta(M_PI / 12.0);
            stage->setMonitoredStage(current_state_ptr);

            // 设置抓取变换（侧向抓取）
            Eigen::Isometry3d grasp_frame_transform;
            grasp_frame_transform.setIdentity();
            Eigen::Quaterniond q = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitX()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitZ());
            grasp_frame_transform.linear() = q.matrix();
            grasp_frame_transform.translation().z() = 0.02;

            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("grasp pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(2);  // 优化：从16降到2个解
            wrapper->setMinSolutionDistance(0.5);  // 优化：从0.3增加到0.5，减少冗余解
            wrapper->setIKFrame(grasp_frame_transform, hand_frame);
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(8.0);
            grasp->insert(std::move(wrapper));
        }

        // 4.3 允许手与物体的碰撞
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision (gripper,container)");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()->getJointModelGroup(hand_group_name)->getLinkModelNamesWithCollisionGeometry(),
                true);
            grasp->insert(std::move(stage));
        }

        // 4.4 微插入提高抓取稳定性
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("pre-close insert", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setIKFrame(hand_frame);
            stage->setMinMaxDistance(0.01, 0.03);
            stage->properties().set("marker_ns", "pre_close_insert");
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = hand_frame;
            vec.vector.z = 1.0;
            stage->setDirection(vec);
            grasp->insert(std::move(stage));
        }

        // 4.5 关闭夹爪
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("close gripper", 
                                          std::make_shared<mtc::solvers::JointInterpolationPlanner>());
            stage->setGroup(hand_group_name);
            std::map<std::string, double> close_goal;
            close_goal["drive_joint"] = gripper_close_ratio;
            stage->setGoal(close_goal);
            grasp->insert(std::move(stage));
        }

        // 4.6 附着对象到夹爪
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach container");
            stage->attachObject(p.object_id, hand_frame);
            grasp->insert(std::move(stage));
        }

        // 4.7 抬升物体
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("lift container", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "lift_container");
            stage->setMinMaxDistance(p.lift_height, p.lift_height + 0.05);
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.z = 1.0;
            stage->setDirection(vec);
            grasp->insert(std::move(stage));
        }

        task.add(std::move(grasp));
    }

    return task;
}

// =============================================================================
// 2. 简单倾倒任务构建器 (pour_to_target)
// =============================================================================

mtc::Task build_pour_only_task(const rclcpp::Node::SharedPtr& node, const PourOnlyTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 pour only task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // 创建规划器
    auto slow_cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    slow_cartesian_planner->setMaxVelocityScalingFactor(0.12);
    slow_cartesian_planner->setMaxAccelerationScalingFactor(0.3);
    slow_cartesian_planner->setStepSize(0.008);
    slow_cartesian_planner->setJumpThreshold(0.0);

    auto slow_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
    const double joint6_max_rad_s = 5.0;
    double scaling_from_deg = (p.tilt_speed_deg_s * M_PI / 180.0) / joint6_max_rad_s;
    slow_interpolation_planner->setMaxVelocityScalingFactor(clamp(scaling_from_deg, 0.05, 1.0));
    slow_interpolation_planner->setMaxAccelerationScalingFactor(0.3);

    // 阶段1：获取当前状态
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // 阶段2：倾倒序列
    {
        auto pour = std::make_unique<mtc::SerialContainer>("pour water");
        task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
        pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });
        
        // 2.1 移动到倾倒位置（Y轴单独移动）
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("move to pour position", slow_cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.move_to_pour_min, p.move_to_pour_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "move_to_pour");
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.y = -1.0;  // 沿-Y方向移动
            stage->setDirection(vec);
            pour->insert(std::move(stage));
        }

        // 2.2 倾斜开始
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt start", slow_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }

        // 按时长减速：根据 pour_hold_sec 计算 start→end 与 end→start 的速度缩放
        {
            const double joint6_max_rad_s = 2.0;
            const double tilt_delta_rad = std::abs((p.tilt_end_deg - p.tilt_start_deg) * M_PI / 180.0);
            double desired_T = p.pour_hold_sec > 0.0 ? p.pour_hold_sec
                              : (tilt_delta_rad / std::max(p.tilt_speed_deg_s * M_PI / 180.0, 1e-3));
            desired_T = clamp(desired_T, 0.2, 20.0);
            const double v_req = tilt_delta_rad / desired_T;
            double vel_scaling_timed = clamp(v_req / joint6_max_rad_s, 0.05, 1.0);
            RCLCPP_INFO(node->get_logger(), "⏱️ 倾倒时间控制(独立): delta=%.3frad (~%.1f°), T=%.2fs, v_req=%.3f, scaling=%.2f",
                        tilt_delta_rad, tilt_delta_rad * 180.0 / M_PI, desired_T, v_req, vel_scaling_timed);

            auto timed_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
            timed_interpolation_planner->setMaxVelocityScalingFactor(vel_scaling_timed);
            timed_interpolation_planner->setMaxAccelerationScalingFactor(0.3);

            // 以受控时长从 start → end
            {
                auto stage = std::make_unique<mtc::stages::MoveTo>("tilt to end (timed)", timed_interpolation_planner);
                stage->setGroup(arm_group_name);
                std::map<std::string, double> joint_goal;
                joint_goal["joint6"] = p.tilt_end_deg * M_PI / 180.0;
                stage->setGoal(joint_goal);
                pour->insert(std::move(stage));
            }
            // 以受控时长从 end → start（回退）
            {
                auto stage = std::make_unique<mtc::stages::MoveTo>("return from pour (timed)", timed_interpolation_planner);
                stage->setGroup(arm_group_name);
                std::map<std::string, double> joint_goal;
                joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
                stage->setGoal(joint_goal);
                pour->insert(std::move(stage));
            }
        }

        // 2.5 从倾倒位置返回
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("return from pour", slow_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }

        task.add(std::move(pour));
    }

    return task;
}

// =============================================================================
// 3. 放置任务构建器 (place_container)
// =============================================================================

mtc::Task build_place_task(const rclcpp::Node::SharedPtr& node, const PlaceTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 place container task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // 创建规划器
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(3.0);
    pipeline_planner->setMaxVelocityScalingFactor(0.3);
    pipeline_planner->setMaxAccelerationScalingFactor(0.5);
    pipeline_planner->setPlannerId("RRTConnect");

    auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
    interpolation_planner->setMaxVelocityScalingFactor(0.5);
    interpolation_planner->setMaxAccelerationScalingFactor(0.6);

    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(0.3);
    cartesian_planner->setMaxAccelerationScalingFactor(0.5);
    cartesian_planner->setStepSize(0.008);
    cartesian_planner->setJumpThreshold(0.0);

    // 阶段1：获取当前状态
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // 阶段2：附着对象到夹爪（模拟已经抓住的状态）- 这是关键的状态管理阶段
    mtc::Stage* attach_object_stage_ptr = nullptr;
    {
        // 检查目标对象是否还存在于世界碰撞体中；如果已经被抓取（不存在于world），则跳过附着阶段
        moveit::planning_interface::PlanningSceneInterface psi;
        bool object_in_world = false;
        try {
            auto objs = psi.getObjects({ p.object_id });
            object_in_world = objs.find(p.object_id) != objs.end();
        } catch (...) {
            object_in_world = true; // 保守起见执行附着
        }
        if (object_in_world) {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object for place");
            stage->attachObject(p.object_id, hand_frame);
            attach_object_stage_ptr = stage.get();  // 保存指针用于监控
            task.add(std::move(stage));
        } else {
            // 已经附着到手上了，使用当前状态作为监控参考
            attach_object_stage_ptr = current_state_ptr;
        }
    }

    // 阶段3：连接到放置位置
    {
        auto stage = std::make_unique<mtc::stages::Connect>(
            "move to place",
            mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, interpolation_planner } });
        stage->setTimeout(15.0);
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }

    // 阶段4：放置容器序列（完整版本，按照mtc_tutorial.cpp）
    {
        auto place = std::make_unique<mtc::SerialContainer>("place object");
        task.properties().exposeTo(place->properties(), { "eef", "group", "ik_frame" });
        place->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 4.1 生成放置姿态 - 使用完整的GeneratePlacePose
        {
            auto stage = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "place_pose");
            stage->setObject(p.object_id);

            // 设置放置目标位置
            geometry_msgs::msg::PoseStamped target_pose_msg;
            target_pose_msg.header.frame_id = "link_base";
            if (p.target_pose.has_value()) {
                target_pose_msg.pose = p.target_pose.value();
            } else {
                // 使用默认放置位置
                target_pose_msg.pose.position.x = 0.0;
                target_pose_msg.pose.position.y = -0.45;
                target_pose_msg.pose.position.z = 0.18;
                target_pose_msg.pose.orientation.w = 1.0;
            }
            stage->setPose(target_pose_msg);
            
            // 关键：设置监控阶段 - 这是GeneratePlacePose正常工作的必要条件
            if (attach_object_stage_ptr) {
                stage->setMonitoredStage(attach_object_stage_ptr);
            }

            // 计算IK
            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("place pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(1);
            wrapper->setMinSolutionDistance(0.5);
            
            // 定义放置时的物体框架 - 让物体保持垂直
            Eigen::Isometry3d place_frame_transform;
            place_frame_transform.setIdentity();
            wrapper->setIKFrame(place_frame_transform, p.object_id);
            
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(5.0);
            place->insert(std::move(wrapper));
        }

        // 4.2 降低物体到放置位置
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.lower_min, p.lower_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "lower_object");
            
            // 设置向下的方向
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.z = -1.0;
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }

        // 4.3 打开夹爪释放物体
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("release object", interpolation_planner);
            stage->setGroup(hand_group_name);
            stage->setGoal("open");
            place->insert(std::move(stage));
        }

        // 4.4 禁止手和物体之间的碰撞
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid collision (hand,object)");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()
                    ->getJointModelGroup(hand_group_name)
                    ->getLinkModelNamesWithCollisionGeometry(),
                false);
            place->insert(std::move(stage));
        }

        // 4.5 分离物体
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
            stage->detachObject(p.object_id, hand_frame);
            place->insert(std::move(stage));
        }

        // 4.6 后退
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.retreat_min, p.retreat_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "retreat");

            // 设置后退方向
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = hand_frame;
            vec.vector.z = -1.0;  // 向后退
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }
        
        task.add(std::move(place));
    }

    return task;
}

// =============================================================================
// 4. 返回任务构建器 (return_to_home)
// =============================================================================

mtc::Task build_return_task(const rclcpp::Node::SharedPtr& node, const ReturnTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 return home task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_frame = "link_tcp";  // 添加hand_frame定义

    task.setProperty("group", arm_group_name);

    // 创建规划器
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(3.0);
    pipeline_planner->setMaxVelocityScalingFactor(0.3);
    pipeline_planner->setMaxAccelerationScalingFactor(0.5);
    pipeline_planner->setPlannerId("RRTConnect");

    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(0.3);
    cartesian_planner->setMaxAccelerationScalingFactor(0.5);
    cartesian_planner->setStepSize(0.008);
    cartesian_planner->setJumpThreshold(0.0);

    // 阶段1：获取当前状态
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // 阶段1.5：安全抬升到安全高度
    {
        auto stage = std::make_unique<mtc::stages::MoveRelative>("safe lift before return", cartesian_planner);
        stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        stage->setIKFrame(hand_frame);
        stage->properties().set("marker_ns", "safe_lift_return");
        stage->setMinMaxDistance(0.08, 0.12);  // 安全抬升高度8-12cm
        geometry_msgs::msg::Vector3Stamped vec;
        vec.header.frame_id = "link_base";
        vec.vector.z = 1.0;  // 垂直向上
        stage->setDirection(vec);
        task.add(std::move(stage));
    }

    // 阶段2：返回初始位置
    {
        auto stage = std::make_unique<mtc::stages::MoveTo>("return to home", pipeline_planner);
        stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        stage->setGroup(arm_group_name);
        
        if (p.target_joints.has_value()) {
            // 使用指定的关节目标
            stage->setGoal(p.target_joints.value());
        } else {
            // 使用"home"配置
            stage->setGoal("home");
        }
        
        stage->setTimeout(p.timeout_sec);
        task.add(std::move(stage));
    }

    return task;
}



// =============================================================================
// 5. 移动到倾倒位置任务构建器 (move_to_pour_position) - 高级优化版本
// =============================================================================

mtc::Task build_move_to_pour_task(const rclcpp::Node::SharedPtr& node, const MoveToPourTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 move to pour position task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // 创建优化的笛卡尔规划器（基于简化的参数）
    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.acceleration_scaling);
    cartesian_planner->setStepSize(p.step_size);
    cartesian_planner->setJumpThreshold(0.0);
    cartesian_planner->setMinFraction(p.min_cartesian_fraction);

    // 阶段1：获取当前状态
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // 阶段2：直接移动到目标位置（简化版本）
    {
        RCLCPP_INFO(node->get_logger(), "🎯 移动到目标位置: (%.3f, %.3f, %.3f), 速度: %.2f", 
                   p.target_x, p.target_y, p.target_z, p.velocity_scaling);

        geometry_msgs::msg::PoseStamped target_pose_msg;
        target_pose_msg.header.frame_id = "link_base";
        target_pose_msg.pose.position.x = p.target_x;
        target_pose_msg.pose.position.y = p.target_y;
        target_pose_msg.pose.position.z = p.target_z;

        // 尝试获取并保持当前姿态
        try {
            tf2_ros::Buffer tf_buffer(node->get_clock());
            tf2_ros::TransformListener tf_listener(tf_buffer);
            auto tf = tf_buffer.lookupTransform("link_base", hand_frame, 
                                              tf2::TimePointZero, std::chrono::milliseconds(500));
            target_pose_msg.pose.orientation = tf.transform.rotation;
            RCLCPP_INFO(node->get_logger(), "✅ 保持当前姿态");
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ 无法获取当前姿态，使用默认姿态");
            // 使用默认的直立姿态
            target_pose_msg.pose.orientation.w = 1.0;
            target_pose_msg.pose.orientation.x = 0.0;
            target_pose_msg.pose.orientation.y = 0.0;
            target_pose_msg.pose.orientation.z = 0.0;
        }

        auto stage = std::make_unique<mtc::stages::MoveTo>("move to pour position", cartesian_planner);
        stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        stage->properties().set("marker_ns", "move_to_pour");
        stage->setGroup(arm_group_name);
        stage->setTimeout(p.timeout_sec);
        stage->setIKFrame(hand_frame);
        stage->setGoal(target_pose_msg);
        task.add(std::move(stage));
    }

    // 可选：阶段3-6 简单倾倒序列（融合自 pour_only），仅当 pour_execute 为真
    if (p.pour_execute) {
        RCLCPP_INFO(node->get_logger(), "🫗 启用简单倾倒序列: start=%.1f°, end=%.1f°, speed=%.1f°/s, hold=%.1fs",
                    p.tilt_start_deg, p.tilt_end_deg, p.tilt_speed_deg_s, p.pour_hold_sec);

        const double joint6_max_rad_s = 2.0;
        const double tilt_delta_rad = std::abs((p.tilt_end_deg - p.tilt_start_deg) * M_PI / 180.0);
        double desired_T = p.pour_hold_sec > 0.0 ? p.pour_hold_sec
                          : (tilt_delta_rad / std::max(p.tilt_speed_deg_s * M_PI / 180.0, 1e-3));
        // 将期望时长夹紧到[0.2s, 20s]范围，避免异常值
        desired_T = clamp(desired_T, 0.2, 20.0);
        const double v_req = tilt_delta_rad / desired_T;
        double vel_scaling_timed = clamp(v_req / joint6_max_rad_s, 0.05, 1.0);

        RCLCPP_INFO(node->get_logger(), "⏱️ 倾倒时间控制: delta=%.3frad (~%.1f°), T=%.2fs, v_req=%.3f rad/s, scaling=%.2f",
                    tilt_delta_rad, tilt_delta_rad * 180.0 / M_PI, desired_T, v_req, vel_scaling_timed);

        auto timed_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
        timed_interpolation_planner->setMaxVelocityScalingFactor(vel_scaling_timed);
        timed_interpolation_planner->setMaxAccelerationScalingFactor(0.3);

        auto pour = std::make_unique<mtc::SerialContainer>("pour water");
        task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
        pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 倾斜开始（到达起始角）
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt start", timed_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }
        // 以受控时长从 start → end
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt to end (timed)", timed_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_end_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }
        // 以受控时长从 end → start（回退）
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("return from pour (timed)", timed_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }

        task.add(std::move(pour));
    }

    // 可选：阶段7 递给用户的动作（打开夹爪），仅当 execute_give 为真
    if (p.execute_give) {
        RCLCPP_INFO(node->get_logger(), "🤲 启用递给用户动作: 夹爪打开比例=%.2f", p.gripper_open_ratio);

        auto give = std::make_unique<mtc::SerialContainer>("give to user");
        task.properties().exposeTo(give->properties(), { "eef", "group", "ik_frame" });
        give->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 7.1 可选：稍微后退一点，方便用户接取
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat for user", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(0.02, 0.05); // 后退2-5cm
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "retreat_for_user");
            
            // 沿着手部坐标系的 -X 方向后退（通常是向后方向）
            geometry_msgs::msg::Vector3Stamped retreat_vec;
            retreat_vec.header.frame_id = hand_frame;
            retreat_vec.vector.z = +0.5;
            stage->setDirection(retreat_vec);
            
            give->insert(std::move(stage));
        }

        // 7.2 打开夹爪到指定比例
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper for user", 
                                                               std::make_shared<mtc::solvers::JointInterpolationPlanner>());
            stage->setGroup(hand_group_name);
            
            // 智能夹爪控制：如果用户要求完全打开(1.0)，使用预定义的"open"姿态
            // 否则使用自定义的关节值
            if (std::abs(p.gripper_open_ratio - 1.0) < 0.01) {  // 几乎完全打开
                stage->setGoal("open");  // 使用SRDF中定义的"open"姿态
                RCLCPP_INFO(node->get_logger(), "🤏 使用预定义的'open'姿态完全打开夹爪");
            } else {
                // 计算夹爪关节值：gripper_open_ratio (0.0=完全闭合, 1.0=完全打开)
                // UF850夹爪使用drive_joint：0.0=完全打开，0.85=完全闭合
                double max_gripper_closing = 0.85; // UF850夹爪的最大闭合值
                double gripper_target = (1.0 - p.gripper_open_ratio) * max_gripper_closing; // 反向映射：1.0->0.0, 0.0->0.85
                
                std::map<std::string, double> gripper_goal;
                gripper_goal["drive_joint"] = gripper_target;
                stage->setGoal(gripper_goal);
                
                RCLCPP_INFO(node->get_logger(), "🤏 UF850夹爪自定义位置: %.4f (drive_joint, 0.0=打开, 0.85=闭合) - 用户请求打开比例: %.2f", 
                           gripper_target, p.gripper_open_ratio);
            }
            
            stage->setTimeout(3.0); // 给夹爪动作足够时间
            give->insert(std::move(stage));
        }

        // 7.3 释放物体：分离物体并恢复碰撞检测
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("release and restore object");
            
            // 获取夹爪的所有碰撞几何体
            auto gripper_links = task.getRobotModel()
                ->getJointModelGroup(hand_group_name)
                ->getLinkModelNamesWithCollisionGeometry();
            
            // 智能物体释放：尝试分离和恢复常见的物体名称
            std::vector<std::string> possible_objects = {
                "object", "object_1", "object_2", "object_3", "object_4", "object_5",
                "bowl", "bowl_1", "bowl_2", "bowl_3", "cup", "cup_1", "container"
            };
            
            int released_count = 0;
            for (const auto& obj_name : possible_objects) {
                try {
                    // 分离物体（如果物体没有被附着，这个操作会被MTC忽略）
                    stage->detachObject(obj_name, hand_frame);
                    
                    // 恢复碰撞检测（重新启用夹爪与物体之间的碰撞检测）
                    stage->allowCollisions(obj_name, gripper_links, false);  // false = 重新启用碰撞检测
                    
                    released_count++;
                    RCLCPP_DEBUG(node->get_logger(), "🔓 释放物体并恢复碰撞: %s", obj_name.c_str());
                    
                } catch (const std::exception& e) {
                    // 忽略操作失败的情况（物体可能不存在或未被附着）
                    RCLCPP_DEBUG(node->get_logger(), "⚠️ 无法处理物体 %s: %s", obj_name.c_str(), e.what());
                } catch (...) {
                    // 忽略其他异常
                }
            }
            
            RCLCPP_INFO(node->get_logger(), "🔒 已释放物体并恢复碰撞检测（处理了 %d 个潜在物体），物体现在可以被用户安全取走", released_count);
            give->insert(std::move(stage));
        }



        task.add(std::move(give));
    }

    RCLCPP_INFO(node->get_logger(), "🔧 简化移动任务配置完成 - 速度: %.2f, 超时: %.1fs%s%s", 
               p.velocity_scaling, p.timeout_sec,
               p.pour_execute ? ", 包含倾倒" : "",
               p.execute_give ? ", 包含递给用户" : "");

    return task;
}



// =============================================================================
// 7. 预倒水任务构建器 (pre_pour)
// =============================================================================

mtc::Task build_pre_pour_task(const rclcpp::Node::SharedPtr& node, const PrePourTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 pre-pour task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // 规划器
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(5.0);
    pipeline_planner->setMaxVelocityScalingFactor(p.velocity_scaling);
    pipeline_planner->setMaxAccelerationScalingFactor(p.acceleration_scaling);
    pipeline_planner->setPlannerId("RRTConnect");

    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.acceleration_scaling);
    cartesian_planner->setStepSize(p.step_size);
    cartesian_planner->setJumpThreshold(0.0);
    cartesian_planner->setMinFraction(p.min_cartesian_fraction);

    // 阶段1：当前状态
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // 阶段2：连接到预姿态（解决起始连通性）
    // 移除Connect阶段，直接进入预倒水容器，避免在无完整场景/状态下初始化失败

    // 阶段3：预倒水容器
    {
        auto pre = std::make_unique<mtc::SerialContainer>("pre-pour");
        task.properties().exposeTo(pre->properties(), { "eef", "group", "ik_frame" });
        pre->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 3.1 生成预倒水姿势
        geometry_msgs::msg::PoseStamped target_pose_msg;
        target_pose_msg.header.frame_id = "link_base";
        target_pose_msg.pose.position.x = p.target_x;
        target_pose_msg.pose.position.y = p.target_y;
        target_pose_msg.pose.position.z = p.target_z + p.safe_lift_z;

        // 计算姿态：保持当前 roll/pitch，可选对齐 yaw 指向目标
        try {
            tf2_ros::Buffer tf_buffer(node->get_clock());
            tf2_ros::TransformListener tf_listener(tf_buffer);
            auto tf = tf_buffer.lookupTransform("link_base", hand_frame, 
                                              tf2::TimePointZero, std::chrono::milliseconds(500));
            double roll = 0.0, pitch = 0.0, yaw = 0.0;
            {
                tf2::Quaternion q_current;
                tf2::fromMsg(tf.transform.rotation, q_current);
                tf2::Matrix3x3(q_current).getRPY(roll, pitch, yaw);
            }

            if (p.yaw_align_to_target) {
                const double curr_x = tf.transform.translation.x;
                const double curr_y = tf.transform.translation.y;
                const double vec_x = p.target_x - curr_x;
                const double vec_y = p.target_y - curr_y;
                const double heading = std::atan2(vec_y, vec_x);
                yaw = heading;
            }

            if (!p.keep_current_roll_pitch) {
                roll = 0.0; pitch = 0.0;
            }

            tf2::Quaternion q_target;
            q_target.setRPY(roll, pitch, yaw);
            target_pose_msg.pose.orientation = tf2::toMsg(q_target);
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️ 预倒水姿态：无法获取当前姿态，使用默认直立");
            target_pose_msg.pose.orientation.w = 1.0;
            target_pose_msg.pose.orientation.x = 0.0;
            target_pose_msg.pose.orientation.y = 0.0;
            target_pose_msg.pose.orientation.z = 0.0;
        }

        // 直接使用 MoveTo 以目标姿态进行预倒水定位（无需单独的 GeneratePose/ComputeIK）

        // 3.2 移动到预倒水姿势（末段可选笛卡尔）
        if (p.use_cartesian_for_final_approach) {
            auto move = std::make_unique<mtc::stages::MoveTo>("move to pre-pour (cartesian)", cartesian_planner);
            move->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            move->properties().set("marker_ns", "move_to_pre_pour");
            move->setGroup(arm_group_name);
            move->setIKFrame(hand_frame);
            move->setGoal(target_pose_msg);
            move->setTimeout(p.timeout_sec);
            pre->insert(std::move(move));
        } else {
            auto move = std::make_unique<mtc::stages::MoveTo>("move to pre-pour", pipeline_planner);
            move->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            move->properties().set("marker_ns", "move_to_pre_pour");
            move->setGroup(arm_group_name);
            move->setGoal(target_pose_msg);
            move->setTimeout(p.timeout_sec);
            pre->insert(std::move(move));
        }

        task.add(std::move(pre));
    }

    return task;
}

} // namespace mtc_tutorial 