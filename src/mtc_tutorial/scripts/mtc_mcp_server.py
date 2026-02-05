#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 确保可以导入同目录下的工具脚本
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.append(str(_THIS_DIR))

try:
    # 需要安装：pip install "mcp[stdio]"
    from mcp.server.fastmcp import FastMCP
except Exception as e:
    sys.stderr.write("[mtc_mcp_server] Missing MCP SDK. Please install: pip install 'mcp[stdio]'\n")
    raise

import ros_client_tools as tools

server = FastMCP("mtc_mcp_server")


# @server.tool()
# async def execute_pour(params: Dict[str, Any],
#                        action_name: str = 'execute_pour',
#                        timeout_sec: float = 180.0,
#                        cancel_after: Optional[float] = None,
#                        # 杯子位姿参数（重构后：仅用于位姿更新，不再负责场景构建）
#                        cup_x: Optional[float] = None,
#                        cup_y: Optional[float] = None,
#                        cup_z: Optional[float] = None,
#                        cup_qx: Optional[float] = None,
#                        cup_qy: Optional[float] = None,
#                        cup_qz: Optional[float] = None,
#                        cup_qw: Optional[float] = None) -> Dict[str, Any]:
#     """执行一次倒水动作 - 重构版本（职责分离：仅负责任务规划和执行）
#     
#     重构说明：
#     - 场景构建职责已移至setup_planning_scene工具
#     - 执行前会自动检查cup对象是否存在
#     - 如果cup对象不存在，将返回错误并提示先运行setup_planning_scene
#     
#     Args:
#         params: 倾倒参数字典，包含：
#             - tilt_start_deg: 起始倾斜角度 (默认: 45.0)
#             - tilt_end_deg: 结束倾斜角度 (默认: 120.0)  
#             - tilt_speed_deg_s: 倾斜速度 (默认: 25.0)
#             - pour_hold_sec: 倾倒保持时间 (默认: 2.0)
#             - lift_height: 抬升高度 (默认: 0.12)
#             - approach_min: 接近最小距离 (默认: 0.05)
#             - approach_max: 接近最大距离 (默认: 0.15)
#             - plan_only: 仅规划不执行 (默认: False)
#             - target_id: 目标ID (默认: "")
#             - update_cup_pose_first: 是否在执行前更新杯子位姿 (默认: False)
#         action_name: Action服务器名称
#         timeout_sec: 执行超时时间
#         cancel_after: 自动取消时间（可选）
#         cup_x, cup_y, cup_z: 杯子位置坐标（仅在update_cup_pose_first=True时使用）
#         cup_qx, cup_qy, cup_qz, cup_qw: 杯子方向四元数（可选）
#         
#     Returns:
#         执行结果字典，包含：
#         - ok/success: 执行状态
#         - status: 详细状态
#         - duration_sec: 执行时长
#         - error: 错误信息
#         - params: 实际使用的参数
#         - cup_pose_updated: 杯子位姿是否被更新
#         - object_check: 对象存在检查结果
#         
#     使用流程：
#     1. 首先运行setup_planning_scene构建场景
#     2. 然后运行execute_pour执行任务（已禁用，避免服务器冲突）
#     3. 可选：使用update_cup_pose更新杯子位置
#         
#     注意：此工具已禁用以避免与现有服务器冲突。请使用 move_to_pour_position 的 pour_execute 功能代替。
#     """
#     # 将杯子位姿参数合并到params中（仅用于位姿更新）
#     if cup_x is not None and cup_y is not None and cup_z is not None:
#         params = {**params,
#                   'cup_x': cup_x,
#                   'cup_y': cup_y, 
#                   'cup_z': cup_z,
#                   'update_cup_pose_first': True}  # 启用位姿更新
#         if all(q is not None for q in [cup_qx, cup_qy, cup_qz, cup_qw]):
#             params.update({
#                 'cup_qx': cup_qx,
#                 'cup_qy': cup_qy,
#                 'cup_qz': cup_qz,
#                 'cup_qw': cup_qw
#             })
#     
#     return tools.execute_pour(params, action_name=action_name, timeout_sec=timeout_sec, cancel_after=cancel_after)


@server.tool()
async def set_cup_pose(x: float, y: float, z: float, qx: Optional[float] = None, qy: Optional[float] = None, qz: Optional[float] = None, qw: Optional[float] = None, valid: bool = True,server_node: str = '/execute_pour_server',timeout_sec: float = 5.0) -> Dict[str, Any]:
    """设置杯子的位姿参数"""
    ok = tools.set_cup_pose(x, y, z, qx=qx, qy=qy, qz=qz, qw=qw, valid=valid,server_node=server_node, timeout_sec=timeout_sec)
    return {"ok": bool(ok)}


@server.tool()
async def set_gripper_close_ratio(ratio: float,server_node: str = '/execute_pour_server',timeout_sec: float = 5.0) -> Dict[str, Any]:
    """设置夹爪闭合比例 (0.0-1.0)"""
    ok = tools.set_gripper_close_ratio(ratio, server_node=server_node, timeout_sec=timeout_sec)
    return {"ok": bool(ok)}


# =============== 场景构建和管理工具 ===============

@server.tool()
async def setup_planning_scene(
                               detection_result: Optional[Dict[str, Any]] = None,
                               only_cup: bool = True,
                               id_prefix: str = 'object',
                               timeout_sec: float = 10.0,
                               # 兼容旧输入（无需时可忽略）
                               detected_objects: Optional[Dict[str, Any]] = None,
                               include_cup: bool = True,
                               cup_x: float = 0.0, cup_y: float = -0.4, cup_z: float = 0.13,
                               cup_qx: Optional[float] = None, cup_qy: Optional[float] = None,
                               cup_qz: Optional[float] = None, cup_qw: Optional[float] = 1.0,
                               cup_height: float = 0.1, cup_radius: float = 0.02,
                               add_no_go_wall: bool = False,  # 默认禁用虚拟墙
                               ) -> Dict[str, Any]:
    """设置完整的规划场景，包括桌面和基于检测结果的杯子对象

    优先使用 detection_result（来自检测节点的 DetectionResult）。
    仅生成 object 数量、ID 与位置，姿态固定为 (0,0,0,1)，尺寸使用默认 height/radius。
    若未提供检测结果，可用 detected_objects 或回退到 include_cup + 默认位置。
    """
    return tools.setup_planning_scene(
        detection_result=detection_result,
        only_cup=only_cup,
        id_prefix=id_prefix,
        timeout_sec=timeout_sec,
        detected_objects=detected_objects,
        include_cup=include_cup,
        cup_x=cup_x, cup_y=cup_y, cup_z=cup_z,
        cup_qx=cup_qx, cup_qy=cup_qy, cup_qz=cup_qz, cup_qw=cup_qw,
        cup_height=cup_height, cup_radius=cup_radius,
        add_no_go_wall=add_no_go_wall,  # 传递参数
    )


@server.tool()
async def check_object_exists(object_id: str = "object", timeout_sec: float = 5.0) -> Dict[str, Any]:
    """检查指定的碰撞对象是否存在于规划场景中

    Args:
        object_id: 要检查的对象ID（默认"object"，即杯子）
        timeout_sec: 超时时间
    
    Returns:
        详细的对象存在状态，包括：
        - ok: 是否成功执行检查
        - status: 检查状态
        - object_exists: 对象是否存在（布尔值）
        - object_id: 被检查的对象ID
        - known_objects: 场景中所有已知对象的列表
        - msg: 详细消息
    
    这个工具在execute_pour执行前用于验证cup对象是否正确加载，
    确保任务有正确的目标对象可以操作。
    """
    return tools.check_object_exists(object_id=object_id, timeout_sec=timeout_sec)


@server.tool() 
async def update_cup_pose(cup_x: float, cup_y: float, cup_z: float,
                          cup_qx: Optional[float] = None, cup_qy: Optional[float] = None,
                          cup_qz: Optional[float] = None, cup_qw: Optional[float] = 1.0,
                          cup_height: float = 0.1, cup_radius: float = 0.02,
                          timeout_sec: float = 5.0) -> Dict[str, Any]:
    """动态更新杯子对象的位姿（无需重建整个场景）

    Args:
        cup_x, cup_y, cup_z: 新的杯子位置坐标
        cup_qx, cup_qy, cup_qz, cup_qw: 新的杯子方向四元数（可选）
        cup_height: 杯子高度（米）
        cup_radius: 杯子半径（米）
        timeout_sec: 超时时间

    Returns:
        更新结果，包括：
        - ok: 是否成功
        - status: 更新状态
        - cup_position/orientation: 新的杯子位姿
        - msg: 详细消息

    这个工具允许在不重建整个场景的情况下更新杯子位置，
    比setup_planning_scene更高效，适用于杯子位置微调。

    注意:杯子对象必须已存在(通过setup_planning_scene创建)。
    """
    return tools.update_cup_pose(
        cup_x=cup_x, cup_y=cup_y, cup_z=cup_z,
        cup_qx=cup_qx, cup_qy=cup_qy, cup_qz=cup_qz, cup_qw=cup_qw,
        cup_height=cup_height, cup_radius=cup_radius,
        timeout_sec=timeout_sec
    )


# =============== 模块化任务执行工具 ===============

@server.tool()
async def pick_container(source_pose: Dict[str, float],
                         grasp_hint: Optional[Dict[str, Any]] = None,
                         object_id: str = "object",
                         plan_only: bool = False,
                         timeout_sec: float = 180.0) -> Dict[str, Any]:
    """抓取容器 - 独立的抓取任务（拆分版本）
    
    这个工具专门负责抓取阶段，包括：
    1. 获取当前状态
    2. 打开夹爪
    3. 移动到抓取位置
    4. 执行抓取序列：
       - 接近/上方安全高度 + 垂直下降
       - 生成抓取姿态
       - 允许碰撞
       - 微插入
       - 关闭夹爪
       - 附着对象
       - 抬升容器
    
    Args:
        source_pose: 源位姿字典，至少包含 {"x": float, "y": float, "z": float}
                     可选: {"qx": float, "qy": float, "qz": float, "qw": float}
        grasp_hint: 抓取提示，可选参数包括：
            - approach_min/max/lift_height
            - safe_approach_height: 安全上方高度（米）
            - use_back_constraint: 是否启用“后方约束”限制路径（默认True）
            - back_region_center_y/back_region_size_{x,y,z}: 约束盒参数（米）
        object_id: 目标对象ID（默认"object"，即杯子）
        plan_only: 仅规划不执行（默认False）
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典，包含：
        - ok/success: 执行状态
        - status: 详细状态
        - duration_sec: 执行时长
        - error: 错误信息
        - params: 实际使用的参数
        - task_name: 任务名称
        
    使用示例：
    {
        "tool": "pick_container",
        "arguments": {
            "source_pose": {"x": 0.0, "y": -0.4, "z": 0.13},
            "grasp_hint": {"approach_min": 0.05, "approach_max": 0.15, "lift_height": 0.12,
                             "safe_approach_height": 0.10,
                             "use_back_constraint": true}
        }
    }
    """
    return tools.pick_container(
        source_pose=source_pose,
        grasp_hint=grasp_hint,
        object_id=object_id,
        plan_only=plan_only,
        timeout_sec=timeout_sec
    )


# @server.tool()
# async def pour_to_target(target_pose: Optional[Dict[str, float]] = None,
#                          tilt_deg: Dict[str, float] = {"start": 45.0, "end": 120.0},
#                          speed: float = 25.0,
#                          stop_condition: Dict[str, float] = {"hold_time": 2.0},
#                          move_distance: Optional[Dict[str, float]] = None,
#                          plan_only: bool = False,
#                          timeout_sec: float = 180.0) -> Dict[str, Any]:
#     """执行倾倒动作到目标位置 - 独立的倾倒任务（拆分版本）
    
#     这个工具专门负责倾倒阶段，包括：
#     1. 获取当前状态（假设已抓取容器）
#     2. 移动到倾倒位置
#     3. 执行倾倒序列：
#        - 倾斜到开始角度
#        - 倾斜到结束角度
#        - 保持倾倒位置
#        - 从倾倒位置返回
    
#     Args:
#         target_pose: 目标倾倒位置（可选，将使用相对移动）
#         tilt_deg: 倾斜角度范围 {"start": float, "end": float}
#         speed: 倾斜速度（度/秒）
#         stop_condition: 停止条件 {"hold_time": float}
#         move_distance: 移动到倾倒位置的距离范围 {"min": float, "max": float}
#         plan_only: 仅规划不执行
#         timeout_sec: 超时时间
        
#     Returns:
#         执行结果字典，包含任务执行状态和详细信息
        
#     使用示例：
#     {
#         "tool": "pour_to_target",
#         "arguments": {
#             "tilt_deg": {"start": 45, "end": 120},
#             "speed": 25.0,
#             "stop_condition": {"hold_time": 3.0}
#         }
#     }
    
#     注意：此工具假设容器已经被抓取，需要先运行pick_container工具。
#     """
#     return tools.pour_to_target(
#         target_pose=target_pose,
#         tilt_deg=tilt_deg,
#         speed=speed,
#         stop_condition=stop_condition,
#         move_distance=move_distance,
#         plan_only=plan_only,
#         timeout_sec=timeout_sec
#     )


@server.tool()
async def move_to_pour_position(x: Optional[float] = None,
                               y: Optional[float] = None, 
                               z: Optional[float] = None,
                               speed: float = 0.15,
                               timeout_sec: float = 60.0,
                               pour_execute: bool = True,
                               tilt_deg: Dict[str, float] = {"start": 15.0, "end": 140.0},
                               tilt_speed_deg_s: float = 25.0,
                               pour_hold_sec: float = 2.0,
                               execute_give: bool = False,
                               gripper_open_ratio: float = 1.0,
                               object_id: Optional[str] = None) -> Dict[str, Any]:
    """移动到指定的倾倒位置（保持当前抓取姿势）
    
    简化版本的移动工具，可通过 object_id 选中目标对象位置，或直接指定坐标。
    
    Args:
        x/y/z: 目标坐标（可选）。若提供 object_id，则会被对象位置覆盖；留空将按0.0转发。
        安全位置:x=0.07, y=-0.45, z=0.45
        speed: 移动速度比例（0.05-0.3，默认0.15）
        timeout_sec: 超时时间（默认60秒）
        pour_execute: 是否在到达后执行简单倾倒序列
        tilt_deg: 倾斜角度范围 {"start": float, "end": float}
        tilt_speed_deg_s: 倾倒速度（度/秒）
        pour_hold_sec: 倾倒保持时间（秒）
        execute_give: 是否在到达后执行递给用户的动作（打开夹爪）
        gripper_open_ratio: 夹爪打开比例（0.0-1.0，1.0表示完全打开）
        object_id: 若提供，则以该 object 的坐标作为目标
    
    Returns:
        执行结果字典，包含任务执行状态和详细信息
    """
    return tools.move_to_pour_position(
        x=0.0 if x is None else x,
        y=0.0 if y is None else y,
        z=0.0 if z is None else z,
        speed=max(0.05, min(0.3, speed)), timeout_sec=timeout_sec,
        pour_execute=pour_execute, tilt_deg=tilt_deg, tilt_speed_deg_s=tilt_speed_deg_s,
        pour_hold_sec=pour_hold_sec, execute_give=execute_give, 
        gripper_open_ratio=gripper_open_ratio, object_id=object_id
    )


@server.tool()
async def move_to_secure_place(secure_position: str = "default",
                               speed: float = 0.15,
                               timeout_sec: float = 60.0,
                               force_clear_params: bool = True) -> Dict[str, Any]:
    """移动机械手臂到安全位置，为下一步规划做准备
    
    这是一个专门的安全移动工具，会将机械手臂移动到预设的安全位置。
    与move_to_pour_position不同，此工具专注于安全移动，不执行任何额外操作。
    
    Args:
        secure_position: 安全位置类型，可选值：
            - "default": 默认安全位置 (x=0.07, y=-0.45, z=0.45)
            - "high": 高安全位置 (x=0.0, y=-0.5, z=0.5)  
            - "left": 左侧安全位置 (x=-0.2, y=-0.45, z=0.4)
            - "right": 右侧安全位置 (x=0.2, y=-0.45, z=0.4)
            - "center": 中心安全位置 (x=0.0, y=-0.4, z=0.35)
        speed: 移动速度比例（0.05-0.3，默认0.15）
        timeout_sec: 超时时间（默认60秒）
        force_clear_params: 是否强制清除之前的参数（推荐True）
    
    Returns:
        执行结果字典，包含：
        - ok/success: 执行状态
        - status: 详细状态  
        - coordinate_mode: "coordinates"（使用坐标模式）
        - secure_position_used: 使用的安全位置类型
        - target_coordinates: 实际使用的坐标
        - params_cleared: 是否清除了参数
    
    使用示例：
    {
        "tool": "move_to_secure_place",
        "arguments": {
            "secure_position": "default",
            "speed": 0.15
        }
    }
    
    特点：
    - 禁用所有额外功能（不倾倒，不递给用户）
    - 自动清除可能冲突的参数
    - 提供多个预设安全位置选择
    - 专门为下一步规划做准备
    """
    
    # 预设的安全位置坐标
    secure_positions = {
        "default": {"x": 0.07, "y": -0.45, "z": 0.45, "desc": "默认安全位置（稍微偏右）"},
        "high": {"x": 0.0, "y": -0.5, "z": 0.5, "desc": "高安全位置（最高点）"}, 
        "left": {"x": -0.2, "y": -0.45, "z": 0.4, "desc": "左侧安全位置"},
        "right": {"x": 0.2, "y": -0.45, "z": 0.4, "desc": "右侧安全位置"},
        "center": {"x": 0.0, "y": -0.4, "z": 0.35, "desc": "中心安全位置（适中高度）"}
    }
    
    # 验证安全位置参数
    if secure_position not in secure_positions:
        return {
            "ok": False,
            "error": f"无效的安全位置类型: {secure_position}",
            "available_positions": list(secure_positions.keys()),
            "status": "invalid_position"
        }
    
    # 获取目标坐标
    target_pos = secure_positions[secure_position]
    x, y, z = target_pos["x"], target_pos["y"], target_pos["z"]
    
    # 调用底层移动函数，使用安全的参数设置
    result = tools.move_to_pour_position(
        x=x, y=y, z=z,
        speed=max(0.05, min(0.3, speed)),
        timeout_sec=timeout_sec,
        pour_execute=False,      # 禁用倾倒
        execute_give=False,      # 禁用递给用户
        object_id=None,          # 不使用对象ID
        force_clear_params=force_clear_params  # 清除冲突参数
    )
    
    # 增强结果信息
    if isinstance(result, dict):
        result.update({
            "secure_position_used": secure_position,
            "secure_position_desc": target_pos["desc"],
            "target_coordinates": {"x": x, "y": y, "z": z},
            "params_cleared": force_clear_params,
            "tool_purpose": "安全移动，为下一步规划做准备"
        })
        
        # 如果成功，更新任务名称
        if result.get("ok") or result.get("success"):
            result["task_name"] = f"移动到安全位置({secure_position}): {target_pos['desc']}"
    
    return result


@server.tool()
async def place_container(target_pose: Optional[Dict[str, float]] = None,
                          object_id: str = "object",
                          return_to_origin: bool = True,
                          plan_only: bool = False,
                          timeout_sec: float = 180.0) -> Dict[str, Any]:
    """放置容器到目标位置 - 独立的放置任务（拆分版本）
    
    这个工具专门负责放置阶段，包括：
    1. 获取当前状态（假设正在抓取容器）
    2. 移动到放置位置
    3. 执行放置序列：
       - 生成放置姿态
       - 降低容器到放置位置
       - 打开夹爪释放容器
       - 禁止碰撞
       - 分离对象
       - 后退
    
    Args:
        target_pose: 目标放置位置（可选，仅需 x/y/z）
        object_id: 目标对象ID
        return_to_origin: 若为True，优先回到 object_id 的初始位置
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典，包含任务执行状态和详细信息
        
    使用示例：
    {
        "tool": "place_container",
        "arguments": {
            "target_pose": {"x": 0.0, "y": -0.45, "z": 0.18}
        }
    }
    
    注意：此工具假设容器已经被抓取，需要先运行pick_container工具。
    """
    return tools.place_container(
        target_pose=target_pose,
        object_id=object_id,
        return_to_origin=return_to_origin,
        plan_only=plan_only,
        timeout_sec=timeout_sec
    )


@server.tool()
async def return_to_home(target_joints: Optional[Dict[str, float]] = None,
                         plan_only: bool = False,
                         timeout_sec: float = 60.0) -> Dict[str, Any]:
    """返回初始/安全位置 - 独立的返回任务（拆分版本）
    
    这个工具专门负责机器人返回安全位置，包括：
    1. 获取当前状态
    2. 返回到指定的关节配置或"home"位置
    
    Args:
        target_joints: 目标关节配置（可选，使用"home"配置）
                       例如 {"joint1": 0.0, "joint2": 0.0, "joint3": 0.0, 
                             "joint4": 0.0, "joint5": 0.0, "joint6": 0.0}
        plan_only: 仅规划不执行
        timeout_sec: 超时时间
        
    Returns:
        执行结果字典，包含任务执行状态和详细信息
        
    使用示例：
    {
        "tool": "return_to_home",
        "arguments": {}
    }
    
    或者指定特定关节配置：
    {
        "tool": "return_to_home", 
        "arguments": {
            "target_joints": {"joint1": 0.0, "joint2": 0.0, "joint3": 0.0, 
                              "joint4": 0.0, "joint5": 0.0, "joint6": 0.0}
        }
    }
    """
    return tools.return_to_home(
        target_joints=target_joints,
        plan_only=plan_only,
        timeout_sec=timeout_sec
    )


# =============== Agent的辅助工具 ===============

@server.tool()
async def get_task_state(timeout_sec: float = 5.0) -> Dict[str, Any]:
    """获取当前任务状态 - Agent友好的系统状态检查工具
    
    Returns:
        详细的任务状态信息，包括：
        - stage: 当前阶段 ("idle", "planning", "executing", "completed", "error")
        - last_error: 最近的错误信息 
        - robot_pose: 机器人末端执行器位姿
        - gripper_state: 夹爪状态 ("open", "closed", "grasping")
        - action_status: Action服务器状态
        - system_ready: 系统是否准备好执行任务
        - timestamp: 状态检查时间戳
    
    这个工具帮助Agent了解当前系统状态，制定下一步决策。
    """
    return tools.get_task_state(timeout_sec=timeout_sec)


@server.tool()
async def abort_and_reset(reason: str = "Agent requested emergency stop",
                          safe_pose_joints: Optional[list] = None, 
                          timeout_sec: float = 30.0,
                          force_stop: bool = True) -> Dict[str, Any]:
    """紧急中止当前任务并重置到安全状态 - Agent友好的失败恢复工具
    
    Args:
        reason: 中止原因，用于日志记录和调试
        safe_pose_joints: 安全位姿的关节角度 (可选，默认使用预设安全姿态)
        timeout_sec: 操作超时时间
        force_stop: 是否强制停止（推荐设置为True，会尝试多种方式确保任务停止）
    
    Returns:
        详细的执行结果，包括：
        - success: 是否成功完成中止和重置
        - reason: 中止原因
        - actions_taken: 执行的具体动作列表
        - warnings: 警告信息
        - robot_safe: 机器人是否处于安全状态
        - timestamp: 操作时间戳
        - force_stop: 是否使用了强制停止模式
    
    这个工具在任务出现问题时提供紧急恢复能力，确保机器人和环境安全。
    改进版本能够：
    - 强制中断正在运行的倾倒任务（即使在MCP工具调用期间）
    - 将机器人移动到安全位姿
    - 重置夹爪状态
    - 清除无效的杯子位姿参数
    
    注意：虽然MCP是单线程的，但这个函数通过ROS直接与action服务器通信，
         可以在其他任务运行时提供一定的中止能力。
    """
    return tools.abort_and_reset(reason=reason, safe_pose_joints=safe_pose_joints, timeout_sec=timeout_sec, force_stop=force_stop)


if __name__ == "__main__":
    # 通过 STDIO 运行 MCP 服务器（显式指定 stdio 以兼容不同客户端）
    server.run(transport='stdio') 
