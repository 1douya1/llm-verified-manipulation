#include <rclcpp/rclcpp.hpp>
#include <moveit/planning_scene/planning_scene.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <moveit/task_constructor/task.h>
#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <moveit/move_group_interface/move_group_interface.h>
#include <thread>
#include <chrono>
#include <vector>
#if __has_include(<tf2_geometry_msgs/tf2_geometry_msgs.hpp>)
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#else
#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#endif
#if __has_include(<tf2_eigen/tf2_eigen.hpp>)
#include <tf2_eigen/tf2_eigen.hpp>
#else
#include <tf2_eigen/tf2_eigen.h>
#endif

static const rclcpp::Logger LOGGER = rclcpp::get_logger("mtc_tutorial");
namespace mtc = moveit::task_constructor;

class MTCTaskNode
{
public:
  MTCTaskNode(const rclcpp::NodeOptions& options);

  rclcpp::node_interfaces::NodeBaseInterface::SharedPtr getNodeBaseInterface();

  void doTask();

  void setupPlanningScene();

private:
  // Compose an MTC task from a series of stages.
  mtc::Task createTask();
  mtc::Task task_;
  rclcpp::Node::SharedPtr node_;
  // 夹爪参数：xArm驱动关节 close 名义值≈0.85，支持按比例半闭
  double gripper_close_ratio_ = 0.33;    // 1/3 闭合
  const double gripper_close_full_ = 0.85; // SRDF "close" 的驱动关节目标
};

rclcpp::node_interfaces::NodeBaseInterface::SharedPtr MTCTaskNode::getNodeBaseInterface()
{
  return node_->get_node_base_interface();
}

MTCTaskNode::MTCTaskNode(const rclcpp::NodeOptions& options)
  : node_{ std::make_shared<rclcpp::Node>("mtc_tutorial_node", options) }
{
    // 夹爪参数（可通过 ros 参数覆盖）
    node_->declare_parameter("gripper_close_ratio", gripper_close_ratio_);
    node_->get_parameter("gripper_close_ratio", gripper_close_ratio_);
    // 声明基本的MoveIt参数
    node_->declare_parameter("robot_description", "");
    node_->declare_parameter("robot_description_semantic", "");
    
    // 声明规划器相关参数
    node_->declare_parameter("default_planning_pipeline", "ompl");
    node_->declare_parameter("planning_pipelines", std::vector<std::string>{"ompl"});
    node_->declare_parameter("ompl.planning_plugin", "ompl_interface/OMPLPlanner");
    
    // 关键：声明请求适配器参数，确保包含时间参数化
    node_->declare_parameter("ompl.request_adapters", 
        "default_planner_request_adapters/AddTimeOptimalParameterization "
        "default_planner_request_adapters/FixWorkspaceBounds "
        "default_planner_request_adapters/FixStartStateBounds "
        "default_planner_request_adapters/FixStartStateCollision "
        "default_planner_request_adapters/FixStartStatePathConstraints");
    
    // 声明OMPL特定参数
    node_->declare_parameter("ompl.start_state_max_bounds_error", 0.1);
    node_->declare_parameter("ompl.jiggle_fraction", 0.05);
    node_->declare_parameter("ompl.max_planning_threads", 4);
    node_->declare_parameter("ompl.simplify_solutions", true);
    node_->declare_parameter("ompl.minimum_waypoint_count", 2);
    
    // 声明执行器相关参数
    node_->declare_parameter("trajectory_execution.allowed_execution_duration_scaling", 1.2);
    node_->declare_parameter("trajectory_execution.allowed_goal_duration_margin", 0.5);
    node_->declare_parameter("trajectory_execution.allowed_start_tolerance", 0.01);
    node_->declare_parameter("trajectory_execution.execution_duration_monitoring", true);
    node_->declare_parameter("trajectory_execution.wait_for_trajectory_completion", true);
    node_->declare_parameter("moveit_controller_manager", "moveit_simple_controller_manager/MoveItSimpleControllerManager");
    
    // 只为主臂声明kinematics参数（gripper不需要）
    node_->declare_parameter("robot_description_kinematics.uf850.kinematics_solver", "");
    node_->declare_parameter("robot_description_kinematics.uf850.kinematics_solver_search_resolution", 0.005);
    node_->declare_parameter("robot_description_kinematics.uf850.kinematics_solver_timeout", 0.005);
    node_->declare_parameter("robot_description_kinematics.uf850.kinematics_solver_attempts", 3);
    
    RCLCPP_INFO(LOGGER, "Waiting for move_group parameters...");
    
    // 首先加载joint_limits参数 - 这对执行至关重要
    RCLCPP_INFO(LOGGER, "Loading joint limits configuration...");
    node_->declare_parameter("robot_description_planning.joint_limits.joint1.has_acceleration_limits", true);
    node_->declare_parameter("robot_description_planning.joint_limits.joint1.max_acceleration", 5.0);  // 保守值
    node_->declare_parameter("robot_description_planning.joint_limits.joint1.has_velocity_limits", true);
    node_->declare_parameter("robot_description_planning.joint_limits.joint1.max_velocity", 1.0);
    
    for (int i = 2; i <= 6; i++) {
        std::string joint_name = "joint" + std::to_string(i);
        node_->declare_parameter("robot_description_planning.joint_limits." + joint_name + ".has_acceleration_limits", true);
        node_->declare_parameter("robot_description_planning.joint_limits." + joint_name + ".max_acceleration", 5.0);
        node_->declare_parameter("robot_description_planning.joint_limits." + joint_name + ".has_velocity_limits", true);
        node_->declare_parameter("robot_description_planning.joint_limits." + joint_name + ".max_velocity", 1.0);
    }
    
    auto param_client = std::make_shared<rclcpp::SyncParametersClient>(node_, "/move_group");
    
    if (param_client->wait_for_service(std::chrono::seconds(30))) {
        try {
            // 获取基本参数
            auto basic_params = param_client->get_parameters({
                "robot_description", 
                "robot_description_semantic"
            });
            
            // 获取规划器参数
            auto planning_params = param_client->get_parameters({
                "default_planning_pipeline",
                "planning_pipelines",
                "ompl.planning_plugin",
                "ompl.request_adapters"  // 重要：获取请求适配器列表
            });
            
            // 获取执行器参数 - 确保与move_group一致
            auto execution_params = param_client->get_parameters({
                "trajectory_execution.allowed_execution_duration_scaling",
                "trajectory_execution.allowed_goal_duration_margin", 
                "trajectory_execution.allowed_start_tolerance",
                "moveit_controller_manager"
            });
            
            // 只获取主臂的kinematics参数
            auto kinematics_params = param_client->get_parameters({
                "robot_description_kinematics.uf850.kinematics_solver",
                "robot_description_kinematics.uf850.kinematics_solver_search_resolution",
                "robot_description_kinematics.uf850.kinematics_solver_timeout",
                "robot_description_kinematics.uf850.kinematics_solver_attempts"
            });
            
            if (basic_params.size() >= 2) {
                // 设置基本参数
                node_->set_parameter(rclcpp::Parameter("robot_description", basic_params[0].as_string()));
                node_->set_parameter(rclcpp::Parameter("robot_description_semantic", basic_params[1].as_string()));
                
                // 设置规划器参数
                if (planning_params.size() >= 4) {
                    node_->set_parameter(rclcpp::Parameter("default_planning_pipeline", planning_params[0].as_string()));
                    node_->set_parameter(rclcpp::Parameter("planning_pipelines", planning_params[1].as_string_array()));
                    node_->set_parameter(rclcpp::Parameter("ompl.planning_plugin", planning_params[2].as_string()));
                    // 关键：设置请求适配器
                    std::string adapters = planning_params[3].as_string();
                    RCLCPP_INFO(LOGGER, "Request adapters from move_group: %s", adapters.c_str());
                    // 确保包含时间参数化适配器
                    if (adapters.find("AddTimeOptimalParameterization") == std::string::npos) {
                        RCLCPP_WARN(LOGGER, "AddTimeOptimalParameterization not found in adapters, adding it");
                        adapters = "default_planner_request_adapters/AddTimeOptimalParameterization " + adapters;
                    }
                    node_->set_parameter(rclcpp::Parameter("ompl.request_adapters", adapters));
                } else {
                    RCLCPP_WARN(LOGGER, "Could not get planning parameters, using default OMPL configuration");
                    node_->set_parameter(rclcpp::Parameter("default_planning_pipeline", "ompl"));
                    node_->set_parameter(rclcpp::Parameter("planning_pipelines", std::vector<std::string>{"ompl"}));
                    node_->set_parameter(rclcpp::Parameter("ompl.planning_plugin", "ompl_interface/OMPLPlanner"));
                    // 确保设置正确的请求适配器
                    node_->set_parameter(rclcpp::Parameter("ompl.request_adapters", 
                        "default_planner_request_adapters/AddTimeOptimalParameterization "
                        "default_planner_request_adapters/FixWorkspaceBounds "
                        "default_planner_request_adapters/FixStartStateBounds "
                        "default_planner_request_adapters/FixStartStateCollision "
                        "default_planner_request_adapters/FixStartStatePathConstraints"));
                }
                
                // 设置执行器参数 - 与move_group保持完全一致，但使用更宽松的设置
                if (execution_params.size() >= 4) {
                    try {
                        // 使用更宽松的执行参数来避免超时
                        node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_execution_duration_scaling", 5.0));  // 慢速轨迹需要更宽松时长
                        node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_goal_duration_margin", 2.0));     // 增加余量
                        node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_start_tolerance", 0.05));        // 增加起始容忍度
                        node_->set_parameter(rclcpp::Parameter("moveit_controller_manager", execution_params[3].as_string()));
                        RCLCPP_INFO(LOGGER, "Successfully obtained execution configuration from move_group with relaxed parameters");
                    } catch (const std::exception& ex) {
                        RCLCPP_WARN(LOGGER, "Failed to set execution parameters from move_group: %s", ex.what());
                        RCLCPP_WARN(LOGGER, "Using declared default execution parameters");
                    }
                } else {
                    RCLCPP_WARN(LOGGER, "Could not get execution parameters, using relaxed defaults compatible with move_group");
                    // 设置更宽松的默认值
                    node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_execution_duration_scaling", 5.0));
                    node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_goal_duration_margin", 2.0));
                    node_->set_parameter(rclcpp::Parameter("trajectory_execution.allowed_start_tolerance", 0.05));
                }
                
                // 设置主臂的kinematics参数
                if (kinematics_params.size() >= 4 && !kinematics_params[0].as_string().empty()) {
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver", kinematics_params[0].as_string()));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_search_resolution", kinematics_params[1].as_double()));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_timeout", kinematics_params[2].as_double()));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_attempts", kinematics_params[3].as_int()));
                    
                    RCLCPP_INFO(LOGGER, "Successfully obtained MoveIt configuration parameters");
                } else {
                    RCLCPP_WARN(LOGGER, "Could not get kinematics parameters, setting defaults for uf850 arm");
                    // 设置默认的kinematics配置（只为主臂）
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver", "kdl_kinematics_plugin/KDLKinematicsPlugin"));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_search_resolution", 0.005));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_timeout", 0.005));
                    node_->set_parameter(rclcpp::Parameter("robot_description_kinematics.uf850.kinematics_solver_attempts", 3));
                }
            } else {
                RCLCPP_WARN(LOGGER, "Could not get basic robot description parameters from move_group");
            }
        } catch (const std::exception& e) {
            RCLCPP_WARN(LOGGER, "Failed to get parameters from move_group: %s", e.what());
            RCLCPP_WARN(LOGGER, "Using declared default parameters");
        }
    } else {
        RCLCPP_WARN(LOGGER, "move_group parameter service not available, using declared default configuration");
    }
}

void MTCTaskNode::setupPlanningScene()
{
  moveit::planning_interface::PlanningSceneInterface psi;
  
  // 1. 添加台面碰撞对象 (OptoSigma光学面包板)
  moveit_msgs::msg::CollisionObject table_surface;
  table_surface.id = "table_surface";
  table_surface.header.frame_id = "link_base";
  table_surface.primitives.resize(1);
  table_surface.primitives[0].type = shape_msgs::msg::SolidPrimitive::BOX;
  table_surface.primitives[0].dimensions = { 1.0, 1.5, 0.01 };  // 长x宽x高 (米)

  geometry_msgs::msg::Pose table_pose;
  table_pose.position.x = 0.0;   // 台面中心相对于机械臂基座
  table_pose.position.y = -0.25;   
  table_pose.position.z = -0.01;  // 台面高度，低于机械臂基座
  table_pose.orientation.w = 1.0;
  table_surface.pose = table_pose;
  table_surface.operation = moveit_msgs::msg::CollisionObject::ADD;
  
  // 2. 添加台面支撑结构 
  moveit_msgs::msg::CollisionObject table_base;
  table_base.id = "table_base";
  table_base.header.frame_id = "link_base";
  table_base.primitives.resize(1);
  table_base.primitives[0].type = shape_msgs::msg::SolidPrimitive::BOX;
  table_base.primitives[0].dimensions = { 0.7, 0.7, 0.05 };  // 长x宽x高 (米)
  // 底座位置，高于台面0.05米
  geometry_msgs::msg::Pose base_pose;
  base_pose.position.x = 0.0;
  base_pose.position.y = -0.55;
  base_pose.position.z = 0.025;  // 底座位置，低于台面
  base_pose.orientation.w = 1.0;
  table_base.pose = base_pose;
  table_base.operation = moveit_msgs::msg::CollisionObject::ADD;
  
  
  
  // 添加目标物体 (原来的圆柱体)
  moveit_msgs::msg::CollisionObject object;
  object.id = "object";
  object.header.frame_id = "link_base";
  object.primitives.resize(1);
  object.primitives[0].type = shape_msgs::msg::SolidPrimitive::CYLINDER;
  object.primitives[0].dimensions = { 0.1, 0.02 };  // 高度10cm，半径2cm

  geometry_msgs::msg::Pose pose;
  pose.position.x = 0.0;   // 更近一些，确保可达
  pose.position.y = -0.4;  // Y方向位置
  pose.position.z = 0.13;  // Z方向位置，台面上方
  pose.orientation.w = 1.0;
  object.pose = pose;
  object.operation = moveit_msgs::msg::CollisionObject::ADD;

  // 应用所有碰撞对象
  std::vector<moveit_msgs::msg::CollisionObject> collision_objects;
  collision_objects.push_back(table_surface);
  collision_objects.push_back(table_base);
  collision_objects.push_back(object);
  
  psi.applyCollisionObjects(collision_objects);
  
  RCLCPP_INFO(LOGGER, "Added workspace collision objects: table_surface, table_base, and target object");
  RCLCPP_INFO(LOGGER, "Target object position: x=%.3f, y=%.3f, z=%.3f", pose.position.x, pose.position.y, pose.position.z);
  RCLCPP_INFO(LOGGER, "Table surface position: x=%.3f, y=%.3f, z=%.3f", table_pose.position.x, table_pose.position.y, table_pose.position.z);
  RCLCPP_INFO(LOGGER, "Object height above table: %.3f meters", pose.position.z - table_pose.position.z);
}

void MTCTaskNode::doTask()
{
  task_ = createTask();

  try
  {
    task_.init();
  }
  catch (mtc::InitStageException& e)
  {
    RCLCPP_ERROR_STREAM(LOGGER, e);
    return;
  }

  if (!task_.plan(2))  // 降低最大解决方案数量
  {
    RCLCPP_ERROR_STREAM(LOGGER, "Task planning failed");
    return;
  }

  // 规划成功后的处理
  RCLCPP_INFO(LOGGER, "Planning successful! Found %zu solutions", task_.solutions().size());
  
  // 获取最佳解决方案
  const auto& solution = *task_.solutions().front();
  RCLCPP_INFO(LOGGER, "Best solution cost: %.3f", solution.cost());
  
  // 发布解决方案用于RViz可视化
  RCLCPP_INFO(LOGGER, "Publishing solution for visualization in RViz...");
  task_.introspection().publishSolution(solution);
  
  // 启用执行以测试OMPL参数是否修复了时间戳问题
  bool execute_enabled = true;  // 设置为true以测试执行
  
  if (execute_enabled) {
    RCLCPP_INFO(LOGGER, "Execution is enabled. Starting task execution...");
    
    // 打印解决方案的基本信息
    RCLCPP_INFO(LOGGER, "Solution cost: %.3f", solution.cost());
    RCLCPP_INFO(LOGGER, "Using OMPL planner with time parameterization adapter");
    
    // 等待一段时间确保系统稳定
    RCLCPP_INFO(LOGGER, "Waiting 2 seconds for system to stabilize before execution...");
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 尝试执行任务
    RCLCPP_INFO(LOGGER, "Calling task.execute()...");
    auto result = task_.execute(solution);
    if (result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS)
    {
      RCLCPP_ERROR_STREAM(LOGGER, "Task execution failed with error code: " << result.val);
      // 打印更多错误信息
      switch(result.val) {
        case moveit_msgs::msg::MoveItErrorCodes::PLANNING_FAILED:
          RCLCPP_ERROR(LOGGER, "Error: PLANNING_FAILED");
          break;
        case moveit_msgs::msg::MoveItErrorCodes::INVALID_MOTION_PLAN:
          RCLCPP_ERROR(LOGGER, "Error: INVALID_MOTION_PLAN");
          break;
        case moveit_msgs::msg::MoveItErrorCodes::CONTROL_FAILED:
          RCLCPP_ERROR(LOGGER, "Error: CONTROL_FAILED");
          break;
        case moveit_msgs::msg::MoveItErrorCodes::TIMED_OUT:
          RCLCPP_ERROR(LOGGER, "Error: TIMED_OUT");
          break;
        default:
          RCLCPP_ERROR(LOGGER, "Error: Unknown error code %d", result.val);
      }
      
      // 如果是时间戳问题，建议使用Pilz
      RCLCPP_INFO(LOGGER, "If you see 'Time between points' error, consider:");
      RCLCPP_INFO(LOGGER, "1. Check if AddTimeOptimalParameterization adapter is loaded");
      RCLCPP_INFO(LOGGER, "2. Try using Pilz planner: ros2 launch mtc_tutorial pick_place_demo_pilz.launch.py");
    } else {
      RCLCPP_INFO(LOGGER, "Task execution completed successfully!");
    }
  } else {
    RCLCPP_INFO(LOGGER, "Execution is disabled. Task completed with planning and visualization only.");
    RCLCPP_INFO(LOGGER, "You can view the planned trajectory in RViz.");
    RCLCPP_INFO(LOGGER, "Set execute_enabled = true in doTask() to enable execution.");
  }

  // 保持节点运行一段时间以便观察结果
  std::this_thread::sleep_for(std::chrono::seconds(5));
}

mtc::Task MTCTaskNode::createTask()
{
  mtc::Task task;
  task.stages()->setName("uf850 pick and place task");
  task.loadRobotModel(node_);

  // UF850机器人配置
  const auto& arm_group_name = "uf850";
  const auto& hand_group_name = "uf850_gripper";
  const auto& hand_frame = "link_tcp";

  // Set task properties
  task.setProperty("group", arm_group_name);
  task.setProperty("eef", hand_group_name);
  task.setProperty("ik_frame", hand_frame);

  // 创建规划器
  auto pipeline_planner = std::make_shared<mtc::solvers::PipelinePlanner>(node_);
  pipeline_planner->setTimeout(3.0);  // 适中超时
  pipeline_planner->setMaxVelocityScalingFactor(0.3);  // 更稳健
  pipeline_planner->setMaxAccelerationScalingFactor(0.5);
  pipeline_planner->setPlannerId("RRTConnect");  // 明确指定规划器
  // 确保轨迹有正确的时间参数化
  pipeline_planner->setProperty("longest_valid_segment_fraction", 0.02);  // 增加分段长度以减少计算
  
  // 为OMPL设置额外的属性以确保时间参数化
  pipeline_planner->setProperty("goal_joint_tolerance", 1e-4);  // 收紧容忍度：从1e-3改为1e-4，提高精度
  pipeline_planner->setProperty("simplify_solutions", true);
  pipeline_planner->setProperty("minimum_waypoint_count", 2);
  
  // 添加OMPL特定的加速参数
  pipeline_planner->setProperty("range", 0.08);  // 略增采样跨度，提高连通性
  pipeline_planner->setProperty("max_planning_time", 2.5);  // 加快失败返回
  
  auto interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
  interpolation_planner->setMaxVelocityScalingFactor(0.5);
  interpolation_planner->setMaxAccelerationScalingFactor(0.6);

  // 慢速关节插值规划器（用于倒水相关动作）
  auto slow_interpolation_planner = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
  slow_interpolation_planner->setMaxVelocityScalingFactor(0.12);
  slow_interpolation_planner->setMaxAccelerationScalingFactor(0.2);

  auto cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
  cartesian_planner->setMaxVelocityScalingFactor(0.3);
  cartesian_planner->setMaxAccelerationScalingFactor(0.5);
  cartesian_planner->setStepSize(0.008);  // 更细的笛卡尔步长
  cartesian_planner->setJumpThreshold(0.0);  // 禁用跳跃检测以避免轨迹中断

  // 慢速笛卡尔规划器（用于拿着杯子移动与靠近倒水位）
  auto slow_cartesian_planner = std::make_shared<mtc::solvers::CartesianPath>();
  slow_cartesian_planner->setMaxVelocityScalingFactor(0.15);
  slow_cartesian_planner->setMaxAccelerationScalingFactor(0.25);
  slow_cartesian_planner->setStepSize(0.006);
  slow_cartesian_planner->setJumpThreshold(0.0);

  // ====================== 开始构建任务阶段 ======================
  
  // 当前状态 - 用于监控
  mtc::Stage* current_state_ptr = nullptr;
  {
    auto stage_state_current = std::make_unique<mtc::stages::CurrentState>("current");
    current_state_ptr = stage_state_current.get();
    task.add(std::move(stage_state_current));
  }

  // 打开夹爪
  {
    auto stage = std::make_unique<mtc::stages::MoveTo>("open hand", interpolation_planner);
    stage->setGroup(hand_group_name);
    stage->setGoal("open");
    task.add(std::move(stage));
  }

  // ====================== PICK部分 ======================
  
  // 连接到抓取位置
  {
    auto stage = std::make_unique<mtc::stages::Connect>(
      "move to pick",
      mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, pipeline_planner } });
    stage->setTimeout(15.0);
    stage->properties().configureInitFrom(mtc::Stage::PARENT);
    task.add(std::move(stage));
  }

  // 抓取容器
  mtc::Stage* attach_object_stage = nullptr;  // 用于放置阶段的引用
  {
    auto grasp = std::make_unique<mtc::SerialContainer>("pick object");
    task.properties().exposeTo(grasp->properties(), { "eef", "group", "ik_frame" });
    grasp->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

    // 接近物体
    {
      auto stage = std::make_unique<mtc::stages::MoveRelative>("approach object", cartesian_planner);
      stage->properties().set("marker_ns", "approach_object");
      stage->properties().set("link", hand_frame);
      stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      stage->setMinMaxDistance(0.05, 0.15);  // 侧向预抓取距离，拉开安全余量
      
      // 设置接近方向 - 沿TCP的Z轴向前
      geometry_msgs::msg::Vector3Stamped vec;
      vec.header.frame_id = hand_frame;
      vec.vector.z = 1.0;
      stage->setDirection(vec);
      grasp->insert(std::move(stage));
    }

    // 生成抓取姿态
    {
      auto stage = std::make_unique<mtc::stages::GenerateGraspPose>("generate grasp pose");
      stage->properties().configureInitFrom(mtc::Stage::PARENT);
      stage->properties().set("marker_ns", "grasp_pose");
      stage->setPreGraspPose("open");
      stage->setObject("object");
      stage->setAngleDelta(M_PI / 12.0);  // 更细的角度步进，提高命中率
      stage->setMonitoredStage(current_state_ptr);  // 监控当前状态

      // 定义抓取框架变换 - 侧向抓取尝试
      Eigen::Isometry3d grasp_frame_transform;
      Eigen::Quaterniond q = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitX()) *
                             Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()) *
                             Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitZ());
      grasp_frame_transform.linear() = q.matrix();
      grasp_frame_transform.translation().z() = 0.0001;  // 大幅减少TCP到物体中心的距离：从0.08改为0.02

      // 计算IK
      auto wrapper = std::make_unique<mtc::stages::ComputeIK>("grasp pose IK", std::move(stage));
      wrapper->setMaxIKSolutions(8);  // 增加IK解数量
      wrapper->setMinSolutionDistance(0.3);
      wrapper->setIKFrame(grasp_frame_transform, hand_frame);
      wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
      wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
      wrapper->setTimeout(8.0);  // 给IK更多时间
      grasp->insert(std::move(wrapper));
    }

    // 允许手和物体之间的碰撞
    {
      auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("allow collision (hand,object)");
      stage->allowCollisions("object",
                            task.getRobotModel()
                                ->getJointModelGroup(hand_group_name)
                                ->getLinkModelNamesWithCollisionGeometry(),
                            true);
      grasp->insert(std::move(stage));
    }

    // 关闭夹爪
    {
      // 在真正关爪前，向前微插入，确保杯体进入爪深处而非仅前端夹紧
      auto insert = std::make_unique<mtc::stages::MoveRelative>("pre-close insert", cartesian_planner);
      insert->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      insert->setIKFrame(hand_frame);
      insert->setMinMaxDistance(0.01, 0.03);  // 1-3cm 微插入
      insert->properties().set("marker_ns", "pre_close_insert");
      geometry_msgs::msg::Vector3Stamped vec_ins;
      vec_ins.header.frame_id = hand_frame;
      vec_ins.vector.z = 1.0;  // 按你的策略：横向后沿 Z 轴靠近
      insert->setDirection(vec_ins);
      grasp->insert(std::move(insert));

      // 按比例半闭合
      auto stage = std::make_unique<mtc::stages::MoveTo>("close hand partial", interpolation_planner);
      stage->setGroup(hand_group_name);
      std::map<std::string, double> partial_close;
      partial_close["drive_joint"] = std::clamp(gripper_close_full_ * gripper_close_ratio_, 0.0, gripper_close_full_);
      stage->setGoal(partial_close);
      grasp->insert(std::move(stage));
    }

    // 附加物体到手上
    {
      auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("attach object");
      stage->attachObject("object", hand_frame);
      attach_object_stage = stage.get();  // 保存引用供后续使用
      grasp->insert(std::move(stage));
    }

    // 抬起物体
    {
      auto stage = std::make_unique<mtc::stages::MoveRelative>("lift object", cartesian_planner);
      stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      stage->setMinMaxDistance(0.1, 0.15);  // 减少抬起高度
      stage->setIKFrame(hand_frame);
      stage->properties().set("marker_ns", "lift_object");
      
      // 设置向上的方向
      geometry_msgs::msg::Vector3Stamped vec;
      vec.header.frame_id = "link_base";  // 使用基座坐标系
      vec.vector.z = 1.0;
      stage->setDirection(vec);
      grasp->insert(std::move(stage));
    }
    
    task.add(std::move(grasp));
  }

  // ====================== 倒水姿势阶段 ======================
  
  // 倒水容器
  {
    auto pour = std::make_unique<mtc::SerialContainer>("pour water");
    task.properties().exposeTo(pour->properties(), { "eef", "group", "ik_frame" });
    pour->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

    // 移动到倒水位置
    {
      auto stage = std::make_unique<mtc::stages::MoveRelative>("move to pour position", slow_cartesian_planner);
      stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      stage->setMinMaxDistance(0.08, 0.15);  // 左移8-15cm，确保安全距离
      stage->setIKFrame(hand_frame);
      stage->properties().set("marker_ns", "move_to_pour");
      
      // 设置向左移动方向
      geometry_msgs::msg::Vector3Stamped vec;
      vec.header.frame_id = "link_base";
      vec.vector.y = -1.0;
      stage->setDirection(vec);
      pour->insert(std::move(stage));
    }

    // 执行倒水动作 - 通过joint6旋转（分步进行，更安全）
    {
      // 第一步：旋转45度
      auto stage1 = std::make_unique<mtc::stages::MoveTo>("pour water step 1", slow_interpolation_planner);
      stage1->setGroup(arm_group_name);
      
      std::map<std::string, double> pour_joint_values_1;
      pour_joint_values_1["joint6"] = M_PI / 4;  // 旋转45度
      
      stage1->setGoal(pour_joint_values_1);
      stage1->setTimeout(5.0);  // 2秒超时
      pour->insert(std::move(stage1));
    }

    {
      // 第二步：旋转到120度（更充分倒水）
      auto stage2 = std::make_unique<mtc::stages::MoveTo>("pour water step 2", slow_interpolation_planner);
      stage2->setGroup(arm_group_name);
      
      std::map<std::string, double> pour_joint_values_2;
      pour_joint_values_2["joint6"] = 2.0 * M_PI / 3.0;  // 约120度
      
      stage2->setGoal(pour_joint_values_2);
      stage2->setTimeout(5.0);  // 2秒超时
      pour->insert(std::move(stage2));
    }

    // 保持倒水姿态一段时间（模拟倒水过程）
    {
      auto stage = std::make_unique<mtc::stages::MoveTo>("hold pour position", slow_interpolation_planner);
      stage->setGroup(arm_group_name);
      
      // 保持当前倒水姿态
      std::map<std::string, double> hold_joint_values;
      hold_joint_values["joint6"] = 2.0 * M_PI / 3.0;  // 保持约120度
      
      stage->setGoal(hold_joint_values);
      stage->setTimeout(3.0);  // 保持3秒，模拟倒水时间
      pour->insert(std::move(stage));
    }

    // 恢复水平姿态（分步进行）
    {
      // 第一步：回到45度
      auto stage1 = std::make_unique<mtc::stages::MoveTo>("return to 45 degrees", slow_interpolation_planner);
      stage1->setGroup(arm_group_name);
      
      std::map<std::string, double> return_joint_values_1;
      return_joint_values_1["joint6"] = M_PI / 4;  // 回到45度
      
      stage1->setGoal(return_joint_values_1);
      stage1->setTimeout(2.0);  // 2秒超时
      pour->insert(std::move(stage1));
    }

    {
      // 第二步：回到水平（0度）
      auto stage2 = std::make_unique<mtc::stages::MoveTo>("return to horizontal", slow_interpolation_planner);
      stage2->setGroup(arm_group_name);
      
      // 将joint6恢复到0度（水平）
      std::map<std::string, double> horizontal_joint_values;
      horizontal_joint_values["joint6"] = 0.0;  // 水平姿态
      
      stage2->setGoal(horizontal_joint_values);
      stage2->setTimeout(2.0);  // 2秒超时
      pour->insert(std::move(stage2));
    }
    
    task.add(std::move(pour));
  }

  // ====================== PLACE部分 ======================
  
  // 连接到放置位置
  {
    auto stage = std::make_unique<mtc::stages::Connect>(
        "move to place",
        mtc::stages::Connect::GroupPlannerVector{ { arm_group_name, interpolation_planner } });
    stage->setTimeout(15.0);
    stage->properties().configureInitFrom(mtc::Stage::PARENT);
    task.add(std::move(stage));
  }

  // 放置容器
  {
    auto place = std::make_unique<mtc::SerialContainer>("place object");
    task.properties().exposeTo(place->properties(), { "eef", "group", "ik_frame" });
    place->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group", "ik_frame" });

    // 生成放置姿态
    {
      auto stage = std::make_unique<mtc::stages::GeneratePlacePose>("generate place pose");
      stage->properties().configureInitFrom(mtc::Stage::PARENT);
      stage->properties().set("marker_ns", "place_pose");
      stage->setObject("object");

      // 设置放置目标位置
      geometry_msgs::msg::PoseStamped target_pose_msg;
      target_pose_msg.header.frame_id = "link_base";  // 使用基座坐标系
      target_pose_msg.pose.position.x = 0.0;   
      target_pose_msg.pose.position.y = -0.45;   
      target_pose_msg.pose.position.z = 0.18;  // 桌面高度
      target_pose_msg.pose.orientation.w = 1.0;
      stage->setPose(target_pose_msg);
      stage->setMonitoredStage(attach_object_stage);  // 监控附加物体阶段

      // 计算IK
      auto wrapper = std::make_unique<mtc::stages::ComputeIK>("place pose IK", std::move(stage));
      wrapper->setMaxIKSolutions(3);  // 修复：从3.0改为3（整数）
      wrapper->setMinSolutionDistance(0.5);
      
      // 定义放置时的物体框架 - 让物体保持垂直
      Eigen::Isometry3d place_frame_transform;
      place_frame_transform.setIdentity();
      wrapper->setIKFrame(place_frame_transform, "object");
      
      wrapper->properties().configureInitFrom(mtc::Stage::PARENT, { "eef", "group" });
      wrapper->properties().configureInitFrom(mtc::Stage::INTERFACE, { "target_pose" });
      wrapper->setTimeout(5.0);
      place->insert(std::move(wrapper));
    }

    // 降低物体到放置位置
    {
      auto stage = std::make_unique<mtc::stages::MoveRelative>("lower object", cartesian_planner);
      stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      stage->setMinMaxDistance(0.03, 0.2);
      stage->setIKFrame(hand_frame);
      stage->properties().set("marker_ns", "lower_object");
      
      // 设置向下的方向
      geometry_msgs::msg::Vector3Stamped vec;
      vec.header.frame_id = "link_base";
      vec.vector.z = -1.0;
      stage->setDirection(vec);
      place->insert(std::move(stage));
    }

    // 打开夹爪
    {
      auto stage = std::make_unique<mtc::stages::MoveTo>("release object", interpolation_planner);
      stage->setGroup(hand_group_name);
      stage->setGoal("open");
      place->insert(std::move(stage));
    }

    // 禁止手和物体之间的碰撞
    {
      auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("forbid collision (hand,object)");
      stage->allowCollisions("object",
                            task.getRobotModel()
                                ->getJointModelGroup(hand_group_name)
                                ->getLinkModelNamesWithCollisionGeometry(),
                            false);
      place->insert(std::move(stage));
    }

    // 分离物体
    {
      auto stage = std::make_unique<mtc::stages::ModifyPlanningScene>("detach object");
      stage->detachObject("object", hand_frame);
      place->insert(std::move(stage));
    }

    // 后退
    {
      auto stage = std::make_unique<mtc::stages::MoveRelative>("retreat", cartesian_planner);
      stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
      stage->setMinMaxDistance(0.05, 0.1);
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

  // ====================== 返回初始位置 ======================
  {
    auto stage = std::make_unique<mtc::stages::MoveTo>("return home", pipeline_planner);
    stage->properties().configureInitFrom(mtc::Stage::PARENT, { "group" });
    stage->setGoal("home");  // UF850使用home位置
    stage->setTimeout(15.0);
    task.add(std::move(stage));
  }

  return task;
}

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);

  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(true);

  auto mtc_task_node = std::make_shared<MTCTaskNode>(options);
  rclcpp::executors::MultiThreadedExecutor executor;

  auto spin_thread = std::make_unique<std::thread>([&executor, &mtc_task_node]() {
    executor.add_node(mtc_task_node->getNodeBaseInterface());
    executor.spin();
    executor.remove_node(mtc_task_node->getNodeBaseInterface());
  });

  // 先等待一下让系统初始化
  std::this_thread::sleep_for(std::chrono::seconds(2));
  
  mtc_task_node->setupPlanningScene();
  
  // 等待场景更新
  std::this_thread::sleep_for(std::chrono::seconds(1));
  
  mtc_task_node->doTask();

  spin_thread->join();
  rclcpp::shutdown();
  return 0;
}