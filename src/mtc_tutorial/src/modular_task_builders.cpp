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
// 1. Pick Task Builder (pick_container)
// =============================================================================

mtc::Task build_pick_task(const rclcpp::Node::SharedPtr& node, const PickTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 pick container task");
    task.loadRobotModel(node);

    // Read gripper closing ratio parameter
    double gripper_close_ratio = 0.30;
    node->get_parameter_or<double>("gripper.close_ratio", gripper_close_ratio, 0.30);

    const std::string arm_group_name = "uf850";
    const std::string hand_group_name = "uf850_gripper"; 
    const std::string hand_frame = "link_tcp";

    task.setProperty("group", arm_group_name);
    task.setProperty("eef", hand_group_name);
    task.setProperty("ik_frame", hand_frame);

    // Create planners
    auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node);
    pipeline_planner->setTimeout(3.0);
    pipeline_planner->setMaxVelocityScalingFactor(0.3);
    pipeline_planner->setMaxAccelerationScalingFactor(0.5);
    pipeline_planner->setPlannerId("RRTConnect");  // Optimized: use fast RRTConnect planner

    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(0.3);
    cartesian_planner->setMaxAccelerationScalingFactor(0.5);
    cartesian_planner->setStepSize(0.008);
    cartesian_planner->setJumpThreshold(0.0);

    // Stage 1: Get current state
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // Stage 1.5: Allow collision between link_base and table (robot base sits adjacent to table)
    {
        auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision (base,table)");
        stage->allowCollisions("table", {"link_base"}, true);
        task.add(std::move(stage));
    }

    // Stage 2: Open gripper
    {
        auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper", 
                                      std::make_shared<mtc::solvers::JointInterpolationPlanner>());
        stage->setGroup(hand_group_name);
        stage->setGoal("open");
        task.add(std::move(stage));
    }

    // Stage 3: Connect to pick location
    {
        auto stage = std::make_unique<mtc::stages::Connect>("move to pick location",
            mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, pipeline_planner } });
        stage->setTimeout(15.0);
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }

    // Stage 4: Grasp sequence
    {
        auto grasp = std::make_unique<mtc::SerialContainer>("grasp container");
        task.properties().exposeTo(grasp->properties(), { "eef", "group", "ik_frame" });
        grasp->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 4.1 Approach object (vertical approach using safe height)
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("approach container", cartesian_planner);
            stage->properties().set("marker_ns", "approach_container");
            stage->properties().set("link", hand_frame);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.safe_approach_height, p.safe_approach_height);
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";  // Use world frame
            vec.vector.z = -1.0;                 // Vertically down
            stage->setDirection(vec);
            grasp->insert(std::move(stage));
        }

        // 4.2 Generate grasp pose (optimized version)
        {
            auto stage = std::make_unique<mtc::stages::GenerateGraspPose>("generate grasp pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "grasp_pose");
            stage->setPreGraspPose("open");
            stage->setObject(p.object_id);
            stage->setAngleDelta(M_PI / 12.0);
            stage->setMonitoredStage(current_state_ptr);

            // Set grasp transform (side grasp)
            Eigen::Isometry3d grasp_frame_transform;
            grasp_frame_transform.setIdentity();
            Eigen::Quaterniond q = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitX()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()) *
                                 Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitZ());
            grasp_frame_transform.linear() = q.matrix();
            grasp_frame_transform.translation().z() = 0.02;

            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("grasp pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(2);  // Optimized: reduced from 16 to 2 solutions
            wrapper->setMinSolutionDistance(0.5);  // Optimized: increased from 0.3 to 0.5 to reduce redundant solutions
            wrapper->setIKFrame(grasp_frame_transform, hand_frame);
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(8.0);
            grasp->insert(std::move(wrapper));
        }

        // 4.3 Allow collision between hand and object
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision (gripper,container)");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()->getJointModelGroup(hand_group_name)->getLinkModelNamesWithCollisionGeometry(),
                true);
            grasp->insert(std::move(stage));
        }

        // 4.4 Micro-insertion for grasp stability
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

        // 4.5 Close gripper
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("close gripper", 
                                          std::make_shared<mtc::solvers::JointInterpolationPlanner>());
            stage->setGroup(hand_group_name);
            std::map<std::string, double> close_goal;
            close_goal["drive_joint"] = gripper_close_ratio;
            stage->setGoal(close_goal);
            grasp->insert(std::move(stage));
        }

        // 4.6 Attach object to gripper
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach container");
            stage->attachObject(p.object_id, hand_frame);
            grasp->insert(std::move(stage));
        }

        // 4.7 Lift object
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
// 2. Pour-Only Task Builder (pour_to_target)
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

    // Create planners
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

    // Stage 1: Get current state
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // Stage 2: Pour sequence
    {
        auto pour = std::make_unique<mtc::SerialContainer>("pour water");
        task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
        pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });
        
        // 2.1 Move to pour position (Y-axis movement)
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("move to pour position", slow_cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.move_to_pour_min, p.move_to_pour_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "move_to_pour");
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.y = -1.0;  // Move along -Y direction
            stage->setDirection(vec);
            pour->insert(std::move(stage));
        }

        // 2.2 Tilt start
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt start", slow_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }

        // Time-based deceleration: calculate velocity scaling for start→end and end→start based on pour_hold_sec
        {
            const double joint6_max_rad_s = 2.0;
            const double tilt_delta_rad = std::abs((p.tilt_end_deg - p.tilt_start_deg) * M_PI / 180.0);
            double desired_T = p.pour_hold_sec > 0.0 ? p.pour_hold_sec
                              : (tilt_delta_rad / std::max(p.tilt_speed_deg_s * M_PI / 180.0, 1e-3));
            desired_T = clamp(desired_T, 0.2, 20.0);
            const double v_req = tilt_delta_rad / desired_T;
            double vel_scaling_timed = clamp(v_req / joint6_max_rad_s, 0.05, 1.0);
            RCLCPP_INFO(node->get_logger(), "Pour timing control (independent): delta=%.3frad (~%.1f deg), T=%.2fs, v_req=%.3f, scaling=%.2f",
                        tilt_delta_rad, tilt_delta_rad * 180.0 / M_PI, desired_T, v_req, vel_scaling_timed);

            auto timed_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
            timed_interpolation_planner->setMaxVelocityScalingFactor(vel_scaling_timed);
            timed_interpolation_planner->setMaxAccelerationScalingFactor(0.3);

            // Tilt from start to end with controlled duration
            {
                auto stage = std::make_unique<mtc::stages::MoveTo>("tilt to end (timed)", timed_interpolation_planner);
                stage->setGroup(arm_group_name);
                std::map<std::string, double> joint_goal;
                joint_goal["joint6"] = p.tilt_end_deg * M_PI / 180.0;
                stage->setGoal(joint_goal);
                pour->insert(std::move(stage));
            }
            // Return from end → start with controlled duration
            {
                auto stage = std::make_unique<mtc::stages::MoveTo>("return from pour (timed)", timed_interpolation_planner);
                stage->setGroup(arm_group_name);
                std::map<std::string, double> joint_goal;
                joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
                stage->setGoal(joint_goal);
                pour->insert(std::move(stage));
            }
        }

        // 2.5 Return from pour position
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
// 3. Place Task Builder (place_container)
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

    // Create planners
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

    // Stage 1: Get current state
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // Stage 1.5: Allow collision between link_base and table (robot base sits adjacent to table)
    {
        auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision (base,table)");
        stage->allowCollisions("table", {"link_base"}, true);
        task.add(std::move(stage));
    }

    // Stage 2: Attach object to gripper (simulate already grasped state) - critical state management
    mtc::Stage* attach_object_stage_ptr = nullptr;
    {
        // Check if target object still exists in world collision objects; skip if already grasped
        moveit::planning_interface::PlanningSceneInterface psi;
        bool object_in_world = false;
        try {
            auto objs = psi.getObjects({ p.object_id });
            object_in_world = objs.find(p.object_id) != objs.end();
        } catch (...) {
            object_in_world = true; // Conservative: perform attachment
        }
        if (object_in_world) {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object for place");
            stage->attachObject(p.object_id, hand_frame);
            attach_object_stage_ptr = stage.get();  // Save pointer for monitoring
            task.add(std::move(stage));
        } else {
            // Already attached to hand, use current state as monitoring reference
            attach_object_stage_ptr = current_state_ptr;
        }
    }

    // Stage 3: Connect to place location
    {
        auto stage = std::make_unique<mtc::stages::Connect>(
            "move to place",
            mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, interpolation_planner } });
        stage->setTimeout(15.0);
        stage->properties().configureInitFrom(mtc::Stage::PARENT);
        task.add(std::move(stage));
    }

    // Stage 4: Place container sequence (full version, following mtc_tutorial.cpp)
    {
        auto place = std::make_unique<mtc::SerialContainer>("place object");
        task.properties().exposeTo(place->properties(), { "eef", "group", "ik_frame" });
        place->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 4.1 Generate place pose - using full GeneratePlacePose
        {
            auto stage = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
            stage->properties().configureInitFrom(mtc::Stage::PARENT);
            stage->properties().set("marker_ns", "place_pose");
            stage->setObject(p.object_id);

            // Set target place position
            geometry_msgs::msg::PoseStamped target_pose_msg;
            target_pose_msg.header.frame_id = "link_base";
            if (p.target_pose.has_value()) {
                target_pose_msg.pose = p.target_pose.value();
            } else {
                // Use default place position
                target_pose_msg.pose.position.x = 0.0;
                target_pose_msg.pose.position.y = -0.45;
                target_pose_msg.pose.position.z = 0.18;
                target_pose_msg.pose.orientation.w = 1.0;
            }
            stage->setPose(target_pose_msg);
            
            // Critical: set monitored stage - required for GeneratePlacePose to work correctly
            if (attach_object_stage_ptr) {
                stage->setMonitoredStage(attach_object_stage_ptr);
            }

            // Compute IK
            auto wrapper = std::make_unique<mtc::stages::ComputeIK>("place pose IK", std::move(stage));
            wrapper->setMaxIKSolutions(1);
            wrapper->setMinSolutionDistance(0.5);
            
            // Define object frame for placing - keep object vertical
            Eigen::Isometry3d place_frame_transform;
            place_frame_transform.setIdentity();
            wrapper->setIKFrame(place_frame_transform, p.object_id);
            
            wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
            wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
            wrapper->setTimeout(5.0);
            place->insert(std::move(wrapper));
        }

        // 4.2 Lower object to place position
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.lower_min, p.lower_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "lower_object");
            
            // Set downward direction
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = "link_base";
            vec.vector.z = -1.0;
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }

        // 4.3 Open gripper to release object
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("release object", interpolation_planner);
            stage->setGroup(hand_group_name);
            stage->setGoal("open");
            place->insert(std::move(stage));
        }

        // 4.4 Forbid collision between hand and object
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid collision (hand,object)");
            stage->allowCollisions(p.object_id,
                task.getRobotModel()
                    ->getJointModelGroup(hand_group_name)
                    ->getLinkModelNamesWithCollisionGeometry(),
                false);
            place->insert(std::move(stage));
        }

        // 4.5 Detach object
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
            stage->detachObject(p.object_id, hand_frame);
            place->insert(std::move(stage));
        }

        // 4.6 Retreat
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(p.retreat_min, p.retreat_max);
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "retreat");

            // Set retreat direction
            geometry_msgs::msg::Vector3Stamped vec;
            vec.header.frame_id = hand_frame;
            vec.vector.z = -1.0;  // Backward
            stage->setDirection(vec);
            place->insert(std::move(stage));
        }
        
        task.add(std::move(place));
    }

    return task;
}

// =============================================================================
// 4. Return Task Builder (return_to_home)
// =============================================================================

mtc::Task build_return_task(const rclcpp::Node::SharedPtr& node, const ReturnTaskParams& p) {
    configure_moveit_params(node);
    sync_robot_model_params(node);

    mtc::Task task;
    task.stages()->setName("uf850 return home task");
    task.loadRobotModel(node);

    const std::string arm_group_name = "uf850";
    const std::string hand_frame = "link_tcp";  // Add hand_frame definition

    task.setProperty("group", arm_group_name);

    // Create planners
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

    // Stage 1: Get current state
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // Stage 1.5: Safe lift to safe height
    {
        auto stage = std::make_unique<mtc::stages::MoveRelative>("safe lift before return", cartesian_planner);
        stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        stage->setIKFrame(hand_frame);
        stage->properties().set("marker_ns", "safe_lift_return");
        stage->setMinMaxDistance(0.08, 0.12);  // Safe lift height 8-12cm
        geometry_msgs::msg::Vector3Stamped vec;
        vec.header.frame_id = "link_base";
        vec.vector.z = 1.0;  // Vertically upward
        stage->setDirection(vec);
        task.add(std::move(stage));
    }

    // Stage 2: Return to initial position
    {
        auto stage = std::make_unique<mtc::stages::MoveTo>("return to home", pipeline_planner);
        stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
        stage->setGroup(arm_group_name);
        
        if (p.target_joints.has_value()) {
            // Use specified joint target
            stage->setGoal(p.target_joints.value());
        } else {
            // Use "home" configuration
            stage->setGoal("home");
        }
        
        stage->setTimeout(p.timeout_sec);
        task.add(std::move(stage));
    }

    return task;
}



// =============================================================================
// 5. Move-to-Pour Task Builder (move_to_pour_position) - Advanced Optimized Version
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

    // Create optimized Cartesian planner (based on simplified parameters)
    auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
    cartesian_planner->setMaxVelocityScalingFactor(p.velocity_scaling);
    cartesian_planner->setMaxAccelerationScalingFactor(p.acceleration_scaling);
    cartesian_planner->setStepSize(p.step_size);
    cartesian_planner->setJumpThreshold(0.0);
    cartesian_planner->setMinFraction(p.min_cartesian_fraction);

    // Stage 1: Get current state
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        task.add(std::move(stage));
    }

    // Stage 2: Move directly to target position (simplified version)
    {
        RCLCPP_INFO(node->get_logger(), "Moving to target: (%.3f, %.3f, %.3f), velocity: %.2f", 
                   p.target_x, p.target_y, p.target_z, p.velocity_scaling);

        geometry_msgs::msg::PoseStamped target_pose_msg;
        target_pose_msg.header.frame_id = "link_base";
        target_pose_msg.pose.position.x = p.target_x;
        target_pose_msg.pose.position.y = p.target_y;
        target_pose_msg.pose.position.z = p.target_z;

        // Try to get and maintain current orientation
        try {
            tf2_ros::Buffer tf_buffer(node->get_clock());
            tf2_ros::TransformListener tf_listener(tf_buffer);
            auto tf = tf_buffer.lookupTransform("link_base", hand_frame, 
                                              tf2::TimePointZero, std::chrono::milliseconds(500));
            target_pose_msg.pose.orientation = tf.transform.rotation;
            RCLCPP_INFO(node->get_logger(), "Maintaining current orientation");
        } catch (const std::exception& e) {
            RCLCPP_WARN(node->get_logger(), "Cannot get current orientation, using default");
            // Use default upright orientation
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

    // Optional: Stage 3-6 simple pour sequence (merged from pour_only), only when pour_execute is true
    if (p.pour_execute) {
        RCLCPP_INFO(node->get_logger(), "Enabling pour sequence: start=%.1f deg, end=%.1f deg, speed=%.1f deg/s, hold=%.1fs",
                    p.tilt_start_deg, p.tilt_end_deg, p.tilt_speed_deg_s, p.pour_hold_sec);

        const double joint6_max_rad_s = 2.0;
        const double tilt_delta_rad = std::abs((p.tilt_end_deg - p.tilt_start_deg) * M_PI / 180.0);
        double desired_T = p.pour_hold_sec > 0.0 ? p.pour_hold_sec
                          : (tilt_delta_rad / std::max(p.tilt_speed_deg_s * M_PI / 180.0, 1e-3));
        // Clamp desired duration to [0.2s, 20s] range to avoid outliers
        desired_T = clamp(desired_T, 0.2, 20.0);
        const double v_req = tilt_delta_rad / desired_T;
        double vel_scaling_timed = clamp(v_req / joint6_max_rad_s, 0.05, 1.0);

        RCLCPP_INFO(node->get_logger(), "Pour timing control: delta=%.3frad (~%.1f deg), T=%.2fs, v_req=%.3f rad/s, scaling=%.2f",
                    tilt_delta_rad, tilt_delta_rad * 180.0 / M_PI, desired_T, v_req, vel_scaling_timed);

        auto timed_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
        timed_interpolation_planner->setMaxVelocityScalingFactor(vel_scaling_timed);
        timed_interpolation_planner->setMaxAccelerationScalingFactor(0.3);

        auto pour = std::make_unique<mtc::SerialContainer>("pour water");
        task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
        pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // Tilt start (reach start angle)
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt start", timed_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_start_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }
        // Tilt from start → end with controlled duration
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("tilt to end (timed)", timed_interpolation_planner);
            stage->setGroup(arm_group_name);
            std::map<std::string, double> joint_goal;
            joint_goal["joint6"] = p.tilt_end_deg * M_PI / 180.0;
            stage->setGoal(joint_goal);
            pour->insert(std::move(stage));
        }
        // Return from end → start with controlled duration
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

    // Optional: Stage 7 give-to-user action (open gripper), only when execute_give is true
    if (p.execute_give) {
        RCLCPP_INFO(node->get_logger(), "Enabling give-to-user action: gripper_open_ratio=%.2f", p.gripper_open_ratio);

        auto give = std::make_unique<mtc::SerialContainer>("give to user");
        task.properties().exposeTo(give->properties(), { "eef", "group", "ik_frame" });
        give->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 7.1 Optional: Retreat slightly for user to take object
        {
            auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat for user", cartesian_planner);
            stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
            stage->setMinMaxDistance(0.02, 0.05); // Retreat 2-5cm
            stage->setIKFrame(hand_frame);
            stage->properties().set("marker_ns", "retreat_for_user");
            
            // Retreat along hand frame -X direction (typically backward)
            geometry_msgs::msg::Vector3Stamped retreat_vec;
            retreat_vec.header.frame_id = hand_frame;
            retreat_vec.vector.z = +0.5;
            stage->setDirection(retreat_vec);
            
            give->insert(std::move(stage));
        }

        // 7.2 Open gripper to specified ratio
        {
            auto stage = std::make_unique<mtc::stages::MoveTo>("open gripper for user", 
                                                               std::make_shared<mtc::solvers::JointInterpolationPlanner>());
            stage->setGroup(hand_group_name);
            
            // Smart gripper control: if fully open (1.0), use predefined "open" pose
            // Otherwise use custom joint value
            if (std::abs(p.gripper_open_ratio - 1.0) < 0.01) {  // Nearly fully open
                stage->setGoal("open");  // Use "open" pose defined in SRDF
                RCLCPP_INFO(node->get_logger(), "Using predefined 'open' pose to fully open gripper");
            } else {
                // Calculate gripper joint value: gripper_open_ratio (0.0=fully closed, 1.0=fully open)
                // UF850 gripper uses drive_joint: 0.0=fully open, 0.85=fully closed
                double max_gripper_closing = 0.85; // UF850 gripper max closing value
                double gripper_target = (1.0 - p.gripper_open_ratio) * max_gripper_closing; // Reverse mapping: 1.0->0.0, 0.0->0.85
                
                std::map<std::string, double> gripper_goal;
                gripper_goal["drive_joint"] = gripper_target;
                stage->setGoal(gripper_goal);
                
                RCLCPP_INFO(node->get_logger(), "UF850 gripper custom position: %.4f (drive_joint, 0.0=open, 0.85=closed) - user requested ratio: %.2f", 
                           gripper_target, p.gripper_open_ratio);
            }
            
            stage->setTimeout(3.0); // Give gripper action enough time
            give->insert(std::move(stage));
        }

        // 7.3 Release object: detach object and restore collision checking
        {
            auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("release and restore object");
            
            // Get all collision geometries of gripper
            auto gripper_links = task.getRobotModel()
                ->getJointModelGroup(hand_group_name)
                ->getLinkModelNamesWithCollisionGeometry();
            
            // Smart object release: try to detach and restore common object names
            std::vector<std::string> possible_objects = {
                "object", "object_1", "object_2", "object_3", "object_4", "object_5",
                "bowl", "bowl_1", "bowl_2", "bowl_3", "cup", "cup_1", "container"
            };
            
            int released_count = 0;
            for (const auto& obj_name : possible_objects) {
                try {
                    // Detach object (ignored by MTC if object not attached)
                    stage->detachObject(obj_name, hand_frame);
                    
                    // Restore collision checking (re-enable collision between gripper and object)
                    stage->allowCollisions(obj_name, gripper_links, false);  // false = re-enable collision checking
                    
                    released_count++;
                    RCLCPP_DEBUG(node->get_logger(), "Released object and restored collision: %s", obj_name.c_str());
                    
                } catch (const std::exception& e) {
                    // Ignore operation failures (object may not exist or not be attached)
                    RCLCPP_DEBUG(node->get_logger(), "Cannot process object %s: %s", obj_name.c_str(), e.what());
                } catch (...) {
                    // Ignore other exceptions
                }
            }
            
            RCLCPP_INFO(node->get_logger(), "Released %d possible objects and restored collision checking, object can now be safely taken by user", released_count);
            give->insert(std::move(stage));
        }



        task.add(std::move(give));
    }

    RCLCPP_INFO(node->get_logger(), "Simplified move task configured - velocity: %.2f, timeout: %.1fs%s%s", 
               p.velocity_scaling, p.timeout_sec,
               p.pour_execute ? ", includes pouring" : "",
               p.execute_give ? ", includes give-to-user" : "");

    return task;
}



// =============================================================================
// 7. Pre-Pour Task Builder (pre_pour)
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

    // Planners
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

    // Stage 1: Current state
    mtc::Stage* current_state_ptr = nullptr;
    {
        auto stage = std::make_unique<mtc::stages::CurrentState>("current state");
        current_state_ptr = stage.get();
        task.add(std::move(stage));
    }

    // Stage 2: Connect to pre-pose (solve start connectivity)
    // Removed Connect stage, directly enter pre-pour container to avoid init failure without full scene/state

    // Stage 3: Pre-pour container
    {
        auto pre = std::make_unique<mtc::SerialContainer>("pre-pour");
        task.properties().exposeTo(pre->properties(), { "eef", "group", "ik_frame" });
        pre->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

        // 3.1 Generate pre-pour pose
        geometry_msgs::msg::PoseStamped target_pose_msg;
        target_pose_msg.header.frame_id = "link_base";
        target_pose_msg.pose.position.x = p.target_x;
        target_pose_msg.pose.position.y = p.target_y;
        target_pose_msg.pose.position.z = p.target_z + p.safe_lift_z;

        // Calculate orientation: maintain current roll/pitch, optionally align yaw to target
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
            RCLCPP_WARN(node->get_logger(), "Pre-pour pose: cannot get current orientation, using default upright");
            target_pose_msg.pose.orientation.w = 1.0;
            target_pose_msg.pose.orientation.x = 0.0;
            target_pose_msg.pose.orientation.y = 0.0;
            target_pose_msg.pose.orientation.z = 0.0;
        }

        // Directly use MoveTo with target pose for pre-pour positioning (no separate GeneratePose/ComputeIK needed)
        
        // 3.2 Move to pre-pour pose (final approach optionally Cartesian)
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