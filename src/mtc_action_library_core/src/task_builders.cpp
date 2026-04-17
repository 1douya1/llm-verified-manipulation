#include "mtc_action_library/task_builders.hpp"

#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/robot_state/robot_state.h>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rclcpp/node.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <chrono>
#include <cmath>
#include <vector>

namespace mtc = moveit::task_constructor;

namespace mtc_action_library {

static double clamp(double v, double lo, double hi) { 
    return std::max(lo, std::min(hi, v)); 
}

// =============================================================================
// 通用MoveIt配置函数
// =============================================================================

void configure_moveit_params(const rclcpp::Node::SharedPtr& node) {
    auto declare_if = [&](const std::string& name, const rclcpp::ParameterValue& def){
        try { if (!node->has_parameter(name)) node->declare_parameter(name, def); } catch (...) {}
    };
    
    declare_if("robot_description", rclcpp::ParameterValue(""));
    declare_if("robot_description_semantic", rclcpp::ParameterValue(""));
    declare_if("default_planning_pipeline", rclcpp::ParameterValue("ompl"));
    declare_if("planning_pipelines", rclcpp::ParameterValue(std::vector<std::string>{"ompl"}));
    declare_if("ompl.planning_plugin", rclcpp::ParameterValue("ompl_interface/OMPLPlanner"));
    declare_if("ompl.request_adapters", rclcpp::ParameterValue(
        std::string("default_planner_request_adapters/AddTimeOptimalParameterization ") +
        "default_planner_request_adapters/FixWorkspaceBounds "
        "default_planner_request_adapters/FixStartStateBounds "
        "default_planner_request_adapters/FixStartStateCollision "
        "default_planner_request_adapters/FixStartStatePathConstraints"));
    declare_if("trajectory_execution.allowed_execution_duration_scaling", rclcpp::ParameterValue(5.0));
    declare_if("trajectory_execution.allowed_goal_duration_margin", rclcpp::ParameterValue(2.0));
    declare_if("trajectory_execution.allowed_start_tolerance", rclcpp::ParameterValue(0.05));
    declare_if("moveit_controller_manager", rclcpp::ParameterValue("moveit_simple_controller_manager/MoveItSimpleControllerManager"));
    
    declare_if("robot_description_kinematics.uf850.kinematics_solver", rclcpp::ParameterValue("kdl_kinematics_plugin/KDLKinematicsPlugin"));
    declare_if("robot_description_kinematics.uf850.kinematics_solver_search_resolution", rclcpp::ParameterValue(0.005));
    declare_if("robot_description_kinematics.uf850.kinematics_solver_timeout", rclcpp::ParameterValue(0.005));
    declare_if("robot_description_kinematics.uf850.kinematics_solver_attempts", rclcpp::ParameterValue(3));
    
    for (int i = 1; i <= 6; ++i) {
        const std::string j = "robot_description_planning.joint_limits.joint" + std::to_string(i);
        declare_if(j + ".has_acceleration_limits", rclcpp::ParameterValue(true));
        declare_if(j + ".max_acceleration", rclcpp::ParameterValue(5.0));
        declare_if(j + ".has_velocity_limits", rclcpp::ParameterValue(true));
        declare_if(j + ".max_velocity", rclcpp::ParameterValue(1.0));
    }
    
    declare_if("gripper.close_ratio", rclcpp::ParameterValue(0.30));
    
    // 尝试从move_group同步参数
    std::string urdf_existing, srdf_existing;
    node->get_parameter_or<std::string>("robot_description", urdf_existing, "");
    node->get_parameter_or<std::string>("robot_description_semantic", srdf_existing, "");
    
    auto probe = std::make_shared<rclcpp::Node>(
        "action_lib_param_probe", 
        rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
    auto client = std::make_shared<rclcpp::SyncParametersClient>(probe, "/move_group");
    
    if (client->wait_for_service(std::chrono::seconds(5))) {
        try {
            // 获取robot description
            auto base = client->get_parameters({"robot_description", "robot_description_semantic"});
            if (base.size() >= 2) {
                if (urdf_existing.empty() && base[0].get_type() == rclcpp::PARAMETER_STRING)
                    node->set_parameter(rclcpp::Parameter("robot_description", base[0].as_string()));
                if (srdf_existing.empty() && base[1].get_type() == rclcpp::PARAMETER_STRING)
                    node->set_parameter(rclcpp::Parameter("robot_description_semantic", base[1].as_string()));
            }
            
            // 同步kinematics solver配置
            auto kin = client->get_parameters({
                "robot_description_kinematics.uf850.kinematics_solver",
                "robot_description_kinematics.uf850.kinematics_solver_search_resolution",
                "robot_description_kinematics.uf850.kinematics_solver_timeout",
                "robot_description_kinematics.uf850.kinematics_solver_attempts"
            });
            
            if (kin.size() >= 4) {
                if (kin[0].get_type() == rclcpp::PARAMETER_STRING && !kin[0].as_string().empty()) {
                    node->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver", kin[0].as_string()));
                    RCLCPP_INFO(node->get_logger(), "✅ Synced kinematics solver: %s", kin[0].as_string().c_str());
                }
                if (kin[1].get_type() == rclcpp::PARAMETER_DOUBLE)
                    node->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_search_resolution", kin[1].as_double()));
                if (kin[2].get_type() == rclcpp::PARAMETER_DOUBLE)
                    node->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_timeout", kin[2].as_double()));
                if (kin[3].get_type() == rclcpp::PARAMETER_INTEGER)
                    node->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_attempts", kin[3].as_int()));
            }
            
            // 同步planning配置
            auto planning = client->get_parameters({
                "default_planning_pipeline",
                "planning_pipelines",
                "ompl.planning_plugin",
                "ompl.request_adapters"
            });
            
            if (planning.size() >= 4) {
                if (planning[0].get_type() == rclcpp::PARAMETER_STRING)
                    node->set_parameter(rclcpp::Parameter("default_planning_pipeline", planning[0].as_string()));
                if (planning[1].get_type() == rclcpp::PARAMETER_STRING_ARRAY)
                    node->set_parameter(rclcpp::Parameter("planning_pipelines", planning[1].as_string_array()));
                if (planning[2].get_type() == rclcpp::PARAMETER_STRING)
                    node->set_parameter(rclcpp::Parameter("ompl.planning_plugin", planning[2].as_string()));
                if (planning[3].get_type() == rclcpp::PARAMETER_STRING)
                    node->set_parameter(rclcpp::Parameter("ompl.request_adapters", planning[3].as_string()));
            }
            
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "⚠️  configure_moveit_params: %s", e.what());
        }
    } else {
        RCLCPP_WARN(node->get_logger(), "⚠️  Could not connect to /move_group for parameter sync");
    }
}

// =============================================================================
// 1. Pick任务构建器
// =============================================================================

mtc::Task build_pick_task(const rclcpp::Node::SharedPtr& node, const PickTaskParams& p) {
    configure_moveit_params(node);
    
    mtc::Task task;
    task.stages()->setName("pick container task");
    task.loadRobotModel(node);
    
    double gripper_close_ratio = 0.30;
    node->get_parameter_or<double>("gripper.close_ratio", gripper_close_ratio, 0.30);
    
    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper"; 
    const std::string hand_frame = "link_tcp";
    
    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);
    
    // 创建规划器（使用params配置）
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(p.params.planner_timeout);
    pipeline_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    pipeline_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    pipeline_planner->setPlannerId("RRTConnect");

    auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
    interpolation_planner->setMaxVelocityScalingFactor(0.5);
    interpolation_planner->setMaxAccelerationScalingFactor(0.6);
    
    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    cartesian_planner->setStepSize(p.params.cartesian_step_size);
    cartesian_planner->setJumpThreshold(p.params.cartesian_jump_threshold);
    
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
        stage->setTimeout(p.params.connect_timeout);
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }
    
    // 阶段4：抓取序列
    {
        auto grasp = std::make_unique<mtc::SerialContainer>("grasp container");
        task.properties().exposeTo(grasp->properties(), { "eef", "group", "ik_frame" });
        grasp->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });
        
        // 4.1 接近物体（垂直向下）
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("approach container", cartesian_planner);
            stage->properties().set("marker_ns", "approach_container");
            stage->properties().set("link", hand_frame);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.safe_approach_height, p.safe_approach_height);
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.z = -1.0;
            stage->setDirection(vec);
            grasp->insert(std::move(stage));
        }
        
        // 4.2 生成抓取姿态
        {
            auto stage = std::make_unique<mtc::stages::GenerateGraspPose>("generate grasp pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "grasp_pose");
            stage->setPreGraspPose("open");
            stage->setObject(p.object_id);
            stage->setAngleDelta(M_PI / 12.0);
            stage->setMonitoredStage(current_state_ptr);
            
            Eigen::Isometry3d grasp_frame_transform;
            grasp_frame_transform.setIdentity();
            Eigen::Quaterniond q = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitX()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitZ());
            grasp_frame_transform.linear() = q.matrix();
            grasp_frame_transform.translation().z() = 0.02;
            
            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("grasp pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(p.params.max_ik_solutions);
            wrapper->setMinSolutionDistance(p.params.min_solution_distance);
            wrapper->setIKFrame(grasp_frame_transform, hand_frame);
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(p.params.ik_timeout);
            grasp->insert(std::move(wrapper));
        }
        
        // 4.3 允许碰撞
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()->getJointModelGroup(hand_group_name)->getLinkModelNamesWithCollisionGeometry(),
                true);
            grasp->insert(std::move(stage));
        }
        
        // 4.4 微插入
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
        
        // 4.6 附着对象
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach container");
            stage->attachObject(p.object_id, hand_frame);
            grasp->insert(std::move(stage));
        }
        
        // 4.7 抬升
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
// 2. Move to Pour任务构建器
// =============================================================================

mtc::Task build_move_to_pour_task(const rclcpp::Node::SharedPtr& node, const MoveToPourTaskParams& p) {
    configure_moveit_params(node);
    
    mtc::Task task;
    task.stages()->setName("move to pour task");
    task.loadRobotModel(node);
    
    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";
    
    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);
    
    // 创建规划器（使用params配置）
    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    cartesian_planner->setStepSize(p.params.cartesian_step_size);
    cartesian_planner->setJumpThreshold(p.params.cartesian_jump_threshold);
    cartesian_planner->setMinFraction(p.min_cartesian_fraction);

    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(p.params.planner_timeout);
    pipeline_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    pipeline_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    pipeline_planner->setPlannerId("RRTConnect");

    auto joint_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
    const double joint6_max_rad_s = 5.0;
    double scaling_from_deg = (p.tilt_speed_deg_s * M_PI / 180.0) / joint6_max_rad_s;
    joint_planner->setMaxVelocityScalingFactor(clamp(scaling_from_deg, 0.05, 1.0));
    joint_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    
    // 阶段1：当前状态
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }
    
    // 阶段2：移动到目标位置
    {
        double goal_qx = p.target_qx;
        double goal_qy = p.target_qy;
        double goal_qz = p.target_qz;
        double goal_qw = p.target_qw;

        if (p.maintain_current_orientation) {
            // 与MCP版对齐：优先用TF读取当前TCP姿态，保持移动过程中末端姿态不变。
            try {
                tf2_ros::Buffer tf_buffer(node->get_clock());
                tf2_ros::TransformListener tf_listener(tf_buffer);
                auto tf = tf_buffer.lookupTransform("link_base", hand_frame, tf2::TimePointZero, std::chrono::milliseconds(500));
                goal_qx = tf.transform.rotation.x;
                goal_qy = tf.transform.rotation.y;
                goal_qz = tf.transform.rotation.z;
                goal_qw = tf.transform.rotation.w;
                RCLCPP_INFO(node->get_logger(), "move_to_pour: keep current ee orientation from TF");
            } catch (const std::exception& e) {
                RCLCPP_WARN(node->get_logger(),
                            "move_to_pour: cannot get current ee orientation from TF (%s); fallback to provided/default quaternion",
                            e.what());
            }
        }

        const double quat_norm = std::sqrt(goal_qx * goal_qx + goal_qy * goal_qy + goal_qz * goal_qz + goal_qw * goal_qw);
        if (quat_norm > 1e-8) {
            goal_qx /= quat_norm;
            goal_qy /= quat_norm;
            goal_qz /= quat_norm;
            goal_qw /= quat_norm;
        } else {
            goal_qx = 0.0;
            goal_qy = 0.0;
            goal_qz = 0.0;
            goal_qw = 1.0;
        }

        // 在创建MoveTo前先做IK可达性探测，自动选择更可达的姿态/高度，避免"Invalid goal state"。
        const auto robot_model = task.getRobotModel();
        const moveit::core::JointModelGroup* arm_jmg = robot_model->getJointModelGroup(arm_group_name);
        moveit::core::RobotState probe_state(robot_model);
        probe_state.setToDefaultValues();

        const auto ik_feasible = [&](double x, double y, double z, double qx, double qy, double qz, double qw) {
            geometry_msgs::msg::Pose pose;
            pose.position.x = x;
            pose.position.y = y;
            pose.position.z = z;
            pose.orientation.x = qx;
            pose.orientation.y = qy;
            pose.orientation.z = qz;
            pose.orientation.w = qw;

            for (int i = 0; i < 8; ++i) {
                probe_state.setToRandomPositions(arm_jmg);
                if (probe_state.setFromIK(arm_jmg, pose, hand_frame, 0.05)) {
                    return true;
                }
            }
            return false;
        };

        std::vector<double> z_candidates;
        z_candidates.push_back(p.target_z);
        z_candidates.push_back(clamp(p.target_z - 0.05, 0.12, 0.85));
        z_candidates.push_back(clamp(p.target_z - 0.10, 0.12, 0.85));
        z_candidates.push_back(clamp(p.target_z + 0.05, 0.12, 0.85));

        bool found_feasible_goal = false;
        double goal_z = p.target_z;
        for (double z_try : z_candidates) {
            if (ik_feasible(p.target_x, p.target_y, z_try, goal_qx, goal_qy, goal_qz, goal_qw)) {
                goal_z = z_try;
                found_feasible_goal = true;
                break;
            }
        }

        if (found_feasible_goal) {
            RCLCPP_INFO(node->get_logger(),
                        "move_to_pour: selected IK-feasible goal (orientation kept) x=%.3f y=%.3f z=%.3f q=(%.3f,%.3f,%.3f,%.3f)",
                        p.target_x, p.target_y, goal_z, goal_qx, goal_qy, goal_qz, goal_qw);
        } else {
            RCLCPP_WARN(node->get_logger(),
                        "move_to_pour: no IK-feasible goal found in probe set, keeping requested pose");
        }

        geometry_msgs::msg::PoseStamped target;
        target.header.frame_id = "link_base";
        target.pose.position.x = p.target_x;
        target.pose.position.y = p.target_y;
        target.pose.position.z = goal_z;
        target.pose.orientation.x = goal_qx;
        target.pose.orientation.y = goal_qy;
        target.pose.orientation.z = goal_qz;
        target.pose.orientation.w = goal_qw;

        auto cartesian_stage = std::make_unique<mtc::stages::MoveTo>("move to target (cartesian)", cartesian_planner);
        cartesian_stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        cartesian_stage->setGroup(arm_group_name);
        cartesian_stage->setIKFrame(hand_frame);
        cartesian_stage->setGoal(target);
        cartesian_stage->setTimeout(p.timeout_sec);
        if (p.cartesian_only) {
            task.add(std::move(cartesian_stage));
            RCLCPP_INFO(node->get_logger(), "move_to_pour: cartesian_only=true, fallback planner disabled");
        } else {
            auto alternatives = std::make_unique<mtc::Alternatives>("move to target");
            alternatives->insert(std::move(cartesian_stage));

            auto fallback_stage = std::make_unique<mtc::stages::MoveTo>("move to target (fallback)", pipeline_planner);
            fallback_stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            fallback_stage->setGroup(arm_group_name);
            fallback_stage->setIKFrame(hand_frame);
            fallback_stage->setGoal(target);
            fallback_stage->setTimeout(p.timeout_sec);
            alternatives->insert(std::move(fallback_stage));

            task.add(std::move(alternatives));
        }
    }
    
    // 阶段3：可选倾倒序列
    if (p.pour_execute) {
        auto pour = std::make_unique<mtc::SerialContainer>("pour");
        task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
        pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });
        
        // 3.1 倾斜开始
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt start", joint_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }
        
        // 3.2 倾倒
        {
            const double tilt_delta_rad = std::abs((p.tilt_end_deg - p.tilt_start_deg) * M_PI / 180.0);
            double desired_T = p.pour_hold_sec > 0.0 ? p.pour_hold_sec : 2.0;
            desired_T = clamp(desired_T, 0.2, 20.0);
            const double v_req = tilt_delta_rad / desired_T;
            double vel_scaling_timed = clamp(v_req / 2.0, 0.05, 1.0);
            
            auto timed_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
            timed_planner->setMaxVelocityScalingFactor(vel_scaling_timed);
            timed_planner->setMaxAccelerationScalingFactor(0.3);
            
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt to end", timed_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_end_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
            
            // 回退
            auto stage2 = std::make_unique<mtc::stages::MoveTo>("return from pour", timed_planner);
            stage2->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal2;
            joint_goal2["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage2->setGoal(joint_goal2);
            pour->insert(std::move(stage2));
        }
        
        task.add(std::move(pour));
    }
    
    // 阶段4：可选递给用户
    if (p.execute_give) {
        auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper", 
                                      std::make_shared<mtc::solvers::JointInterpolationPlanner>());
        stage->setGroup(hand_group_name);
        std::map<std::string, double> open_goal;
        open_goal["drive_joint"] = p.gripper_open_ratio;
        stage->setGoal(open_goal);
        task.add(std::move(stage));

        // Keep planning scene consistent with real release:
        // after opening gripper, restore collisions and detach held object.
        if (!p.object_id.empty()) {
            auto forbid = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid collision");
            forbid->allowCollisions(
                p.object_id,
                task.getRobotModel()->getJointModelGroup(hand_group_name)->getLinkModelNamesWithCollisionGeometry(),
                false);
            task.add(std::move(forbid));

            auto detach = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
            detach->detachObject(p.object_id, hand_frame);
            task.add(std::move(detach));
        }
    }
    
    return task;
}

// =============================================================================
// 3. Place任务构建器
// =============================================================================

mtc::Task build_place_task(const rclcpp::Node::SharedPtr& node, const PlaceTaskParams& p) {
    configure_moveit_params(node);
    
    mtc::Task task;
    task.stages()->setName("place container task");
    task.loadRobotModel(node);
    
    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper";
    const std::string hand_frame = "link_tcp";
    
    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);
    
    // 创建规划器（使用params配置）
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(p.params.planner_timeout);
    pipeline_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    pipeline_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    pipeline_planner->setPlannerId("RRTConnect");

    auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
    interpolation_planner->setMaxVelocityScalingFactor(0.5);
    interpolation_planner->setMaxAccelerationScalingFactor(0.6);
    
    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    cartesian_planner->setStepSize(p.params.cartesian_step_size);
    cartesian_planner->setJumpThreshold(p.params.cartesian_jump_threshold);
    
    // 阶段1：当前状态
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // 阶段2：必要时附着对象（与MCP版place一致，提升状态一致性）
    mtc::Stage* attach_object_stage_ptr = nullptr;
    {
        moveit::planning_interface::PlanningSceneInterface psi;
        bool object_in_world = false;
        try {
            auto objs = psi.getObjects({ p.object_id });
            object_in_world = objs.find(p.object_id) != objs.end();
        } catch (...) {
            object_in_world = true;
        }

        if (object_in_world) {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object for place");
            stage->attachObject(p.object_id, hand_frame);
            attach_object_stage_ptr = stage.get();
            task.add(std::move(stage));
        } else {
            attach_object_stage_ptr = current_state_ptr;
        }
    }

    // 阶段3：连接到放置位置
    {
        auto stage = std::make_unique<mtc::stages::Connect>("move to place location",
            mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, interpolation_planner } });
        stage->setTimeout(std::max(15.0, p.params.connect_timeout));
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }
    
    // 阶段4：放置序列
    {
        auto place = std::make_unique<mtc::SerialContainer>("place container");
        task.properties().exposeTo(place->properties(), { "eef", "group", "ik_frame" });
        place->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });
        
        // 4.1 生成放置姿态
        {
            auto stage = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "place_pose");
            stage->setObject(p.object_id);

            geometry_msgs::msg::PoseStamped target;
            target.header.frame_id = "link_base";
            if (p.target_pose.has_value()) {
                target.pose = p.target_pose.value();
            } else {
                // 兜底默认放置位姿，避免GeneratePlacePose出现 undefined pose。
                target.pose.position.x = 0.0;
                target.pose.position.y = -0.45;
                target.pose.position.z = 0.18;
                target.pose.orientation.w = 1.0;
            }
            stage->setPose(target);
            stage->setMonitoredStage(attach_object_stage_ptr ? attach_object_stage_ptr : current_state_ptr);

            Eigen::Isometry3d place_frame_transform;
            place_frame_transform.setIdentity();
            
            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("place pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(p.params.max_ik_solutions);
            wrapper->setMinSolutionDistance(p.params.min_solution_distance);
            wrapper->setIKFrame(place_frame_transform, p.object_id);
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(p.params.ik_timeout);
            place->insert(std::move(wrapper));
        }

        // 4.2 先向下放置（与MCP版一致，降低释放时瞬间碰撞风险）
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.lower_min, p.lower_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "lower_object");
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.z = -1.0;
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }

        // 4.3 打开夹爪
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper", 
                                          interpolation_planner);
            stage->setGroup(hand_group_name);
            stage->setGoal("open");
            place->insert(std::move(stage));
        }

        // 4.4 禁止碰撞
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid collision");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()->getJointModelGroup(hand_group_name)->getLinkModelNamesWithCollisionGeometry(),
                false);
            place->insert(std::move(stage));
        }

        // 4.5 分离对象
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("detach container");
            stage->detachObject(p.object_id, hand_frame);
            place->insert(std::move(stage));
        }

        // 4.6 后退
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "retreat");
            // 放宽最小后退距离，允许在受限空间中“零距离通过”而不把整条place判失败。
            stage->setMinMaxDistance(0.0, p.retreat_max);
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = hand_frame;
            vec.vector.z = -1.0;
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }
        
        task.add(std::move(place));
    }
    
    return task;
}

// =============================================================================
// 4. Return Home任务构建器
// =============================================================================

mtc::Task build_return_task(const rclcpp::Node::SharedPtr& node, const ReturnTaskParams& p) {
    configure_moveit_params(node);
    
    mtc::Task task;
    task.stages()->setName("return to home task");
    task.loadRobotModel(node);
    
    const std::string arm_group_name = "uf850";
    
    task.setProperty("group", arm_group_name);
    
    // 创建规划器（使用params配置）
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(p.params.planner_timeout);
    pipeline_planner->setMaxVelocityScalingFactor(p.params.velocity_scaling);
    pipeline_planner->setMaxAccelerationScalingFactor(p.params.acceleration_scaling);
    pipeline_planner->setPlannerId("RRTConnect");
    
    // 阶段1：当前状态
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }
    
    // 阶段2：返回home
    {
        auto stage = std::make_unique<mtc::stages::MoveTo>("return to home", pipeline_planner);
        stage->setGroup(arm_group_name);
        
        if (p.target_joints.has_value()) {
            stage->setGoal(p.target_joints.value());
        } else {
            stage->setGoal("home");
        }
        
        stage->setTimeout(p.timeout_sec);
        task.add(std::move(stage));
    }
    
    return task;
}

} // namespace mtc_action_library

