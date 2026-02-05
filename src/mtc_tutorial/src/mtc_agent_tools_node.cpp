#include <rclcpp/rclcpp.hpp>
#include <moveit/task_constructor/task.h>
#include <moveit/task_constructor/solvers.h>
#include <moveit/task_constructor/stages.h>
#include <moveit/planning_scene_interface/planning_scene_interface.h>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <tf2_eigen/tf2_eigen.hpp>
#include "mtc_tutorial/srv/run_task.hpp"

namespace mtc = moveit::task_constructor;

class MTCAgentToolsNode : public rclcpp::Node {
public:
  MTCAgentToolsNode() : Node("mtc_agent_tools_node") {
    service_ = this->create_service<mtc_tutorial::srv::RunTask>(
      "run_mtc_task",
      std::bind(&MTCAgentToolsNode::handleRunTask, this, std::placeholders::_1, std::placeholders::_2));

    // 速度/执行参数
    declare_parameter("default_speed_scale", 0.3);
    get_parameter("default_speed_scale", default_speed_);
  }

private:
  rclcpp::Service<mtc_tutorial::srv::RunTask>::SharedPtr service_;
  double default_speed_{0.3};

  mtc::Task buildPickTask(const std::string& object_id, double cup_diameter, double speed);
  mtc::Task buildCarryTask(const geometry_msgs::msg::PoseStamped& target_pose, double speed);
  mtc::Task buildPourTask(const std::vector<float>& angles_deg, const std::vector<float>& durations_s, double speed);
  mtc::Task buildPlaceTask(const geometry_msgs::msg::PoseStamped& target_pose, double speed);

  void handleRunTask(const std::shared_ptr<mtc_tutorial::srv::RunTask::Request> req,
                     std::shared_ptr<mtc_tutorial::srv::RunTask::Response> res) {
    try {
      double speed = req->speed_scale > 0.0 ? req->speed_scale : default_speed_;
      mtc::Task task;
      if (req->task_type == "PICK") task = buildPickTask(req->object_id, req->cup_diameter, speed);
      else if (req->task_type == "CARRY") task = buildCarryTask(req->target_pose, speed);
      else if (req->task_type == "POUR") task = buildPourTask(req->pour_angles_deg, req->pour_durations_s, speed);
      else if (req->task_type == "PLACE") task = buildPlaceTask(req->target_pose, speed);
      else {
        res->success = false; res->message = "Unknown task_type"; return;
      }

      try { task.init(); } catch (mtc::InitStageException& e) {
        res->success = false; res->message = std::string("Init failed: ") + e.what(); return;
      }

      if (!task.plan(2)) { res->success = false; res->message = "Planning failed"; return; }
      auto solution = *task.solutions().front();
      task.introspection().publishSolution(solution);
      auto result = task.execute(solution);
      res->success = (result.val == moveit_msgs::msg::MoveItErrorCodes::SUCCESS);
      res->message = res->success ? "OK" : ("Exec error code: " + std::to_string(result.val));
    } catch (const std::exception& e) {
      res->success = false; res->message = e.what();
    }
  }
};

// 下面给出非常简化的四个任务骨架：
static std::shared_ptr<mtc::solvers::PipelinePlanner> makePipelinePlanner(rclcpp::Node::SharedPtr node, double speed) {
  auto p = std::make_shared<mtc::solvers::PipelinePlanner>(node);
  p->setMaxVelocityScalingFactor(std::clamp(speed, 0.05, 0.8));
  p->setMaxAccelerationScalingFactor(std::clamp(speed*1.5, 0.1, 0.8));
  p->setTimeout(2.5);
  p->setPlannerId("RRTConnect");
  return p;
}
static std::shared_ptr<mtc::solvers::JointInterpolationPlanner> makeJointInterp(double speed){
  auto j = std::make_shared<mtc::solvers::JointInterpolationPlanner>();
  j->setMaxVelocityScalingFactor(std::clamp(speed, 0.05, 0.8));
  j->setMaxAccelerationScalingFactor(std::clamp(speed*1.5, 0.1, 0.8));
  return j;
}
static std::shared_ptr<mtc::solvers::CartesianPath> makeCartesian(double speed){
  auto c = std::make_shared<mtc::solvers::CartesianPath>();
  c->setMaxVelocityScalingFactor(std::clamp(speed, 0.05, 0.8));
  c->setMaxAccelerationScalingFactor(std::clamp(speed*1.5, 0.1, 0.8));
  c->setStepSize(0.008);
  c->setJumpThreshold(0.0);
  return c;
}

mtc::Task MTCAgentToolsNode::buildPickTask(const std::string& object_id, double cup_diameter, double speed){
  mtc::Task task; task.stages()->setName("pick_task"); task.loadRobotModel(shared_from_this());
  const std::string arm_group = "uf850";
  const std::string hand_group = "uf850_gripper";
  const std::string hand_frame = "link_tcp";
  task.setProperty("group", arm_group);
  task.setProperty("eef", hand_group);
  task.setProperty("ik_frame", hand_frame);
  auto pipe = makePipelinePlanner(shared_from_this(), speed);
  auto cart = makeCartesian(speed);
  auto joint = makeJointInterp(speed);

  // 基于杯径的闭合比（drive_joint close=0.85）：简单线性映射，口径 0.02~0.08 -> 关闭 0.2~0.7
  double close_full = 0.85;
  double ratio = 0.33;
  if (cup_diameter > 0.0){
    ratio = std::clamp((cup_diameter - 0.02) / (0.08 - 0.02) * (0.7 - 0.2) + 0.2, 0.15, 0.8);
  }

  // current
  task.add(std::make_unique<mtc::stages::CurrentState>("current"));
  // open
  {
    auto s = std::make_unique<mtc::stages::MoveTo>("open", joint);
    s->setGroup(hand_group); s->setGoal("open"); task.add(std::move(s));
  }
  // connect
  {
    auto s = std::make_unique<mtc::stages::Connect>("connect", mtc::stages::Connect::GroupPlannerVector{ {arm_group, pipe} });
    s->setTimeout(10.0); task.add(std::move(s));
  }
  // approach + partial close
  {
    auto serial = std::make_unique<mtc::SerialContainer>("grasp");
    // approach along +Z of tcp
    {
      auto s = std::make_unique<mtc::stages::MoveRelative>("approach", cart);
      s->properties().set("link", hand_frame);
      s->properties().configureInitFrom(mtc::Stage::PARENT, {"group"});
      s->setMinMaxDistance(0.02, 0.08);
      geometry_msgs::msg::Vector3Stamped v; v.header.frame_id=hand_frame; v.vector.z=1.0; s->setDirection(v);
      serial->insert(std::move(s));
    }
    // partial close
    {
      auto s = std::make_unique<mtc::stages::MoveTo>("partial_close", joint);
      s->setGroup(hand_group);
      std::map<std::string,double> goal; goal["drive_joint"] = close_full * ratio; s->setGoal(goal);
      serial->insert(std::move(s));
    }
    task.add(std::move(serial));
  }
  return task;
}

mtc::Task MTCAgentToolsNode::buildCarryTask(const geometry_msgs::msg::PoseStamped& target_pose, double speed){
  mtc::Task task; task.stages()->setName("carry_task"); task.loadRobotModel(shared_from_this());
  const std::string arm_group = "uf850"; const std::string hand_group = "uf850_gripper"; const std::string hand_frame = "link_tcp";
  task.setProperty("group", arm_group); task.setProperty("eef", hand_group); task.setProperty("ik_frame", hand_frame);
  auto pipe = makePipelinePlanner(shared_from_this(), speed);
  task.add(std::make_unique<mtc::stages::CurrentState>("current"));
  {
    auto gen = std::make_unique<mtc::stages::GeneratePose>("goto target");
    gen->setPose(target_pose);
    auto ik = std::make_unique<mtc::stages::ComputeIK>("ik", std::move(gen));
    ik->setIKFrame(hand_frame); ik->setMaxIKSolutions(3); ik->setTimeout(3.0);
    auto move = std::make_unique<mtc::stages::MoveTo>("move", pipe);
    move->setGroup(arm_group);
    task.add(std::move(move));
  }
  return task;
}

mtc::Task MTCAgentToolsNode::buildPourTask(const std::vector<float>& angles_deg, const std::vector<float>& durations_s, double speed){
  mtc::Task task; task.stages()->setName("pour_task"); task.loadRobotModel(shared_from_this());
  const std::string arm_group = "uf850"; const std::string hand_group = "uf850_gripper";
  auto joint_slow = makeJointInterp(std::min(0.2, speed));

  task.add(std::make_unique<mtc::stages::CurrentState>("current"));

  // 角速度剖面：按角度序列分段 MoveTo，配合 durations 作为超时近似控制节拍
  for (size_t i=0; i<angles_deg.size(); ++i){
    auto s = std::make_unique<mtc::stages::MoveTo>("pour_seg_"+std::to_string(i), joint_slow);
    s->setGroup(arm_group);
    std::map<std::string,double> j; j["joint6"] = angles_deg[i] * M_PI / 180.0; s->setGoal(j);
    s->setTimeout(i < durations_s.size() ? std::max(1.0f, durations_s[i]) : 2.0);
    task.add(std::move(s));
  }
  // 安全回撤：逐段回到水平 0 度
  {
    auto s = std::make_unique<mtc::stages::MoveTo>("pour_return", joint_slow);
    s->setGroup(arm_group);
    std::map<std::string,double> j; j["joint6"] = 0.0; s->setGoal(j);
    s->setTimeout(3.0);
    task.add(std::move(s));
  }
  return task;
}

mtc::Task MTCAgentToolsNode::buildPlaceTask(const geometry_msgs::msg::PoseStamped& target_pose, double speed){
  mtc::Task task; task.stages()->setName("place_task"); task.loadRobotModel(shared_from_this());
  const std::string arm_group = "uf850"; const std::string hand_group = "uf850_gripper"; const std::string hand_frame = "link_tcp";
  task.setProperty("group", arm_group); task.setProperty("eef", hand_group); task.setProperty("ik_frame", hand_frame);
  auto pipe = makePipelinePlanner(shared_from_this(), speed);
  auto joint = makeJointInterp(speed);
  task.add(std::make_unique<mtc::stages::CurrentState>("current"));
  // move to target
  {
    auto gen = std::make_unique<mtc::stages::GeneratePose>("place_pose");
    gen->setPose(target_pose);
    auto ik = std::make_unique<mtc::stages::ComputeIK>("place_ik", std::move(gen));
    ik->setIKFrame(hand_frame); ik->setMaxIKSolutions(3); ik->setTimeout(3.0);
    auto move = std::make_unique<mtc::stages::MoveTo>("move_to_place", pipe);
    move->setGroup(arm_group);
    task.add(std::move(move));
  }
  // open
  {
    auto s = std::make_unique<mtc::stages::MoveTo>("open", joint);
    s->setGroup(hand_group); s->setGoal("open"); task.add(std::move(s));
  }
  return task;
}

int main(int argc, char** argv){
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MTCAgentToolsNode>());
  rclcpp::shutdown();
  return 0;
} 