#!/usr/bin/env python3
import sys
import os
from typing import Any, Dict, Optional, List, Union
from pathlib import Path

# 确保可以导入同目录下的 pour_tool.py
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.append(str(_THIS_DIR))

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

try:
    # rclpy 0.10+ 提供 AsyncParametersClient
    from rclpy.parameter_client import AsyncParametersClient  # type: ignore
except Exception:
    AsyncParametersClient = None  # type: ignore

# =============== 模块级环境初始化 ===============
def _setup_ros_environment():
    """一次性设置ROS环境，避免重复计算"""
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    install_path = os.path.join(workspace_root, "install")
    
    if os.path.exists(install_path):
        # 设置Python路径
        python_path = os.path.join(install_path, "mtc_interface", "local", "lib", "python3.10", "dist-packages")
        if os.path.exists(python_path) and python_path not in sys.path:
            sys.path.insert(0, python_path)
        
        # 设置ROS环境变量
        if "AMENT_PREFIX_PATH" not in os.environ:
            os.environ["AMENT_PREFIX_PATH"] = install_path
        elif install_path not in os.environ["AMENT_PREFIX_PATH"]:
            os.environ["AMENT_PREFIX_PATH"] = install_path + ":" + os.environ["AMENT_PREFIX_PATH"]
    
    return install_path

# 模块加载时执行一次环境设置
_ROS_INSTALL_PATH = _setup_ros_environment()

# 生成唯一节点名，避免多个同名节点导致rosout重复注册告警
def _unique_node_name(base: str) -> str:
    try:
        import os, time
        return f"{base}_{os.getpid()}_{int(time.time()*1000)%1000000}"
    except Exception:
        return f"{base}_uniq"

# =============== 标准化错误处理 ===============
def _create_error_result(task_name: str, error_msg: str, params: Dict[str, Any] = None, 
                        status: str = "error") -> Dict[str, Any]:
    """创建标准化的错误返回结果"""
    return {
        "ok": False,
        "success": False,
        "status": status,
        "error": error_msg,
        "params": params or {},
        "task_name": task_name,
        "duration_sec": 0.0
    }

def _create_success_result(task_name: str, duration_sec: float = 0.0, 
                          params: Dict[str, Any] = None, **extra_fields) -> Dict[str, Any]:
    """创建标准化的成功返回结果"""
    result = {
        "ok": True,
        "success": True,
        "status": "succeeded",
        "error": "",
        "params": params or {},
        "task_name": task_name,
        "duration_sec": duration_sec
    }
    result.update(extra_fields)
    return result


def _ensure_rclpy_inited() -> bool:
    created = False    
    if not rclpy.ok():
        rclpy.init()
        created = True
    return created


def _shutdown_rclpy_if(created: bool) -> None:
    if created and rclpy.ok():
        rclpy.shutdown()


def _set_params(remote_node_name: str, params: Dict[str, Any], timeout_sec: float = 5.0) -> bool:
    # 优先使用 AsyncParametersClient
    if AsyncParametersClient is not None:
        created = _ensure_rclpy_inited()
        node = rclpy.create_node(_unique_node_name('mtc_mcp_param_setter'))
        try:
            client = AsyncParametersClient(node, remote_node_name)
            if not client.wait_for_service(timeout_sec=timeout_sec):
                node.get_logger().error(f"Param service not available for {remote_node_name}")
                return False
            param_list = []
            for name, value in params.items():
                param_list.append(Parameter(name=name, value=value))
            fut = client.set_parameters(param_list)
            rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout_sec)
            if not fut.done():
                node.get_logger().error("set_parameters timeout")
                return False
            results = fut.result()
            ok = all(r.successful for r in results)
            if not ok:
                for r in results:
                    if not r.successful:
                        node.get_logger().error(f"set_parameter failed: {r.reason}")
            return ok
        finally:
            node.destroy_node()
            _shutdown_rclpy_if(created)

    # 回退：直接调用 /set_parameters 服务
    from rcl_interfaces.srv import SetParameters
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('mtc_mcp_param_setter_srv'))
    try:
        service_name = f"{remote_node_name}/set_parameters"
        client = node.create_client(SetParameters, service_name)
        if not client.wait_for_service(timeout_sec=timeout_sec):
            node.get_logger().error(f"Service not available: {service_name}")
            return False
        req = SetParameters.Request()
        req.parameters = [Parameter(name=name, value=value).to_parameter_msg() for name, value in params.items()]
        fut = client.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout_sec)
        if not fut.done():
            node.get_logger().error("set_parameters (srv) timeout")
            return False
        res = fut.result()
        ok = all(r.successful for r in res.results)
        if not ok:
            for r in res.results:
                if not r.successful:
                    node.get_logger().error("set_parameter (srv) failed")
        return ok
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


# =============== 对外工具：执行倒水 ===============

# 倾倒任务默认参数
POUR_DEFAULTS: Dict[str, Any] = dict(
    tilt_start_deg=45.0,
    tilt_end_deg=120.0,
    tilt_speed_deg_s=25.0,
    pour_hold_sec=2.0,
    lift_height=0.12,
    approach_min=0.05,
    approach_max=0.15,
    plan_only=False,
    target_id="",
    # 新增：直接支持杯子位姿参数
    cup_x=None,
    cup_y=None,
    cup_z=None,
    cup_qx=None,
    cup_qy=None,
    cup_qz=None,
    cup_qw=None,
    set_cup_pose_first=True,  # 是否在执行前先设置杯子位姿
)

def _validate_pour_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """验证倾倒参数"""
    p = {**POUR_DEFAULTS, **params}
    if p["approach_min"] <= 0 or p["approach_max"] <= 0:
        raise ValueError("approach_min/max must be > 0")
    if p["approach_min"] >= p["approach_max"]:
        raise ValueError("approach_min must be < approach_max")
    if p["tilt_speed_deg_s"] <= 0:
        raise ValueError("tilt_speed_deg_s must be > 0")
    if p["pour_hold_sec"] < 0:
        raise ValueError("pour_hold_sec must be >= 0")
    for k in ("tilt_start_deg", "tilt_end_deg"):
        p[k] = max(min(float(p[k]), 180.0), -180.0)
    return p

def execute_pour(params: Dict[str, Any], action_name: str = 'execute_pour', timeout_sec: float = 180.0,
                  cancel_after: Optional[float] = None) -> Dict[str, Any]:
    """执行一次倒水动作。
    params 字段与 POUR_DEFAULTS 一致，可额外传递 target_id、plan_only 等。
    新增支持 cup_x/y/z, cup_qx/qy/qz/qw 直接设置杯子位姿。
    返回字典包含 ok/status/success/error/duration_sec/params。
    """
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('pour_client'))
    
    try:
        # 环境变量已在模块级别设置，无需重复设置
        
        # 导入所需的消息类型
        from rclpy.action import ActionClient
        import mtc_interface.action
        import time
        
        # 验证参数
        p = _validate_pour_params(params)
        
        # 重构：检查杯子对象是否存在于规划场景中
        object_check = check_object_exists(object_id="object_1", timeout_sec=3.0)
        if not object_check["ok"] or not object_check["object_exists"]:
            node.get_logger().error("Cup object 'object_1' not found in planning scene!")
            return _create_error_result("倾倒任务", 
                                       "Cup object not found in planning scene. Please run setup_planning_scene first.",
                                       p, "missing_object")
        
        node.get_logger().info("Cup object found in planning scene, proceeding with pour task")
        
        # 可选功能：如果提供了杯子位姿参数，先更新杯子位姿（而非通过参数设置）
        cup_pose_updated = False
        if p.get('update_cup_pose_first', False):
            cup_x = p.get('cup_x')
            cup_y = p.get('cup_y') 
            cup_z = p.get('cup_z')
            cup_qx = p.get('cup_qx')
            cup_qy = p.get('cup_qy')
            cup_qz = p.get('cup_qz')
            cup_qw = p.get('cup_qw')
            
            if cup_x is not None and cup_y is not None and cup_z is not None:
                node.get_logger().info(f"Updating cup pose: ({cup_x}, {cup_y}, {cup_z})")
                
                update_result = update_cup_pose(
                    cup_x=cup_x, cup_y=cup_y, cup_z=cup_z,
                    cup_qx=cup_qx, cup_qy=cup_qy, cup_qz=cup_qz, cup_qw=cup_qw,
                    timeout_sec=3.0
                )
                
                if update_result["ok"]:
                    node.get_logger().info("Cup pose updated successfully")
                    cup_pose_updated = True
                else:
                    node.get_logger().warn(f"Failed to update cup pose: {update_result.get('error', 'Unknown error')}")
                    # 继续执行，使用现有位姿
                
                # 等待一下确保位姿更新生效
                time.sleep(0.3)
        
        # 创建 Action 客户端
        action_client = ActionClient(node, mtc_interface.action.ExecutePour, action_name)
        
        # 构建 Goal
        goal = mtc_interface.action.ExecutePour.Goal()
        goal.target_id = p.get('target_id', '')
        goal.tilt_start_deg = float(p['tilt_start_deg'])
        goal.tilt_end_deg = float(p['tilt_end_deg'])
        goal.tilt_speed_deg_s = float(p['tilt_speed_deg_s'])
        goal.pour_hold_sec = float(p['pour_hold_sec'])
        goal.lift_height = float(p['lift_height'])
        goal.approach_min = float(p['approach_min'])
        goal.approach_max = float(p['approach_max'])
        goal.plan_only = bool(p['plan_only'])
        
        node.get_logger().info(
            f"Send goal: tilt {goal.tilt_start_deg}->{goal.tilt_end_deg} deg @ {goal.tilt_speed_deg_s} deg/s, "
            f"hold {goal.pour_hold_sec}s, lift {goal.lift_height} m, "
            f"approach[{goal.approach_min}, {goal.approach_max}], plan_only={goal.plan_only}, "
            f"cup_pose_updated={cup_pose_updated}")
        
        # 等待服务器
        if not action_client.wait_for_server(timeout_sec=5.0):
            return {"ok": False, "status": "no_server", "msg": f"Action server {action_name} not available"}
        
        # 发送目标
        def feedback_callback(msg):
            fb = msg.feedback
            node.get_logger().info(f"[{fb.stage}] progress={fb.progress:.2f}, tilt={fb.current_tilt_deg:.1f}")
        
        send_future = action_client.send_goal_async(goal, feedback_callback=feedback_callback)
        rclpy.spin_until_future_complete(node, send_future, timeout_sec=5.0)
        
        gh = send_future.result()
        if gh is None or not gh.accepted:
            return {"ok": False, "status": "rejected", "msg": "Goal rejected by server", "params": p}
        
        node.get_logger().info('Goal accepted')
        start = time.time()
        
        # 可选的定时取消
        if cancel_after is not None and cancel_after > 0:
            import threading
            def _schedule_cancel():
                time.sleep(cancel_after)
                node.get_logger().warn(f"Cancel after {cancel_after}s…")
                gh.cancel_goal_async()
            threading.Thread(target=_schedule_cancel, daemon=True).start()
        
        # 等待结果
        res_future = gh.get_result_async()
        while not res_future.done():
            if timeout_sec and time.time() - start > timeout_sec:
                node.get_logger().error(f"Timeout {timeout_sec}s, cancel goal")
                gh.cancel_goal_async()
                break
            rclpy.spin_once(node, timeout_sec=0.2)
        
        if not res_future.done():
            return {"ok": False, "status": "timeout", "msg": f"Timeout {timeout_sec}s", "params": p}
        
        # 处理结果
        result_msg = res_future.result()
        res = result_msg.result
        status = result_msg.status  # 4 SUCCEEDED, 5 CANCELED, 6 ABORTED
        
        return {
            "ok": bool(res.success) and status == 4,
            "status": {4: "succeeded", 5: "canceled", 6: "aborted"}.get(status, "unknown"),
            "success": bool(res.success),
            "duration_sec": float(res.duration_sec),
            "error": res.error_msg,
            "params": p,
            "cup_pose_updated": cup_pose_updated,
            "object_check": object_check,
        }
        
    except Exception as e:
        return _create_error_result("倾倒任务", f"Pour execution failed: {str(e)}")
    
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


# =============== 对外工具：场景构建和管理 ===============

def setup_planning_scene(
                         detection_result: Optional[Any] = None,
                         *,
                         only_cup: bool = True,
                         id_prefix: str = "object",
                         timeout_sec: float = 10.0,
                         # 向后兼容：如果未提供 detection_result，则仍可使用旧的 detected_objects 输入
                         detected_objects: Optional[Union[Any, List[Any]]] = None,
                         # 以下旧参数将被忽略（仅在未提供检测结果且需要回退时才会用到）
                         include_cup: bool = True,
                         cup_x: float = 0.0, cup_y: float = -0.4, cup_z: float = 0.13,
                         cup_qx: Optional[float] = None, cup_qy: Optional[float] = None,
                         cup_qz: Optional[float] = None, cup_qw: Optional[float] = 1.0,
                         cup_height: float = 0.1, cup_radius: float = 0.02,
                         # 新增：bowl 生成控制与默认模型尺寸
                         include_bowl: bool = True,
                         bowl_id_prefix: str = "bowl",
                         bowl_height: float = 0.07,
                         bowl_radius: float = 0.04,
                         bowl_default_z: float = 0.125,
                         # 新增：bottle 生成控制与默认模型尺寸
                         include_bottle: bool = True,
                         bottle_id_prefix: str = "bottle",
                         bottle_height: float = 0.15,  # bottle比cup高一些
                        bottle_radius: float = 0.025,  # bottle稍微细一点
                        bottle_default_z: float = 0.13,
                        # 可选：添加"虚拟墙"禁入区（通过一个BOX碰撞体实现）
                        add_no_go_wall: bool = False,  # 默认禁用虚拟墙
                         wall_x_min: float = 0.40, wall_x_max: float = 0.42,
                         wall_y_min: float = -0.90, wall_y_max: float = 0.20,
                         wall_z_min: float = 0.00, wall_z_max: float = 0.60,
                         wall_alpha: float = 0.02,
                         ) -> Dict[str, Any]:
    """设置规划场景：基于检测结果创建多个物体对象。
    
    优先使用 detection_result（来自 object_single_shot_detection.py 发布的 DetectionResult）。
    支持创建的物体类型：
      - cup: 杯子（默认尺寸：height=0.1m, radius=0.02m）
      - bowl: 碗（默认尺寸：height=0.07m, radius=0.04m）
      - bottle: 瓶子（默认尺寸：height=0.15m, radius=0.025m）
    
    生成的物体：
      - ID：统一命名为 id_prefix_1, id_prefix_2, id_prefix_3 ...（例如：object_1, object_2）
      - 位姿：position(x,y,z) 来自检测消息；orientation 统一为 (0,0,0,1)
      - 尺寸：使用对应物体类型的默认尺寸，满足 MoveIt 需求
    
    Args:
        detection_result: DetectionResult 消息对象（推荐）
        only_cup: 是否仅根据 class_name=='cup' 生成对象（False时支持cup/bowl/bottle）
        id_prefix: 生成对象ID前缀
        timeout_sec: 等待规划场景服务超时
        detected_objects: 向后兼容的旧输入（DetectionResult/DetectedObject列表/字典列表）
        include_cup/cup_x/...: 仅在没有检测输入时用于回退生成一个默认杯子
        include_bowl/bowl_*: bowl物体的生成控制和尺寸参数
        include_bottle/bottle_*: bottle物体的生成控制和尺寸参数
    
    Returns:
        包含场景设置结果的字典
    """
    created = _ensure_rclpy_inited()
    import rclpy
    node = rclpy.create_node(_unique_node_name('planning_scene_setup'))
    
    try:
        # 导入必要的消息类型
        from moveit_msgs.msg import CollisionObject, PlanningScene, ObjectColor
        from moveit_msgs.srv import ApplyPlanningScene
        from shape_msgs.msg import SolidPrimitive
        from geometry_msgs.msg import Pose
        import time
        
        # 使用ApplyPlanningScene服务，更好地模拟原始的PlanningSceneInterface
        apply_scene_client = node.create_client(ApplyPlanningScene, '/apply_planning_scene')
        
        # 等待服务可用
        if not apply_scene_client.wait_for_service(timeout_sec=timeout_sec):
            node.get_logger().warn("ApplyPlanningScene service not available, falling back to topic publishing")
            # 备用方案：使用topic发布
            collision_object_pub = node.create_publisher(CollisionObject, '/collision_object', 10)
            time.sleep(1.0)
            use_service = False
        else:
            use_service = True
        
        collision_objects: List[CollisionObject] = []
        added_object_specs: List[Dict[str, Any]] = []  # 统一记录写入 place.origin
        added_cup_specs: List[Dict[str, Any]] = []     # 仅cup的位姿（向后兼容返回）
        cup_created_specs: List[Dict[str, Any]] = []   # 仅cup的ID
        bowl_created_specs: List[Dict[str, Any]] = []
        bottle_created_specs: List[Dict[str, Any]] = []  # bottle的ID
        
        # 1. 添加台面碰撞对象
        table_surface = CollisionObject()
        table_surface.header.stamp = node.get_clock().now().to_msg()
        table_surface.header.frame_id = "link_base"
        table_surface.id = "table_surface"
        table_surface.primitives.append(SolidPrimitive())
        table_surface.primitives[0].type = SolidPrimitive.BOX
        table_surface.primitives[0].dimensions = [1.0, 1.5, 0.01]
        table_pose = Pose()
        table_pose.position.x = -0.01
        table_pose.position.y = -0.25
        table_pose.position.z = -0.01
        table_pose.orientation.w = 1.0
        table_surface.primitive_poses.append(table_pose)
        table_surface.operation = CollisionObject.ADD
        collision_objects.append(table_surface)
        
        # 2. 可选：添加"虚拟墙"禁入区 - 通过BOX障碍限制规划范围（如相机/工作区）
        if add_no_go_wall:
            try:
                no_go = CollisionObject()
                no_go.header.stamp = node.get_clock().now().to_msg()
                no_go.header.frame_id = "link_base"
                no_go.id = "no_go_wall"

                # 以 [min,max] 边界定义一个长方体
                dx = float(abs(wall_x_max - wall_x_min))
                dy = float(abs(wall_y_max - wall_y_min))
                dz = float(abs(wall_z_max - wall_z_min))

                no_go.primitives.append(SolidPrimitive())
                no_go.primitives[0].type = SolidPrimitive.BOX
                no_go.primitives[0].dimensions = [dx, dy, dz]

                wall_pose = Pose()
                wall_pose.position.x = float((wall_x_max + wall_x_min) * 0.5)
                wall_pose.position.y = float((wall_y_max + wall_y_min) * 0.5)
                wall_pose.position.z = float((wall_z_max + wall_z_min) * 0.5)
                wall_pose.orientation.w = 1.0
                no_go.primitive_poses.append(wall_pose)
                no_go.operation = CollisionObject.ADD

                collision_objects.append(no_go)
                node.get_logger().info(
                    f"Added no-go wall at center=({wall_pose.position.x:.3f},{wall_pose.position.y:.3f},{wall_pose.position.z:.3f}) size=({dx:.3f},{dy:.3f},{dz:.3f})")
            except Exception as e:
                node.get_logger().warn(f"Failed to add no-go wall: {str(e)}")
        
        # 3. 基于检测结果创建物体对象（仅生成数量、ID和位置，姿态固定，尺寸使用默认）
        def _specs_from_detection_result(msg: Any) -> List[Dict[str, Any]]:
            specs: List[Dict[str, Any]] = []
            if msg is None:
                return specs
            try:
                # DetectionResult 接口：objects 列表；position_base(米)优先，否则 position_camera(米)
                objs = list(getattr(msg, 'objects', []))
                idx = 0
                for o in objs:
                    cls = getattr(o, 'class_name', '')
                    if only_cup and cls != 'cup':
                        continue
                    # 位置来源：优先基座坐标（米），否则相机坐标（米）
                    use_base = bool(getattr(o, 'transform_valid', False)) and bool(getattr(msg, 'transform_available', True))
                    pos = getattr(o, 'position_base', None) if use_base else getattr(o, 'position_camera', None)
                    if pos is None:
                        continue
                    idx += 1
                    obj_id = f"{id_prefix}_{idx}"  # 统一命名: object_1, object_2, ...
                    
                    # 提取姿态信息（如果有的话）
                    orientation_valid = bool(getattr(o, 'orientation_valid', False))
                    if orientation_valid:
                        ori = getattr(o, 'orientation_base', None)
                        qx = float(getattr(ori, 'x', 0.0)) if ori else 0.0
                        qy = float(getattr(ori, 'y', 0.0)) if ori else 0.0
                        qz = float(getattr(ori, 'z', 0.0)) if ori else 0.0
                        qw = float(getattr(ori, 'w', 1.0)) if ori else 1.0
                    else:
                        qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
                    
                    # 提取真实尺寸信息（如果有的话）
                    geometry_fitted = bool(getattr(o, 'geometry_fitted', False))
                    fitted_height = float(getattr(o, 'fitted_height', 0.0)) if geometry_fitted else None
                    fitted_radius = float(getattr(o, 'fitted_radius', 0.0)) if geometry_fitted else None
                    
                    specs.append({
                        "id": obj_id,
                        "class_name": cls,  # 添加类别信息
                        "x": float(getattr(pos, 'x', 0.0)),
                        "y": float(getattr(pos, 'y', 0.0)),
                        "z": float(getattr(pos, 'z', 0.0)),
                        # 新增：姿态信息
                        "qx": qx,
                        "qy": qy,
                        "qz": qz,
                        "qw": qw,
                        "orientation_valid": orientation_valid,
                        # 新增：真实尺寸
                        "fitted_height": fitted_height,
                        "fitted_radius": fitted_radius,
                        "geometry_fitted": geometry_fitted,
                    })
            except Exception:
                pass
            return specs
        
        # 通用：按给定类别提取规格（用于 bowl 等非 cup 类别）
        def _class_specs_from_detection_result(msg: Any, want_class: str, class_id_prefix: str) -> List[Dict[str, Any]]:
            specs: List[Dict[str, Any]] = []
            if msg is None:
                return specs
            try:
                objs = list(getattr(msg, 'objects', []))
                idx = 0
                for o in objs:
                    cls = getattr(o, 'class_name', '')
                    if cls != want_class:
                        continue
                    use_base = bool(getattr(o, 'transform_valid', False)) and bool(getattr(msg, 'transform_available', True))
                    pos = getattr(o, 'position_base', None) if use_base else getattr(o, 'position_camera', None)
                    if pos is None:
                        continue
                    idx += 1
                    obj_id = f"{class_id_prefix}_{idx}"  # 统一命名
                    specs.append({
                        "id": obj_id,
                        "x": float(getattr(pos, 'x', 0.0)),
                        "y": float(getattr(pos, 'y', 0.0)),
                        "z": float(getattr(pos, 'z', 0.0)),
                    })
            except Exception:
                pass
            return specs
        
        def _specs_from_legacy(det_objs: Any) -> List[Dict[str, Any]]:
            # 复用旧逻辑的解析（米单位），仅保留位置与ID
            specs_full: List[Dict[str, Any]] = []
            if not det_objs:
                return specs_full
            try:
                # 尝试导入消息类型以做类型判断
                from mtc_interface.msg import DetectedObject as MsgDetectedObject  # type: ignore
                from mtc_interface.msg import DetectionResult as MsgDetectionResult  # type: ignore
            except Exception:
                MsgDetectedObject = None  # type: ignore
                MsgDetectionResult = None  # type: ignore
            
            objs: List[Any] = []
            if 'MsgDetectionResult' in locals() and MsgDetectionResult and hasattr(det_objs, 'objects'):
                objs = list(det_objs.objects)
            elif isinstance(det_objs, list):
                objs = det_objs
            else:
                objs = [det_objs]
            
            idx = 0
            for o in objs:
                try:
                    if 'MsgDetectedObject' in locals() and MsgDetectedObject and (hasattr(o, 'position_base') or hasattr(o, 'position_camera')):
                        cls = getattr(o, 'class_name', '')
                        if only_cup and cls != 'cup':
                            continue
                        use_base = bool(getattr(o, 'transform_valid', False))
                        pos = getattr(o, 'position_base', None) if use_base else getattr(o, 'position_camera', None)
                        if pos is None:
                            continue
                        idx += 1
                        obj_id = f"{id_prefix}_{idx}"  # 统一命名
                        specs_full.append({
                            "id": obj_id,
                            "x": float(getattr(pos, 'x', 0.0)),
                            "y": float(getattr(pos, 'y', 0.0)),
                            "z": float(getattr(pos, 'z', 0.0)),
                        })
                    elif isinstance(o, dict):
                        cls = o.get('class_name', '')
                        if only_cup and cls != 'cup':
                            continue
                        pos_dict = o.get('position_base') or o.get('position_camera') or o.get('position') or {}
                        idx += 1
                        obj_id = f"{id_prefix}_{idx}"  # 统一命名
                        specs_full.append({
                            "id": obj_id,
                            "x": float(pos_dict.get('x', 0.0)),
                            "y": float(pos_dict.get('y', 0.0)),
                            "z": float(pos_dict.get('z', 0.0)),
                        })
                    else:
                        continue
                except Exception:
                    continue
            return specs_full
        
        cup_specs: List[Dict[str, Any]] = []
        bowl_specs: List[Dict[str, Any]] = []
        bottle_specs: List[Dict[str, Any]] = []
        
        if detection_result is not None:
            # 从检测结果中提取所有物体，然后按类型分类
            all_specs = _specs_from_detection_result(detection_result)
            
            # 按类型分类物体
            for spec in all_specs:
                class_name = spec.get("class_name", "")
                if class_name == "cup":
                    cup_specs.append(spec)
                elif class_name == "bowl" and include_bowl:
                    # 为bowl重新分配ID
                    bowl_idx = len(bowl_specs) + 1
                    bowl_id = f"{bowl_id_prefix}_{bowl_idx}"  # 统一命名
                    spec["id"] = bowl_id
                    bowl_specs.append(spec)
                elif class_name == "bottle" and include_bottle:
                    # 为bottle重新分配ID  
                    bottle_idx = len(bottle_specs) + 1
                    bottle_id = f"{bottle_id_prefix}_{bottle_idx}"  # 统一命名
                    spec["id"] = bottle_id
                    bottle_specs.append(spec)
                    
        elif detected_objects is not None:
            cup_specs = _specs_from_legacy(detected_objects)
            # 旧输入无法区分类别，保持仅杯子
        
        if not cup_specs and include_cup:
            # 回退：添加一个默认杯子
            cup_specs = [{
                "id": f"{id_prefix}_1",  # 统一命名
                "class_name": "cup",
                "x": cup_x, "y": cup_y, "z": cup_z,
            }]
        # bowl 和 bottle 无默认回退，依赖检测
        
        # 生成杯子碰撞对象（使用拟合的真实尺寸和姿态）
        for spec in cup_specs:
            cup_object = CollisionObject()
            cup_object.header.stamp = node.get_clock().now().to_msg()
            cup_object.header.frame_id = "link_base"
            cup_object.id = spec["id"]
            
            cup_object.primitives.append(SolidPrimitive())
            cup_object.primitives[0].type = SolidPrimitive.CYLINDER
            
            # 使用检测到的真实尺寸，如果没有则使用默认值
            actual_height = spec.get("fitted_height") or float(cup_height)
            actual_radius = spec.get("fitted_radius") or float(cup_radius)
            cup_object.primitives[0].dimensions = [actual_height, actual_radius]  # [height, radius]
            
            cup_pose = Pose()
            cup_pose.position.x = float(spec.get("x", 0.0)) 
            cup_pose.position.y = float(spec.get("y", 0.0)) 
            cup_pose.position.z = float(spec.get("z", 0.0)) 
            
            # 使用检测到的真实姿态（如果有的话）
            if spec.get("orientation_valid", False):
                cup_pose.orientation.x = float(spec.get("qx", 0.0))
                cup_pose.orientation.y = float(spec.get("qy", 0.0))
                cup_pose.orientation.z = float(spec.get("qz", 0.0))
                cup_pose.orientation.w = float(spec.get("qw", 1.0))
            else:
                cup_pose.orientation.w = 1.0  # 使用默认姿态(0,0,0,1)
            
            cup_object.primitive_poses.append(cup_pose)
            cup_object.operation = CollisionObject.ADD
            collision_objects.append(cup_object)
            
            # 记录使用的几何信息
            if spec.get("geometry_fitted", False):
                node.get_logger().info(
                    f"Using fitted geometry for {spec['id']}: "
                    f"h={actual_height:.3f}m, r={actual_radius:.3f}m, "
                    f"q=({cup_pose.orientation.x:.3f},{cup_pose.orientation.y:.3f},"
                    f"{cup_pose.orientation.z:.3f},{cup_pose.orientation.w:.3f})"
                )
            
            added_object_specs.append({
                "id": spec["id"],
                "position": {"x": cup_pose.position.x, "y": cup_pose.position.y, "z": cup_pose.position.z},
            })
            added_cup_specs.append({
                "id": spec["id"],
                "position": {"x": cup_pose.position.x, "y": cup_pose.position.y, "z": cup_pose.position.z},
            })
            cup_created_specs.append({"id": spec["id"]})
        
        # 生成 bowl 碰撞对象（更矮更大；Z 使用默认高度）
        if include_bowl and bowl_specs:
            for spec in bowl_specs:
                bowl_object = CollisionObject()
                bowl_object.header.stamp = node.get_clock().now().to_msg()
                bowl_object.header.frame_id = "link_base"
                bowl_object.id = spec["id"]

                bowl_object.primitives.append(SolidPrimitive())
                bowl_object.primitives[0].type = SolidPrimitive.CYLINDER
                bowl_object.primitives[0].dimensions = [float(bowl_height), float(bowl_radius)]

                bowl_pose = Pose()
                bowl_pose.position.x = float(spec.get("x", 0.0))
                bowl_pose.position.y = float(spec.get("y", 0.0))
                bowl_pose.position.z = float(bowl_default_z)
                bowl_pose.orientation.w = 1.0

                bowl_object.primitive_poses.append(bowl_pose)
                bowl_object.operation = CollisionObject.ADD
                collision_objects.append(bowl_object)
                added_object_specs.append({
                    "id": spec["id"],
                    "position": {"x": bowl_pose.position.x, "y": bowl_pose.position.y, "z": bowl_pose.position.z},
                })
                bowl_created_specs.append({"id": spec["id"]})
        
        # 生成 bottle 碰撞对象（更高更细；Z 使用默认高度）
        if include_bottle and bottle_specs:
            for spec in bottle_specs:
                bottle_object = CollisionObject()
                bottle_object.header.stamp = node.get_clock().now().to_msg()
                bottle_object.header.frame_id = "link_base"
                bottle_object.id = spec["id"]

                bottle_object.primitives.append(SolidPrimitive())
                bottle_object.primitives[0].type = SolidPrimitive.CYLINDER
                bottle_object.primitives[0].dimensions = [float(bottle_height), float(bottle_radius)]

                bottle_pose = Pose()
                bottle_pose.position.x = float(spec.get("x", 0.0))
                bottle_pose.position.y = float(spec.get("y", 0.0))
                bottle_pose.position.z = float(bottle_default_z)
                bottle_pose.orientation.w = 1.0

                bottle_object.primitive_poses.append(bottle_pose)
                bottle_object.operation = CollisionObject.ADD
                collision_objects.append(bottle_object)
                added_object_specs.append({
                    "id": spec["id"],
                    "position": {"x": bottle_pose.position.x, "y": bottle_pose.position.y, "z": bottle_pose.position.z},
                })
                bottle_created_specs.append({"id": spec["id"]})
        
        # 应用碰撞对象 - 模拟原始的 psi.applyCollisionObjects(collision_objects)
        if use_service:
            planning_scene_msg = PlanningScene()
            planning_scene_msg.world.collision_objects = collision_objects
            planning_scene_msg.is_diff = True
            # 设置墙的颜色透明度（如果启用）
            if add_no_go_wall:
                oc = ObjectColor()
                oc.id = "no_go_wall"
                # 颜色: 绿色略偏淡，alpha控制透明(0~1)
                oc.color.r = 0.2
                oc.color.g = 0.9
                oc.color.b = 0.2
                oc.color.a = float(max(0.0, min(1.0, wall_alpha)))
                planning_scene_msg.object_colors.append(oc)
            request = ApplyPlanningScene.Request()
            request.scene = planning_scene_msg
            future = apply_scene_client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=timeout_sec)
            if future.result() is not None and future.result().success:
                node.get_logger().info("Applied planning scene via service (like original PlanningSceneInterface)")
                method = "service"
            else:
                node.get_logger().warn("Service call failed, falling back to topic publishing")
                use_service = False
        
        if not use_service:
            if 'collision_object_pub' not in locals():
                collision_object_pub = node.create_publisher(CollisionObject, '/collision_object', 10)
                time.sleep(0.5)
            for obj in collision_objects:
                collision_object_pub.publish(obj)
                node.get_logger().info(f"Published collision object: {obj.id}")
                time.sleep(0.1)
            # 额外通过 /planning_scene 话题设置颜色
            if add_no_go_wall:
                planning_scene_pub = node.create_publisher(PlanningScene, '/planning_scene', 10)
                time.sleep(0.2)
                ps = PlanningScene()
                ps.is_diff = True
                oc = ObjectColor()
                oc.id = "no_go_wall"
                oc.color.r = 0.2
                oc.color.g = 0.9
                oc.color.b = 0.2
                oc.color.a = float(max(0.0, min(1.0, wall_alpha)))
                ps.object_colors.append(oc)
                planning_scene_pub.publish(ps)
                node.get_logger().info(f"Published color for no_go_wall with alpha={oc.color.a:.2f}")
            method = "topic"
        
        time.sleep(1.0)
        
        # 将每个对象（杯子/碗）的原始位置写入模块化服务器的参数表（供 place.return_to_origin 回退使用）
        try:
            origin_params_ok = False
            if added_object_specs:
                param_map: Dict[str, Any] = {}
                for obj in added_object_specs:
                    oid = str(obj["id"]).strip()
                    pos = obj["position"]
                    param_map[f"place.origin.{oid}.x"] = float(pos["x"])  # 已是 link_base 下坐标
                    param_map[f"place.origin.{oid}.y"] = float(pos["y"]) 
                    param_map[f"place.origin.{oid}.z"] = float(pos["z"]) 
                # 写入并重试一次
                origin_params_ok = _set_params('/modular_task_server', param_map, timeout_sec=5.0)
                if not origin_params_ok:
                    node.get_logger().warn("写入place.origin参数超时，重试一次…")
                    origin_params_ok = _set_params('/modular_task_server', param_map, timeout_sec=10.0)
                if origin_params_ok:
                    node.get_logger().info(f"已写入 {len(added_object_specs)} 个对象的原始位姿到 /modular_task_server")
                else:
                    node.get_logger().warn("未能写入place.origin参数，后续回原位/基于object移动可能退化")
        except Exception:
            origin_params_ok = False
            pass
        
        added_objects = [obj.id for obj in collision_objects]
        cup_ids = [spec["id"] for spec in cup_created_specs]
        bowl_ids = [spec["id"] for spec in bowl_created_specs]
        bottle_ids = [spec["id"] for spec in bottle_created_specs]
        
        node.get_logger().info("Planning scene setup completed!")
        node.get_logger().info(f"Added objects using {method}: {added_objects}")
        if added_cup_specs:
            node.get_logger().info(f"Added {len(added_cup_specs)} cup objects: {cup_ids}")
        if bowl_created_specs:
            node.get_logger().info(f"Added {len(bowl_created_specs)} bowl objects: {bowl_ids}")
        if bottle_created_specs:
            node.get_logger().info(f"Added {len(bottle_created_specs)} bottle objects: {bottle_ids}")
        
        return {
            "ok": True,
            "status": "success",
            "objects_added": added_objects,
            "table_objects": ["table_surface"],
            "cup_included": bool(cup_created_specs),
            "cup_count": len(cup_created_specs),
            "cup_ids": cup_ids,
            "cups": added_cup_specs,
            "bowl_included": bool(bowl_created_specs),
            "bowl_count": len(bowl_created_specs),
            "bowl_ids": bowl_ids,
            "bottle_included": bool(bottle_created_specs),
            "bottle_count": len(bottle_created_specs),
            "bottle_ids": bottle_ids,
            "method": method,
            "no_go_wall": add_no_go_wall,
            "wall_alpha": float(max(0.0, min(1.0, wall_alpha))),
            "origin_params_written": bool(locals().get('origin_params_ok', False)),
            "msg": f"Successfully added {len(added_objects)} objects to planning scene using {method}"
        }
        
    except Exception as e:
        node.get_logger().error(f"Failed to setup planning scene: {str(e)}")
        return {
            "ok": False,
            "status": "error",
            "error": str(e),
            "msg": f"Planning scene setup failed: {str(e)}"
        }
        
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


def check_object_exists(object_id: str = "object_1", timeout_sec: float = 5.0) -> Dict[str, Any]:
    """检查指定的碰撞对象是否存在于规划场景中。
    
    Args:
        object_id: 要检查的对象ID
        timeout_sec: 超时时间
        
    Returns:
        包含对象存在状态的字典
    """
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('object_checker'))
    
    try:
        from moveit_msgs.srv import GetPlanningScene
        from moveit_msgs.msg import PlanningSceneComponents
        import time
        
        # 使用GetPlanningScene服务查询对象
        client = node.create_client(GetPlanningScene, '/get_planning_scene')
        
        if not client.wait_for_service(timeout_sec=timeout_sec):
            node.get_logger().warn("GetPlanningScene service not available, assuming object doesn't exist")
            return {
                "ok": True,
                "status": "service_unavailable",
                "object_exists": False,
                "object_id": object_id,
                "known_objects": [],
                "msg": f"Cannot verify object '{object_id}' - planning scene service unavailable"
            }
        
        # 构建请求
        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.WORLD_OBJECT_NAMES
        
        # 发送请求
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=timeout_sec)
        
        if future.result() is not None:
            response = future.result()
            world_objects = response.scene.world.collision_objects
            known_objects = [obj.id for obj in world_objects]
            object_exists = object_id in known_objects
            
            node.get_logger().info(f"Checking for object '{object_id}': {'Found' if object_exists else 'Not found'}")
            node.get_logger().info(f"Known objects in scene: {known_objects}")
            
            return {
                "ok": True,
                "status": "success",
                "object_exists": object_exists,
                "object_id": object_id,
                "known_objects": known_objects,
                "msg": f"Object '{object_id}' {'exists' if object_exists else 'not found'} in planning scene"
            }
        else:
            node.get_logger().error("Failed to get response from planning scene service")
            return {
                "ok": False,
                "status": "service_timeout",
                "object_exists": False,
                "object_id": object_id,
                "known_objects": [],
                "error": "Service call timeout",
                "msg": f"Failed to check object existence: service timeout"
            }
        
    except Exception as e:
        node.get_logger().error(f"Failed to check object existence: {str(e)}")
        return {
            "ok": False,
            "status": "error",
            "object_exists": False,
            "error": str(e),
            "msg": f"Failed to check object existence: {str(e)}"
        }
        
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


def update_cup_pose(cup_x: float, cup_y: float, cup_z: float,
                    cup_qx: Optional[float] = None, cup_qy: Optional[float] = None,
                    cup_qz: Optional[float] = None, cup_qw: Optional[float] = 1.0,
                    cup_height: float = 0.1, cup_radius: float = 0.02,
                    timeout_sec: float = 5.0) -> Dict[str, Any]:
    """更新杯子对象的位姿。
    
    Args:
        cup_x, cup_y, cup_z: 新的杯子位置坐标
        cup_qx, cup_qy, cup_qz, cup_qw: 新的杯子方向四元数（可选）
        cup_height: 杯子高度（米）
        cup_radius: 杯子半径（米）
        timeout_sec: 超时时间
        
    Returns:
        包含更新结果的字典
    """
    created = _ensure_rclpy_inited()
    import rclpy
    node = rclpy.create_node(_unique_node_name('cup_pose_updater'))
    
    try:
        from moveit_msgs.msg import CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene
        from shape_msgs.msg import SolidPrimitive
        from geometry_msgs.msg import Pose
        import time
        
        # 先检查杯子对象是否存在
        check_result = check_object_exists("object_1", timeout_sec=timeout_sec/2)
        if not check_result["ok"] or not check_result["object_exists"]:
            return {
                "ok": False,
                "status": "not_found",
                "msg": "Cup object 'object_1' not found in planning scene. Please setup planning scene first."
            }
        
        # 使用ApplyPlanningScene服务来更新对象，与setup_planning_scene保持一致
        apply_scene_client = node.create_client(ApplyPlanningScene, '/apply_planning_scene')
        
        if not apply_scene_client.wait_for_service(timeout_sec=timeout_sec/2):
            # 备用方案：使用topic发布
            collision_object_pub = node.create_publisher(CollisionObject, '/collision_object', 10)
            time.sleep(0.5)
            use_service = False
        else:
            use_service = True
        
        # 创建新的杯子对象来替换现有的
        cup_object = CollisionObject()
        cup_object.header.stamp = node.get_clock().now().to_msg()
        cup_object.header.frame_id = "link_base"
        cup_object.id = "object_1"
        cup_object.primitives.append(SolidPrimitive())
        cup_object.primitives[0].type = SolidPrimitive.CYLINDER
        cup_object.primitives[0].dimensions = [cup_height, cup_radius]
        
        cup_pose = Pose()
        cup_pose.position.x = cup_x
        cup_pose.position.y = cup_y
        cup_pose.position.z = cup_z
        
        # 设置方向
        if all(q is not None for q in [cup_qx, cup_qy, cup_qz, cup_qw]):
            cup_pose.orientation.x = cup_qx
            cup_pose.orientation.y = cup_qy
            cup_pose.orientation.z = cup_qz
            cup_pose.orientation.w = cup_qw
        else:
            cup_pose.orientation.w = 1.0
        
        cup_object.primitive_poses.append(cup_pose)
        cup_object.operation = CollisionObject.ADD  # 使用ADD操作替换对象（MoveIt会自动覆盖同名对象）
        
        # 更新对象 - 使用先删除再添加的可靠方法
        if use_service:
            # 方式1：先删除现有对象
            remove_object = CollisionObject()
            remove_object.header.stamp = node.get_clock().now().to_msg()
            remove_object.header.frame_id = "link_base"
            remove_object.id = "object_1"
            remove_object.operation = CollisionObject.REMOVE
            
            planning_scene_remove = PlanningScene()
            planning_scene_remove.world.collision_objects = [remove_object]
            planning_scene_remove.is_diff = True
            
            request_remove = ApplyPlanningScene.Request()
            request_remove.scene = planning_scene_remove
            
            future_remove = apply_scene_client.call_async(request_remove)
            rclpy.spin_until_future_complete(node, future_remove, timeout_sec=timeout_sec/4)
            
            # 短暂等待删除完成
            time.sleep(0.2)
            
            # 方式2：重新添加对象到新位置
            planning_scene_add = PlanningScene()
            planning_scene_add.world.collision_objects = [cup_object]
            planning_scene_add.is_diff = True
            
            request_add = ApplyPlanningScene.Request()
            request_add.scene = planning_scene_add
            
            future_add = apply_scene_client.call_async(request_add)
            rclpy.spin_until_future_complete(node, future_add, timeout_sec=timeout_sec/2)
            
            if future_add.result() is not None and future_add.result().success:
                method = "service (remove+add)"
                node.get_logger().info("Successfully removed and re-added cup object at new position")
            else:
                use_service = False
        
        if not use_service:
            # 备用方案：topic发布（先删除再添加）
            if 'collision_object_pub' not in locals():
                collision_object_pub = node.create_publisher(CollisionObject, '/collision_object', 10)
                time.sleep(0.5)
            
            # 删除旧对象
            remove_object = CollisionObject()
            remove_object.header.stamp = node.get_clock().now().to_msg()
            remove_object.header.frame_id = "link_base"
            remove_object.id = "object_1"
            remove_object.operation = CollisionObject.REMOVE
            collision_object_pub.publish(remove_object)
            time.sleep(0.2)
            
            # 添加新对象
            collision_object_pub.publish(cup_object)
            method = "topic (remove+add)"
        
        time.sleep(0.5)  # 等待更新生效
        
        node.get_logger().info(f"Updated cup pose using {method} to: x={cup_x:.3f}, y={cup_y:.3f}, z={cup_z:.3f}")
        
        return {
            "ok": True,
            "status": "success",
            "cup_position": {"x": cup_x, "y": cup_y, "z": cup_z},
            "cup_orientation": {"x": cup_qx, "y": cup_qy, "z": cup_qz, "w": cup_qw} if all(q is not None for q in [cup_qx, cup_qy, cup_qz, cup_qw]) else None,
            "method": method,
            "msg": "Cup pose updated successfully"
        }
        
    except Exception as e:
        node.get_logger().error(f"Failed to update cup pose: {str(e)}")
        return {
            "ok": False,
            "status": "error",
            "error": str(e),
            "msg": f"Failed to update cup pose: {str(e)}"
        }
        
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


# =============== 对外工具：设置杯子位姿 ===============

def set_cup_pose(x: float, y: float, z: float,
                  qx: Optional[float] = None, qy: Optional[float] = None,
                  qz: Optional[float] = None, qw: Optional[float] = None,
                  valid: bool = True,
                  server_node: str = '/execute_pour_server',
                  timeout_sec: float = 5.0) -> bool:
    """设置 /execute_pour_server 的杯子位姿参数。
    若未提供四元数，将仅设置位置（姿态保持不变）。
    """
    p: Dict[str, Any] = {
        'cup_pose.x': float(x),
        'cup_pose.y': float(y),
        'cup_pose.z': float(z),
        'cup_pose.valid': bool(valid),
    }
    if qx is not None and qy is not None and qz is not None and qw is not None:
        p.update({
            'cup_pose.qx': float(qx),
            'cup_pose.qy': float(qy),
            'cup_pose.qz': float(qz),
            'cup_pose.qw': float(qw),
        })
    return _set_params(server_node, p, timeout_sec=timeout_sec)


# =============== 对外工具：设置夹爪闭合比例 ===============

def set_gripper_close_ratio(ratio: float,
                                 server_node: str = '/execute_pour_server',
                                 timeout_sec: float = 5.0) -> bool:
    """设置夹爪闭合比例参数 gripper.close_ratio （0.0 ~ 1.0）。"""
    ratio = max(0.0, min(1.0, float(ratio)))
    return _set_params(server_node, {'gripper.close_ratio': ratio}, timeout_sec=timeout_sec)


# =============== 模块化任务执行工具 ===============

def _execute_real_mtc_task(task_type: str, params_dict: Dict[str, Any], task_name: str, 
                          action_name: str = 'execute_modular_task', timeout_sec: float = 180.0) -> Dict[str, Any]:
    """使用真实的模块化任务服务器执行MTC任务
    
    Args:
        task_type: 任务类型 ("pick", "pour", "place", "return")
        params_dict: 任务参数字典
        task_name: 任务名称（用于日志）
        action_name: Action服务器名称
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典
    """
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('real_mtc_client'))
    
    try:
        import time
        
        node.get_logger().info(f"🚀 开始执行{task_name}任务 (类型: {task_type}) - 使用真实模块化任务服务器")
        
        # 环境变量已在模块级别设置，无需重复设置
        
        # 导入Action客户端
        from rclpy.action import ActionClient
        import mtc_interface.action
        
        # 创建Action客户端
        action_client = ActionClient(node, mtc_interface.action.ExecutePour, action_name)
        
        # 针对 pick 任务：在发送 goal 之前，将参数写入模块化服务器的参数表
        if task_type == "pick":
            server_node = '/modular_task_server'
            param_map: Dict[str, Any] = {}
            if 'safe_approach_height' in params_dict:
                param_map['pick.safe_approach_height'] = float(params_dict['safe_approach_height'])
            if 'use_back_constraint' in params_dict:
                param_map['pick.use_back_constraint'] = bool(params_dict['use_back_constraint'])
            for k_src, k_dst in [
                ('back_region_center_y', 'pick.back_region_center_y'),
                ('back_region_size_x', 'pick.back_region_size_x'),
                ('back_region_size_y', 'pick.back_region_size_y'),
                ('back_region_size_z', 'pick.back_region_size_z'),
            ]:
                if k_src in params_dict:
                    param_map[k_dst] = float(params_dict[k_src])
            if 'object_id' in params_dict:
                oid = str(params_dict['object_id']).strip()
                param_map['pick.object_id'] = oid
            if param_map:
                node.get_logger().info(f"设置模块化服务器参数: {param_map}")
                ok = _set_params(server_node, param_map, timeout_sec=6.0)
                if not ok:
                    node.get_logger().warn("pick 参数设置超时，重试一次（延长超时）…")
                    ok = _set_params(server_node, param_map, timeout_sec=15.0)
                if not ok:
                    node.get_logger().warn("设置 pick 参数失败（可能未启动或节点名不匹配）：/modular_task_server")
        
        # 针对 place 任务：写入简化参数（return_to_origin / target_x/y/z / object_id）
        if task_type == "place":
            server_node = '/modular_task_server'
            param_map: Dict[str, Any] = {}
            if 'object_id' in params_dict:
                oid = str(params_dict['object_id']).strip()
                param_map['place.object_id'] = oid
            if params_dict.get('return_to_origin', False):
                param_map['place.return_to_origin'] = True
            else:
                if 'target_x' in params_dict:
                    param_map['place.target_x'] = float(params_dict['target_x'])
                if 'target_y' in params_dict:
                    param_map['place.target_y'] = float(params_dict['target_y'])
                if 'target_z' in params_dict:
                    param_map['place.target_z'] = float(params_dict['target_z'])
            if param_map:
                node.get_logger().info(f"设置模块化服务器参数: {param_map}")
                ok = _set_params(server_node, param_map, timeout_sec=6.0)
                if not ok:
                    node.get_logger().warn("place 参数设置超时，重试一次（延长超时）…")
                    ok = _set_params(server_node, param_map, timeout_sec=15.0)
                if not ok:
                    node.get_logger().warn("设置 place 参数失败（可能未启动或节点名不匹配）：/modular_task_server")
        
        # 等待服务器
        if not action_client.wait_for_server(timeout_sec=10.0):
            return {
                "ok": False,
                "status": "no_server",
                "error": f"模块化任务服务器不可用: {action_name}",
                "params": params_dict,
                "task_name": task_name
            }
        
        # 构建Goal (复用ExecutePour的消息格式，通过target_id指定任务类型)
        goal = mtc_interface.action.ExecutePour.Goal()
        # 关键：通过target_id指定任务类型；若传入object_id，则编码为 task:object_id
        if task_type in ("pick", "place", "move_to_pour") and 'object_id' in params_dict and params_dict['object_id']:
            goal.target_id = f"{task_type}:{str(params_dict['object_id']).strip()}"
        else:
            goal.target_id = task_type
        
        # 映射参数到ExecutePour格式
        goal.tilt_start_deg = float(params_dict.get("tilt_start_deg", 45.0))
        goal.tilt_end_deg = float(params_dict.get("tilt_end_deg", 120.0)) 
        goal.tilt_speed_deg_s = float(params_dict.get("tilt_speed_deg_s", 25.0))
        goal.pour_hold_sec = float(params_dict.get("pour_hold_sec", 2.0))
        goal.lift_height = float(params_dict.get("lift_height", 0.12))
        goal.approach_min = float(params_dict.get("approach_min", 0.05))
        goal.approach_max = float(params_dict.get("approach_max", 0.15))
        goal.plan_only = bool(params_dict.get("plan_only", False))
        
        node.get_logger().info(f"🎯 发送{task_name}任务到模块化服务器")
        node.get_logger().info(f"📋 任务类型: {task_type} (通过target_id传递: {goal.target_id})")
        node.get_logger().info(f"⚙️ 参数: approach=[{goal.approach_min:.2f}, {goal.approach_max:.2f}], lift={goal.lift_height:.2f}")
        # 🔧 调试信息：显示是否包含object_id
        if 'object_id' in params_dict and params_dict['object_id']:
            node.get_logger().info(f"🎯 包含object_id: {params_dict['object_id']}")
        
        # 反馈处理
        def feedback_callback(feedback_msg):
            fb = feedback_msg.feedback
            node.get_logger().info(f"[{fb.stage}] 进度: {fb.progress:.1%}")
        
        # 发送目标（更稳健：更长等待+一次重试）
        def _send_and_wait(timeout: float):
            fut = action_client.send_goal_async(goal, feedback_callback=feedback_callback)
            rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
            return fut
        
        send_future = _send_and_wait(12.0)
        gh = send_future.result() if send_future.done() else None
        
        # 如果首次未获得响应或被拒绝，等待服务稳定后重试一次
        if gh is None or not getattr(gh, 'accepted', False):
            node.get_logger().warn("首次发送goal未获得接受，等待服务稳定后重试一次…")
            action_client.wait_for_server(timeout_sec=3.0)
            send_future = _send_and_wait(12.0)
            gh = send_future.result() if send_future.done() else None
        
        if gh is None or not getattr(gh, 'accepted', False):
            return {
                "ok": False,
                "status": "rejected",
                "error": "任务被模块化服务器拒绝或未响应（已重试）",
                "params": params_dict,
                "task_name": task_name
            }
        
        node.get_logger().info(f'✅ {task_name}任务已被模块化服务器接受，开始执行...')
        start_time = time.time()
        
        # 等待结果
        result_future = gh.get_result_async()
        while not result_future.done():
            if timeout_sec and time.time() - start_time > timeout_sec:
                node.get_logger().error(f"任务超时 {timeout_sec}s，取消任务")
                gh.cancel_goal_async()
                break
            rclpy.spin_once(node, timeout_sec=0.2)
        
        if not result_future.done():
            return {
                "ok": False,
                "status": "timeout",
                "error": f"任务超时 {timeout_sec}s",
                "params": params_dict,
                "task_name": task_name
            }
        
        # 处理结果
        result_msg = result_future.result()
        result = result_msg.result
        status_code = result_msg.status
        
        status_map = {4: "succeeded", 5: "canceled", 6: "aborted"}
        status_str = status_map.get(status_code, "unknown")
        
        node.get_logger().info(f'🎉 {task_name}任务执行完成: {status_str}, 成功={result.success}, 耗时={result.duration_sec:.2f}s')
        
        success_note = ""
        if result.success:
            success_note = f"✅ 真实的模块化MTC任务执行成功！使用了{task_type}任务构建器"
        
        return {
            "ok": bool(result.success) and status_code == 4,
            "status": status_str,
            "success": bool(result.success),
            "duration_sec": float(result.duration_sec),
            "error": result.error_msg,
            "params": params_dict,
            "task_name": task_name,
            "plan_only": params_dict.get('plan_only', False),
            "note": success_note,
            "used_modular_server": True,
            "task_type": task_type
            }
        
    except Exception as e:
        node.get_logger().error(f"{task_name}任务执行异常: {str(e)}")
        return {
            "ok": False,
            "status": "error",
            "success": False,
            "error": f"客户端执行异常: {str(e)}",
            "params": params_dict,
            "task_name": task_name
        }
        
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)


def pick_container(source_pose: Dict[str, float], 
                   grasp_hint: Optional[Dict[str, float]] = None,
                   object_id: str = "object_1", 
                   plan_only: bool = False,
                   timeout_sec: float = 180.0) -> Dict[str, Any]:
    """抓取容器
    
    Args:
        source_pose: 源位姿 {"x": float, "y": float, "z": float, 可选: "qx", "qy", "qz", "qw"}
        grasp_hint: 抓取提示 {"approach_min": float, "approach_max": float, "lift_height": float,
                           可选: "safe_approach_height": float,
                           可选: "use_back_constraint": bool,
                           可选: "back_region_center_y"/"back_region_size_x"/"back_region_size_y"/"back_region_size_z"}
        object_id: 目标对象ID
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典
    """
    params = {
        "source_x": source_pose.get("x", 0.0),
        "source_y": source_pose.get("y", -0.4),
        "source_z": source_pose.get("z", 0.13),
        "source_qx": source_pose.get("qx", 0.0),
        "source_qy": source_pose.get("qy", 0.0), 
        "source_qz": source_pose.get("qz", 0.0),
        "source_qw": source_pose.get("qw", 1.0),
        "object_id": (object_id.strip() if isinstance(object_id, str) else object_id),
        "plan_only": plan_only
    }
    
    if grasp_hint:
        params.update({
            "approach_min": grasp_hint.get("approach_min", 0.05),
            "approach_max": grasp_hint.get("approach_max", 0.15),
            "lift_height": grasp_hint.get("lift_height", 0.12)
        })
        # 新增：安全高度与后方约束（如提供）
        if "safe_approach_height" in grasp_hint:
            params["safe_approach_height"] = grasp_hint["safe_approach_height"]
        for k in ("use_back_constraint", "back_region_center_y", "back_region_size_x", "back_region_size_y", "back_region_size_z"):
            if k in grasp_hint:
                params[k] = grasp_hint[k]
    else:
        params.update({
            "approach_min": 0.05,
            "approach_max": 0.15,
            "lift_height": 0.12
        })
    
    # 使用真实的模块化任务服务器
    try:
        return _execute_real_mtc_task("pick", params, "抓取容器", 'execute_modular_task', timeout_sec)
    except Exception as e:
        # 使用标准化错误处理
        return _create_error_result("抓取容器", f"模块化服务器不可用: {str(e)}", 
                                   params, "server_unavailable")


def pour_to_target(target_pose: Optional[Dict[str, float]] = None,
                   tilt_deg: Dict[str, float] = {"start": 45.0, "end": 120.0},
                   speed: float = 25.0,
                   stop_condition: Dict[str, float] = {"hold_time": 2.0},
                   move_distance: Optional[Dict[str, float]] = None,
                   plan_only: bool = False,
                   timeout_sec: float = 180.0) -> Dict[str, Any]:
    """执行倾倒动作
    
    Args:
        target_pose: 目标倾倒位置（可选，将使用移动相对距离）
        tilt_deg: 倾斜角度 {"start": float, "end": float}
        speed: 倾斜速度（度/秒）
        stop_condition: 停止条件 {"hold_time": float}
        move_distance: 移动距离 {"min": float, "max": float}
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典
    """
    params = {
        "tilt_start_deg": tilt_deg.get("start", 45.0),
        "tilt_end_deg": tilt_deg.get("end", 120.0),
        "tilt_speed_deg_s": speed,
        "pour_hold_sec": stop_condition.get("hold_time", 2.0),
        "plan_only": plan_only
    }
    
    if target_pose:
        params.update({
            "target_x": target_pose.get("x", 0.1),
            "target_y": target_pose.get("y", -0.5),
            "target_z": target_pose.get("z", 0.13)
        })
    
    if move_distance:
        params.update({
            "move_to_pour_min": move_distance.get("min", 0.08),
            "move_to_pour_max": move_distance.get("max", 0.15)
        })
    else:
        params.update({
            "move_to_pour_min": 0.08,
            "move_to_pour_max": 0.15
        })
    
    # 使用真实的模块化任务服务器
    try:
        return _execute_real_mtc_task("pour", params, "倾倒液体", 'execute_modular_task', timeout_sec)
    except Exception as e:
        # 使用标准化错误处理
        return _create_error_result("倾倒液体", f"模块化服务器不可用: {str(e)}", 
                                   params, "server_unavailable")


# 请使用move_to_pour_position + pour_to_target的组合来实现类似功能

def place_container(target_pose: Optional[Dict[str, float]] = None,
                    object_id: str = "object_1",
                    return_to_origin: bool = False,
                    plan_only: bool = False,
                    timeout_sec: float = 180.0) -> Dict[str, Any]:
    """放置容器
    
    Args:
        target_pose: 目标放置位置（可选，提供 x/y/z 即可）
        object_id: 目标对象ID
        return_to_origin: 若为True，优先放回 object_id 的初始位置
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典
    """
    params = {
        "object_id": (object_id.strip() if isinstance(object_id, str) else object_id),
        "plan_only": plan_only
    }
    # 简化：仅三种情况
    # 1) return_to_origin=True -> 服务器读取场景初始位姿
    if return_to_origin:
        params["return_to_origin"] = True
    # 2) or 提供 x/y/z 即可
    elif target_pose:
        if any(k in target_pose for k in ("x", "y", "z")):
            params["target_x"] = target_pose.get("x", 0.0)
            params["target_y"] = target_pose.get("y", -0.45)
            params["target_z"] = target_pose.get("z", 0.18)
    # 3) 否则使用服务器默认位置
    
    # 使用真实的模块化任务服务器
    try:
        return _execute_real_mtc_task("place", params, "放置容器", 'execute_modular_task', timeout_sec)
    except Exception as e:
        # 使用标准化错误处理
        return _create_error_result("放置容器", f"模块化服务器不可用: {str(e)}", 
                                   params, "server_unavailable")


def move_to_pour_position(x: float,
                          y: float,
                          z: float,
                          speed: float = 0.15,
                          timeout_sec: float = 60.0,
                          pour_execute: bool = False,
                          tilt_deg: Dict[str, float] = {"start": 45.0, "end": 120.0},
                          tilt_speed_deg_s: float = 25.0,
                          pour_hold_sec: float = 0.0,
                          execute_give: bool = False,
                          gripper_open_ratio: float = 1.0,
                          object_id: Optional[str] = None,
                          force_clear_params: bool = False) -> Dict[str, Any]:
    """移动到指定的倾倒位置（保持当前抓取姿势）- 简化版本
    
    Args:
        x: 目标X坐标（米）- 当 object_id 为空时使用
        y: 目标Y坐标（米）- 当 object_id 为空时使用
        z: 目标Z坐标（米）- 当 object_id 为空时使用
        speed: 移动速度比例（0.05-0.3，默认0.15）
        timeout_sec: 超时时间（默认60秒）
        pour_execute: 是否在到达后执行简单倾倒序列
        tilt_deg: 倾斜角度范围 {"start": float, "end": float}
        tilt_speed_deg_s: 倾倒速度（度/秒）
        pour_hold_sec: 倾倒保持时间（秒）
        execute_give: 是否在到达后执行递给用户的动作（打开夹爪）
        gripper_open_ratio: 夹爪打开比例（0.0-1.0，1.0表示完全打开）
        object_id: 目标对象ID（可选）
        force_clear_params: 是否强制清除之前的参数（推荐在pour后使用，解决参数冲突问题）
    
    坐标传入逻辑（优化后）：
        1. 优先级：object_id > 自定义坐标(x,y,z) > 默认安全坐标
        2. 当 object_id 非空时：使用对象坐标，清除之前的自定义坐标参数
        3. 当 object_id 为空且传入有效坐标时：使用自定义坐标，清除之前的 object_id 参数  
        4. 当 object_id 为空且坐标为(0,0,0)时：使用默认安全坐标(0,-0.5,0.2)
        5. 参数清理：每次调用都会清除与当前模式冲突的参数，避免之前调用的干扰
    
    Returns:
        执行结果字典，包含：
        - coordinate_mode: "object_id" 或 "coordinates" 表示使用的模式
        - coordinate_info: 使用的坐标信息描述
        - coordinates_cleared/object_id_cleared: 表示清除了冲突参数
    
    使用示例：
    # 使用自定义坐标（安全位置）
    result = move_to_pour_position(x=-0.17, y=-0.45, z=0.42, object_id=None)
    
    # 使用对象坐标（会忽略 x,y,z 参数）
    result = move_to_pour_position(x=0, y=0, z=0, object_id="bowl")
    
    # 移动到安全位置并倾倒
    result = move_to_pour_position(x=0.2, y=-0.6, z=0.25, pour_execute=True,
                                   tilt_deg={"start": 60, "end": 120}, pour_hold_sec=2.0)
    
    # 移动到安全位置并递给用户
    result = move_to_pour_position(x=-0.17, y=-0.45, z=0.42, execute_give=True,
                                   gripper_open_ratio=1.0)
                                   
    # 在pour后安全移动（强制清除参数，解决冲突）
    result = move_to_pour_position(x=-0.17, y=-0.45, z=0.42, force_clear_params=True)
    """
    # 验证速度参数范围
    speed = max(0.05, min(0.3, speed))
    
    # 设置参数到模块化任务服务器 - 使用简化的核心参数
    # 优化坐标传入逻辑：明确区分 object_id 模式和坐标模式
    move_to_pour_params = {
        "move_to_pour.velocity_scaling": speed,
        "move_to_pour.acceleration_scaling": min(0.5, speed * 2.0),
        "move_to_pour.timeout_sec": timeout_sec,
        # 新增：融合后的倾倒控制
        "move_to_pour.pour_execute": bool(pour_execute),
        "move_to_pour.tilt_start_deg": float(tilt_deg.get("start", 45.0) if isinstance(tilt_deg, dict) else 45.0),
        "move_to_pour.tilt_end_deg": float(tilt_deg.get("end", 120.0) if isinstance(tilt_deg, dict) else 120.0),
        "move_to_pour.tilt_speed_deg_s": float(tilt_speed_deg_s),
        "move_to_pour.pour_hold_sec": float(pour_hold_sec),
        # 新增：递给用户控制
        "move_to_pour.execute_give": bool(execute_give),
        "move_to_pour.gripper_open_ratio": max(0.0, min(1.0, float(gripper_open_ratio)))
    }
    
    # 优化的坐标传入逻辑
    use_object_id = False
    resolved_oid = None
    
    # 1. 优先处理 object_id 模式（当 object_id 非空时）
    if object_id and str(object_id).strip():
        # 解析/规范化 object_id，例如 object3 -> object_3
        raw_oid = str(object_id).strip()
        norm_oid = raw_oid
        try:
            import re
            m = re.match(r"^(object)(\d+)$", raw_oid, re.IGNORECASE)
            if m:
                norm_oid = f"{m.group(1)}_{m.group(2)}"
        except Exception:
            pass
        # 查询当前场景的已知对象，尽量解析到真实存在的ID
        known = []
        try:
            check_any = check_object_exists(object_id="object_1", timeout_sec=2.0)
            if isinstance(check_any, dict):
                known = list(check_any.get("known_objects", []))
                print(f"🔍 [DEBUG] 场景中已知对象: {known}")
        except Exception:
            known = []
        
        for cand in [raw_oid, norm_oid]:
            if cand in known:
                resolved_oid = cand
                use_object_id = True
                print(f"🔍 [DEBUG] 找到匹配的object_id: {cand} (从输入 {raw_oid} 解析)")
                break
        
        if not use_object_id:
            print(f"⚠️ [DEBUG] 没有找到匹配的object_id，输入: {raw_oid}, 规范化: {norm_oid}")
            # 容错：若场景中仅有一个 bowl* 对象，则使用它
            bowl_like = [k for k in known if k.startswith("bowl")]
            non_table = [k for k in known if k not in ("table_surface", "no_go_wall")]
            if len(bowl_like) == 1:
                resolved_oid = bowl_like[0]
                use_object_id = True
                print(f"🔄 [DEBUG] 容错使用bowl对象: {resolved_oid}")
            elif norm_oid.lower() == "bowl" and "bowl" in known:
                resolved_oid = "bowl"
                use_object_id = True
                print(f"🔄 [DEBUG] 容错使用bowl: {resolved_oid}")
            elif raw_oid in ("object3", "object_3") and not [k for k in known if k.startswith("object")]:
                # 没有object*但可能只有bowl，兜底选一个非台面对象
                resolved_oid = bowl_like[0] if bowl_like else (non_table[0] if non_table else None)
                if resolved_oid:
                    use_object_id = True
                    print(f"🔄 [DEBUG] 兜底使用对象: {resolved_oid}")

    # 2. 根据使用模式设置对应参数（修复：不使用空字符串，分批设置参数）
    if use_object_id and resolved_oid:
        # 使用 object_id 模式：仅设置 object_id 和控制参数
        move_to_pour_params["move_to_pour.object_id"] = resolved_oid
        # 不设置坐标参数，让服务器使用object_id模式
    else:
        # 使用坐标模式：设置坐标和控制参数
        # 验证坐标有效性（非零坐标）
        has_valid_coords = not (x == 0.0 and y == 0.0 and z == 0.0)
        if has_valid_coords:
            move_to_pour_params["move_to_pour.target_x"] = float(x)
            move_to_pour_params["move_to_pour.target_y"] = float(y) 
            move_to_pour_params["move_to_pour.target_z"] = float(z)
        else:
            # 如果传入的坐标全为0，使用默认安全坐标
            move_to_pour_params["move_to_pour.target_x"] = 0.0
            move_to_pour_params["move_to_pour.target_y"] = -0.5
            move_to_pour_params["move_to_pour.target_z"] = 0.2
        # 不设置 object_id 参数，让服务器使用坐标模式
    
    # 设置参数到服务器 - 采用更安全的两阶段设置
    server_node = '/modular_task_server'
    
    # 预阶段：如果强制清除参数，先重置所有相关参数（适用于pour后的安全移动）
    if force_clear_params:
        force_clear = {
            "move_to_pour.object_id": "none",
            "move_to_pour.target_x": 0.0,
            "move_to_pour.target_y": 0.0,
            "move_to_pour.target_z": 0.0,
            "move_to_pour.pour_execute": False,
            "move_to_pour.execute_give": False,
            "move_to_pour.velocity_scaling": 0.1,  # 先设置低速
            "move_to_pour.acceleration_scaling": 0.2,
        }
        _set_params(server_node, force_clear, timeout_sec=8.0)
        import time
        time.sleep(0.8)  # 等待强制清除生效
    
    # 阶段1：如果模式切换，先清除可能冲突的参数（使用有效的默认值而不是空字符串）
    clear_params = {}
    if use_object_id and resolved_oid:
        # 要使用 object_id，清除可能的坐标参数
        clear_params.update({
            "move_to_pour.target_x": 0.0,
            "move_to_pour.target_y": 0.0, 
            "move_to_pour.target_z": 0.0
        })
    else:
        # 要使用坐标，清除可能的 object_id 参数
        clear_params["move_to_pour.object_id"] = "none"  # 使用特殊值表示无对象
    
    # 先清除冲突参数（如果没有强制清除）
    if clear_params and not force_clear_params:
        _set_params(server_node, clear_params, timeout_sec=5.0)  # 快速清除，不阻塞主流程
    
    # 阶段2：设置主要参数
    if not _set_params(server_node, move_to_pour_params, timeout_sec=20.0):
        # 重试一次，延长超时，缓解服务器忙碌导致的响应延迟
        if not _set_params(server_node, move_to_pour_params, timeout_sec=30.0):
            return _create_error_result("移动到倾倒位置", 
                                       f"无法设置参数到服务器 {server_node}. 参数: {move_to_pour_params}",
                                       move_to_pour_params, "param_setting_failed")
    
    # 构建任务执行参数
    params = {
        "plan_only": False,
        "timeout_sec": timeout_sec,
        # 兼容ExecutePour接口的占位参数（不会被使用，但避免接口错误）
        "tilt_start_deg": 45.0,
        "tilt_end_deg": 120.0,
        "tilt_speed_deg_s": 25.0,
        "pour_hold_sec": 0.0,
        "approach_min": 0.05,
        "approach_max": 0.15,
        "lift_height": 0.12
    }
    
    # 🔧 修复：如果使用object_id模式，将resolved_oid添加到params中
    if use_object_id and resolved_oid:
        params["object_id"] = resolved_oid
        print(f"🔧 [DEBUG] 使用object_id模式: {resolved_oid}，已添加到params中")
    else:
        print(f"🔧 [DEBUG] 使用坐标模式: ({x}, {y}, {z})")
    
    # 使用模块化任务服务器执行移动
    try:
        # 生成任务名称，明确显示使用的模式
        if use_object_id and resolved_oid:
            task_name = f"移动到倾倒位置(对象:{resolved_oid})"
            coord_info = f"对象ID: {resolved_oid}"
        else:
            task_name = f"移动到倾倒位置(坐标:{x:.2f}, {y:.2f}, {z:.2f})"  
            coord_info = f"坐标: ({x:.3f}, {y:.3f}, {z:.3f})"
        
        # 添加额外功能到任务名称
        if pour_execute:
            task_name += " + 倾倒"
        if execute_give:
            task_name += " + 递给用户"
            
        result = _execute_real_mtc_task("move_to_pour", params, task_name,
                                       'execute_modular_task', timeout_sec)
        
        # 添加详细的配置信息到结果中
        if result.get("ok") or result.get("success"):
            info = {
                "coordinate_mode": "object_id" if use_object_id else "coordinates",
                "coordinate_info": coord_info,
                "speed": speed,
                "auto_acceleration": min(0.5, speed * 2.0),
                "optimized_defaults": True,
                "pour_execute": bool(pour_execute),
                "execute_give": bool(execute_give),
                "gripper_open_ratio": float(gripper_open_ratio) if execute_give else None,
                "parameter_strategy": "force_clear" if force_clear_params else "two_stage_safe_setting",
                "force_clear_params": bool(force_clear_params)  # 表示是否使用了强制参数清除
            }
            
            # 根据模式添加不同的信息
            if use_object_id and resolved_oid:
                info.update({
                    "object_id_input": str(object_id).strip() if object_id else "",
                    "resolved_object_id": resolved_oid,
                    "conflict_params_cleared": ["target_x", "target_y", "target_z"],
                    "mode_switch": "to_object_id"
                })
            else:
                info.update({
                    "target_position": {"x": x, "y": y, "z": z},
                    "conflict_params_cleared": ["object_id"],
                    "mode_switch": "to_coordinates"
                })
                if not (x == 0.0 and y == 0.0 and z == 0.0):
                    info["used_custom_coordinates"] = True
                else:
                    info["used_default_safe_coordinates"] = True
                    
            result["simplified_config"] = info
        
        return result
        
    except Exception as e:
        return _create_error_result("移动到倾倒位置", f"任务执行异常: {str(e)}", params, "execution_failed")


# 向后兼容性：保留旧接口，但标记为废弃
# def move_to_pour_position_legacy(target_position: Dict[str, float],
#                          movement_mode: str = "absolute",
#                          relative_movement: Optional[Dict[str, float]] = None,
#                          motion_params: Optional[Dict[str, float]] = None,
#                          plan_only: bool = False,
#                          timeout_sec: float = 60.0) -> Dict[str, Any]:
#     """废弃的复杂接口，建议使用简化版本的move_to_pour_position"""
#     import warnings
#     warnings.warn("move_to_pour_position_legacy已废弃，请使用简化版本的move_to_pour_position(x, y, z, speed)", 
#                   DeprecationWarning, stacklevel=2)
    
#     # 转换为新接口
#     x = target_position.get("x", 0.0)
#     y = target_position.get("y", -0.5)
#     z = target_position.get("z", 0.2)
    
#     speed = 0.15
#     if motion_params:
#         speed = motion_params.get("velocity_scaling", 0.15)
    
#     return move_to_pour_position(x=x, y=y, z=z, speed=speed, timeout_sec=timeout_sec)


def return_to_home(target_joints: Optional[Dict[str, float]] = None,
                   plan_only: bool = False,
                   timeout_sec: float = 60.0) -> Dict[str, Any]:
    """返回初始/安全位置
    
    Args:
        target_joints: 目标关节配置（可选，使用"home"配置）
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典
    """
    params = {
        "plan_only": plan_only,
        "timeout_sec": timeout_sec
    }
    
    if target_joints:
        params["target_joints"] = target_joints
    
    # 使用真实的模块化任务服务器
    try:
        return _execute_real_mtc_task("return", params, "返回初始位置", 'execute_modular_task', timeout_sec)
    except Exception as e:
        # 使用标准化错误处理
        return _create_error_result("返回初始位置", f"模块化服务器不可用: {str(e)}", 
                                   params, "server_unavailable")


# =============== Agent友好的辅助工具 ===============

def get_task_state(timeout_sec: float = 5.0) -> Dict[str, Any]:
    """获取当前任务状态，返回Agent可理解的结构化信息
    
    Returns:
        Dict包含：
        - stage: 当前阶段 ("idle", "planning", "executing", "completed", "error")
        - last_error: 最近的错误信息
        - robot_pose: 机器人末端执行器位姿
        - gripper_state: 夹爪状态 ("open", "closed", "grasping")
        - action_status: Action服务器状态
        - scene_objects: 场景中的对象信息
    """
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('task_state_checker'), start_parameter_services=False)
    result = {
        "stage": "unknown",
        "last_error": None,
        "robot_pose": None,
        "gripper_state": "unknown",
        "action_status": "unknown",
        "scene_objects": [],
        "timestamp": None,
        "system_ready": False
    }
    
    try:
        from sensor_msgs.msg import JointState
        from geometry_msgs.msg import PoseStamped
        from moveit_msgs.msg import PlanningScene
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        import time
        
        result["timestamp"] = time.time()
        
        # 检查Action服务器状态
        from rclpy.action import ActionClient
        try:
            import mtc_interface.action  # type: ignore
            action_client = ActionClient(node, mtc_interface.action.ExecutePour, '/execute_pour')
            if action_client.wait_for_server(timeout_sec=2.0):
                result["action_status"] = "available"
                result["system_ready"] = True
            else:
                result["action_status"] = "unavailable"
                result["last_error"] = "Execute pour action server not available"
        except Exception as e:
            result["action_status"] = "error"
            result["last_error"] = f"Action client setup failed: {str(e)}"
        
        # 获取关节状态 - 推断gripper状态 (UF850适配)
        joint_state_received = False
        def joint_callback(msg):
            nonlocal joint_state_received, result
            joint_state_received = True
            try:
                # 查找UF850夹爪关节 (主要是drive_joint)
                drive_joint_pos = None
                for i, name in enumerate(msg.name):
                    if name == 'drive_joint' and i < len(msg.position):
                        drive_joint_pos = msg.position[i]
                        break
                
                if drive_joint_pos is not None:
                    # UF850夹爪：0=张开，0.85=闭合 (根据SRDF配置)
                    if drive_joint_pos < 0.05:  # 几乎张开
                        result["gripper_state"] = "open"
                    elif drive_joint_pos > 0.75:  # 接近闭合
                        result["gripper_state"] = "closed"
                    else:
                        result["gripper_state"] = "grasping"  # 中间状态，可能在抓取
                    
                    result["gripper_position"] = float(drive_joint_pos)
                    result["gripper_position_normalized"] = float(drive_joint_pos / 0.85)  # 归一化到0-1
                else:
                    result["gripper_state"] = "unknown_no_drive_joint"
            except Exception as e:
                result["gripper_state"] = f"error: {str(e)}"
        
        # 获取机器人末端位姿 - 从tf或话题
        pose_received = False
        def pose_callback(msg):
            nonlocal pose_received, result
            pose_received = True
            result["robot_pose"] = {
                "position": {
                    "x": msg.pose.position.x,
                    "y": msg.pose.position.y,
                    "z": msg.pose.position.z
                },
                "orientation": {
                    "x": msg.pose.orientation.x,
                    "y": msg.pose.orientation.y,
                    "z": msg.pose.orientation.z,
                    "w": msg.pose.orientation.w
                },
                "frame_id": msg.header.frame_id
            }
        
        # 订阅关节状态
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        joint_sub = node.create_subscription(JointState, '/joint_states', joint_callback, qos)
        
        # 尝试订阅末端执行器位姿（多个可能的话题）
        pose_topics = ['/rviz_moveit_motion_planning_display/robot_interaction_interactive_marker_topic/feedback',
                       '/move_group/display_planned_path', 
                       '/end_effector_pose']
        pose_sub = None
        for topic in pose_topics:
            try:
                pose_sub = node.create_subscription(PoseStamped, topic, pose_callback, 1)
                break
            except:
                continue
        
        # 短暂等待数据
        start_time = time.time()
        while (time.time() - start_time) < min(timeout_sec, 3.0):
            rclpy.spin_once(node, timeout_sec=0.1)
            if joint_state_received:  # 至少得到关节状态就够了
                break
        
        # 推断当前阶段
        if result["system_ready"]:
            if result["gripper_state"] == "grasping":
                result["stage"] = "executing"  # 可能正在执行任务
            elif result["gripper_state"] == "open":
                result["stage"] = "idle"       # 准备状态
            elif result["gripper_state"] == "closed":
                result["stage"] = "completed"  # 可能刚完成任务
            else:
                result["stage"] = "idle"
        else:
            result["stage"] = "error"
            if not result["last_error"]:
                result["last_error"] = "System not ready for task execution"
        
        # 清理订阅
        if joint_sub:
            node.destroy_subscription(joint_sub)
        if pose_sub:
            node.destroy_subscription(pose_sub)
        
    except Exception as e:
        result["stage"] = "error"
        result["last_error"] = f"State check failed: {str(e)}"
        result["system_ready"] = False
    
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)
    
    return result


def abort_and_reset(reason: str = "User requested abort", 
                    safe_pose_joints: Optional[list] = None,
                    timeout_sec: float = 30.0,
                    force_stop: bool = True) -> Dict[str, Any]:
    """立即取消当前action并将机器人移动到安全位姿
    
    Args:
        reason: 取消原因
        safe_pose_joints: 安全位姿的关节角度，如果为None使用默认
        timeout_sec: 操作超时时间
        force_stop: 是否强制停止（会尝试多种方式确保停止）
        
    Returns:
        Dict包含操作结果和详细信息
        
    注意：这个函数设计为即使在其他任务运行时也能工作，
         通过直接与ROS action服务器通信来强制取消任务。
    """
    created = _ensure_rclpy_inited()
    node = rclpy.create_node(_unique_node_name('abort_and_reset_client'), start_parameter_services=False)
    result = {
        "success": False,
        "reason": reason,
        "actions_taken": [],
        "warnings": [],
        "robot_safe": False,
        "timestamp": None,
        "force_stop": force_stop
    }
    
    try:
        import time
        from rclpy.action import ActionClient
        from moveit_msgs.action import MoveGroup
        from moveit_msgs.msg import MotionPlanRequest, Constraints, JointConstraint
        from geometry_msgs.msg import Pose
        
        result["timestamp"] = time.time()
        result["actions_taken"].append(f"强制中止请求: {reason}")
        
        # 步骤1: 强制取消正在进行的倾倒action
        cancel_success = False
        try:
            import mtc_interface.action  # type: ignore
            pour_client = ActionClient(node, mtc_interface.action.ExecutePour, '/execute_pour')
            
            if pour_client.wait_for_server(timeout_sec=3.0):
                # 尝试取消所有可能的goals
                # 注意：由于rclpy ActionClient的限制，我们无法直接获取和取消特定的goal handles
                # 但是我们可以通过发送一个立即失败的goal来打断正在执行的任务
                
                if force_stop:
                    # 强制停止策略：发送一个无效的goal来打断当前执行
                    try:
                        invalid_goal = mtc_interface.action.ExecutePour.Goal()
                        invalid_goal.plan_only = True  # 仅规划，不执行
                        invalid_goal.tilt_start_deg = 0.0
                        invalid_goal.tilt_end_deg = 0.0
                        invalid_goal.tilt_speed_deg_s = 1.0
                        invalid_goal.pour_hold_sec = 0.0
                        invalid_goal.lift_height = 0.0
                        invalid_goal.approach_min = 0.01
                        invalid_goal.approach_max = 0.02
                        invalid_goal.target_id = "ABORT_REQUEST"
                        
                        # 发送这个goal会导致服务器处理新的请求，可能中断当前任务
                        send_future = pour_client.send_goal_async(invalid_goal)
                        rclpy.spin_until_future_complete(node, send_future, timeout_sec=2.0)
                        
                        if send_future.done():
                            gh = send_future.result()
                            if gh:
                                # 立即取消这个goal
                                gh.cancel_goal_async()
                                result["actions_taken"].append("发送中断信号到pour action server")
                                cancel_success = True
                            
                    except Exception as e:
                        result["warnings"].append(f"强制中断策略失败: {str(e)}")
                
                result["actions_taken"].append("Pour action server可用，尝试了中断操作")
            else:
                result["warnings"].append("Pour action server不可用，可能没有正在运行的任务")
                cancel_success = True  # 如果服务器不存在，认为取消成功
                
        except Exception as e:
            result["warnings"].append(f"Pour action取消操作失败: {str(e)}")
        
        # 等待一下确保取消操作生效
        if cancel_success:
            time.sleep(0.5)
        
        # 步骤2: 移动到安全位姿 (UF850适配)
        try:
            # 默认安全关节角度 (UF850 home pose: 6DOF全部为0)
            if safe_pose_joints is None:
                safe_pose_joints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # UF850 home pose
            
            # 使用MoveGroup Action移动到安全位姿
            mg_client = ActionClient(node, MoveGroup, '/move_action')
            
            if mg_client.wait_for_server(timeout_sec=5.0):
                # 构建MoveGroup goal
                goal = MoveGroup.Goal()
                goal.request.group_name = "uf850"  # UF850的group名称
                goal.request.max_velocity_scaling_factor = 0.3  # 安全速度
                goal.request.max_acceleration_scaling_factor = 0.3
                
                # 设置关节目标 (UF850的6个关节)
                joint_names = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
                
                joint_constraint = Constraints()
                for i, (name, value) in enumerate(zip(joint_names, safe_pose_joints[:6])):
                    jc = JointConstraint()
                    jc.joint_name = name
                    jc.position = float(value)
                    jc.tolerance_above = 0.01
                    jc.tolerance_below = 0.01
                    jc.weight = 1.0
                    joint_constraint.joint_constraints.append(jc)
                
                goal.request.goal_constraints.append(joint_constraint)
                
                # 发送目标并等待
                send_future = mg_client.send_goal_async(goal)
                rclpy.spin_until_future_complete(node, send_future, timeout_sec=5.0)
                
                if send_future.done():
                    goal_handle = send_future.result()
                    if goal_handle and goal_handle.accepted:
                        result_future = goal_handle.get_result_async()
                        rclpy.spin_until_future_complete(node, result_future, timeout_sec=timeout_sec)
                        
                        if result_future.done():
                            move_result = result_future.result()
                            if move_result and move_result.result.error_code.val == 1:  # SUCCESS
                                result["robot_safe"] = True
                                result["actions_taken"].append("机器人已移动到安全位姿")
                            else:
                                result["warnings"].append(f"MoveGroup失败: 错误代码 {move_result.result.error_code.val if move_result else '未知'}")
                        else:
                            result["warnings"].append("MoveGroup执行超时")
                    else:
                        result["warnings"].append("MoveGroup目标被拒绝")
                else:
                    result["warnings"].append("MoveGroup目标提交超时")
            else:
                result["warnings"].append("MoveGroup action server不可用")
                
        except Exception as e:
            result["warnings"].append(f"安全位姿移动失败: {str(e)}")
        
        # 步骤3: 重置夹爪到打开状态
        try:
            gripper_success = set_gripper_close_ratio(0.0, timeout_sec=3.0)  # 完全打开
            if gripper_success:
                result["actions_taken"].append("夹爪已打开")
            else:
                result["warnings"].append("夹爪打开失败")
        except Exception as e:
            result["warnings"].append(f"夹爪重置失败: {str(e)}")
        
        # 步骤4: 重置cup_pose参数为无效状态
        try:
            reset_params = {'cup_pose.valid': False}
            param_success = _set_params('/execute_pour_server', reset_params, timeout_sec=2.0)
            if param_success:
                result["actions_taken"].append("杯子位姿参数已重置")
            else:
                result["warnings"].append("杯子位姿参数重置失败")
        except Exception as e:
            result["warnings"].append(f"参数重置失败: {str(e)}")
        
        # 判断整体成功
        critical_actions = len([a for a in result["actions_taken"] if "机器人" in a or "夹爪" in a])
        result["success"] = critical_actions > 0 or len(result["actions_taken"]) > 2
        
        if result["success"]:
            result["actions_taken"].append("中止和重置操作成功完成")
        else:
            result["actions_taken"].append("中止操作完成，但有警告 - 建议手动检查")
            
    except Exception as e:
        result["success"] = False
        result["warnings"].append(f"中止操作过程中发生严重错误: {str(e)}")
    
    finally:
        node.destroy_node()
        _shutdown_rclpy_if(created)
    
    return result


# 可选：简单 CLI 骨架，便于手工测试
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')

    sp1 = sub.add_parser('execute')
    # 使用合并后的默认参数
    sp1.add_argument('--start', type=float, default=POUR_DEFAULTS['tilt_start_deg'])
    sp1.add_argument('--end', type=float, default=POUR_DEFAULTS['tilt_end_deg'])
    sp1.add_argument('--speed', type=float, default=POUR_DEFAULTS['tilt_speed_deg_s'])
    sp1.add_argument('--hold', type=float, default=POUR_DEFAULTS['pour_hold_sec'])
    sp1.add_argument('--lift', type=float, default=POUR_DEFAULTS['lift_height'])
    sp1.add_argument('--amin', type=float, default=POUR_DEFAULTS['approach_min'])
    sp1.add_argument('--amax', type=float, default=POUR_DEFAULTS['approach_max'])
    sp1.add_argument('--plan-only', action='store_true')
    sp1.add_argument('--target-id', type=str, default=POUR_DEFAULTS['target_id'])
    sp1.add_argument('--timeout', type=float, default=180.0)

    sp2 = sub.add_parser('set-cup')
    sp2.add_argument('--x', type=float, required=True)
    sp2.add_argument('--y', type=float, required=True)
    sp2.add_argument('--z', type=float, required=True)
    sp2.add_argument('--qx', type=float)
    sp2.add_argument('--qy', type=float)
    sp2.add_argument('--qz', type=float)
    sp2.add_argument('--qw', type=float)
    sp2.add_argument('--valid', type=int, default=1)

    sp3 = sub.add_parser('set-gripper')
    sp3.add_argument('--ratio', type=float, required=True)
    
    # 新增：任务状态检查工具
    sp4 = sub.add_parser('get-state')
    sp4.add_argument('--timeout', type=float, default=5.0)
    
    # 新增：紧急中止工具
    sp5 = sub.add_parser('abort')
    sp5.add_argument('--reason', type=str, default='Manual abort from CLI')
    sp5.add_argument('--timeout', type=float, default=30.0)

    args = ap.parse_args()

    if args.cmd == 'execute':
        res = execute_pour(dict(
            tilt_start_deg=args.start,
            tilt_end_deg=args.end,
            tilt_speed_deg_s=args.speed,
            pour_hold_sec=args.hold,
            lift_height=args.lift,
            approach_min=args.amin,
            approach_max=args.amax,
            plan_only=args.plan_only,
            target_id=args.target_id,
        ), timeout_sec=args.timeout)
        import json
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == 'set-cup':
        ok = set_cup_pose(args.x, args.y, args.z, args.qx, args.qy, args.qz, args.qw, bool(args.valid))
        print({'ok': ok})
    elif args.cmd == 'set-gripper':
        ok = set_gripper_close_ratio(args.ratio)
        print({'ok': ok})
    elif args.cmd == 'get-state':
        result = get_task_state(timeout_sec=args.timeout)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.cmd == 'abort':
        result = abort_and_reset(reason=args.reason, timeout_sec=args.timeout)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        ap.print_help() 