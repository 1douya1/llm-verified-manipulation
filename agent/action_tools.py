"""
Action Tools - 将MTC Action Library封装为LangChain Tools
为Agent提供可调用的机器人动作工具
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
import json
import os

# 导入场景管理器和动作库
from scene_manager import get_scene_manager
try:
    from mtc_action_library import get_action_library
    ACTION_LIB_AVAILABLE = True
except ImportError:
    print("⚠️ Warning: MTC Action Library not available")
    ACTION_LIB_AVAILABLE = False


# ==================== 全局实例 ====================

def _get_lib():
    """获取action library实例"""
    if not ACTION_LIB_AVAILABLE:
        raise RuntimeError("MTC Action Library is not available")
    return get_action_library()


def _get_scene():
    """获取scene manager实例"""
    return get_scene_manager()


def _effective_plan_only(plan_only: bool) -> bool:
    """Dry-run mode always plans without sending motion commands."""
    return plan_only or os.getenv("AGENT_DRY_RUN", "").lower() in ("1", "true", "yes")


def _mode_prefix(plan_only: bool) -> str:
    return "规划成功" if plan_only else "成功"


# ==================== 辅助工具 ====================

@tool
def get_scene_objects() -> str:
    """获取当前场景中的所有物体。
    
    当用户询问场景中有什么物体时使用此工具。
    
    Returns:
        场景中物体的描述字符串
        
    使用场景:
    - 用户问: "场景里有什么?"
    - 用户问: "有哪些杯子?"
    - 在执行动作前需要确认场景状态时
    """
    scene = _get_scene()
    objects = scene.get_objects()
    count = len(objects)
    
    if count == 0:
        return "当前场景中没有检测到物体。"
    elif count == 1:
        obj_id = objects[0]
        details = scene.get_object_details(obj_id)
        if details:
            return f"场景中有1个物体: {obj_id} (类别: {details['class_name']}, 置信度: {details['confidence']:.2f})"
        return f"场景中有1个物体: {obj_id}"
    else:
        obj_list = ", ".join(objects)
        return f"场景中有{count}个物体: {obj_list}"


@tool
def get_robot_status() -> str:
    """获取机器人当前状态。
    
    查询机器人是否正在抓取物体，以及上次执行的动作。
    
    Returns:
        机器人状态描述
        
    使用场景:
    - 用户问: "机器人在干什么?"
    - 用户问: "抓着什么?"
    - 需要了解当前状态以决定下一步动作时
    """
    scene = _get_scene()
    holding = scene.get_robot_holding()
    last_action = scene.get_last_action()
    
    if holding:
        status = f"机器人当前抓着: {holding}"
    else:
        status = "机器人没有抓取任何物体"
    
    if last_action:
        status += f" | 上次动作: {last_action}"
    
    return status


@tool
def ask_user_clarification(question: str, options: List[str]) -> str:
    """当参数不明确时询问用户。
    
    Args:
        question: 要问用户的问题
        options: 可选项列表
        
    Returns:
        用户选择的选项
        
    使用场景:
    - 用户说"抓杯子"但场景有多个物体
    - 用户说"倒水"但目标不明确
    - 任何需要用户澄清意图的情况
    """
    print(f"\n🤔 {question}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    
    while True:
        try:
            choice = input("请选择 (输入数字): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                selected = options[idx]
                print(f"✅ 您选择了: {selected}")
                return selected
            else:
                print(f"❌ 请输入1-{len(options)}之间的数字")
        except ValueError:
            print("❌ 请输入有效的数字")
        except KeyboardInterrupt:
            print("\n❌ 用户取消")
            return "取消"


# ==================== 机器人动作工具 ====================

@tool
def pick_object(object_id: Optional[str] = None, plan_only: bool = False) -> str:
    """抓取指定的物体。
    
    Args:
        object_id: 要抓取的物体ID (如 "object_1")。如果为None则使用默认位置。
        plan_only: 是否只规划不执行。默认False，真机模式下规划成功后直接执行。
        
    Returns:
        执行结果描述
        
    使用场景:
    - 用户说: "抓object_1" -> pick_object("object_1")
    - 用户说: "抓杯子"且场景只有一个物体 -> pick_object(该物体ID)
    - 用户说: "拿起那个杯子" -> 根据场景推断object_id
    
    注意:
    - 如果场景有多个物体且用户没有明确指定，应使用ask_user_clarification询问
    - 成功后会自动更新机器人状态
    """
    lib = _get_lib()
    scene = _get_scene()
    plan_only = _effective_plan_only(plan_only)
    
    # 执行pick动作
    try:
        result = lib.execute("pick", object_id=object_id, plan_only=plan_only)
        
        if result.success:
            # 更新场景状态
            if not plan_only:
                scene.update_robot_holding(object_id)
            scene.set_last_action("pick")
            
            obj_desc = object_id if object_id else "默认位置的物体"
            return f"✅ {_mode_prefix(plan_only)}抓取 {obj_desc}，耗时 {result.duration_sec:.2f}秒"
        else:
            error_msg = result.error_msg or "未知错误"
            return f"❌ 抓取失败: {error_msg}"
    
    except Exception as e:
        return f"❌ 执行pick时发生错误: {str(e)}"


@tool
def place_object(object_id: Optional[str] = None, return_to_origin: bool = True,
                 plan_only: bool = False) -> str:
    """放置当前抓取的物体。
    
    Args:
        object_id: 目标位置ID (通常是原物体的ID)。如果为None，使用当前抓取的物体ID。
        return_to_origin: 是否放回原位 (默认True)
        plan_only: 是否只规划不执行。默认False，真机模式下规划成功后直接执行。
        
    Returns:
        执行结果描述
        
    使用场景:
    - 用户说: "放下" -> place_object(当前抓取的物体ID)
    - 用户说: "放回去" -> place_object(return_to_origin=True)
    - 用户说: "把它放到object_2" -> place_object("object_2", return_to_origin=False)
    
    注意:
    - 必须先执行pick才能place
    - 成功后会自动清除机器人抓取状态
    """
    lib = _get_lib()
    scene = _get_scene()
    plan_only = _effective_plan_only(plan_only)
    
    # 检查是否正在抓取物体
    holding = scene.get_robot_holding()
    if not holding and not object_id:
        return "❌ 机器人没有抓取任何物体，无法执行放置动作。请先执行pick_object。"
    
    # 如果没有指定object_id，使用当前抓取的
    target_id = object_id if object_id else holding
    
    # 执行place动作
    try:
        params = {
            "return_to_origin": 1.0 if return_to_origin else 0.0,
            "plan_only": plan_only,
        }
        result = lib.execute("place", object_id=target_id, **params)
        
        if result.success:
            # 更新场景状态
            if not plan_only:
                scene.clear_robot_holding()
            scene.set_last_action("place")
            
            action_desc = "放回原位" if return_to_origin else f"放置到 {target_id}"
            return f"✅ {_mode_prefix(plan_only)}{action_desc}，耗时 {result.duration_sec:.2f}秒"
        else:
            error_msg = result.error_msg or "未知错误"
            return f"❌ 放置失败: {error_msg}"
    
    except Exception as e:
        return f"❌ 执行place时发生错误: {str(e)}"


@tool
def move_and_pour(target_object_id: Optional[str] = None, should_pour: bool = True, 
                  velocity_scaling: float = 0.15, plan_only: bool = False) -> str:
    """移动到目标位置并选择性地执行倒水动作。
    
    Args:
        target_object_id: 目标物体ID (如 "object_2")。如果为None，移动到默认倒水位置。
        should_pour: 是否执行倒水动作 (默认True)
        velocity_scaling: 速度缩放因子 0.05-0.3 (默认0.15)
        plan_only: 是否只规划不执行。默认False，真机模式下规划成功后直接执行。
        
    Returns:
        执行结果描述
        
    使用场景:
    - 用户说: "倒水给object_2" -> move_and_pour("object_2", should_pour=True)
    - 用户说: "移到倒水位置但不要倒" -> move_and_pour(should_pour=False)
    - 用户说: "把它倒给object_2" -> move_and_pour("object_2")
    
    注意:
    - 通常在pick之后、place之前调用
    - 这是完整倒水任务序列的核心步骤
    """
    lib = _get_lib()
    scene = _get_scene()
    plan_only = _effective_plan_only(plan_only)
    
    # 检查是否正在抓取物体
    holding = scene.get_robot_holding()
    warning = ""
    if not holding:
        warning = "⚠️ 警告: 机器人没有抓取物体，但仍会尝试执行移动动作\n"
    
    # 执行move_to_pour动作
    try:
        params = {
            "pour_execute": 1.0 if should_pour else 0.0,
            "velocity_scaling": velocity_scaling,
            "plan_only": plan_only,
        }
        result = lib.execute("move_to_pour", object_id=target_object_id, **params)
        
        if result.success:
            # 更新场景状态
            scene.set_last_action("move_to_pour")
            
            target_desc = target_object_id if target_object_id else "默认倒水位置"
            action_desc = "并执行倒水" if should_pour else "但未倒水"
            return f"{warning}✅ {_mode_prefix(plan_only)}移动到 {target_desc} {action_desc}，耗时 {result.duration_sec:.2f}秒"
        else:
            error_msg = result.error_msg or "未知错误"
            return f"❌ 移动/倒水失败: {error_msg}"
    
    except Exception as e:
        return f"❌ 执行move_and_pour时发生错误: {str(e)}"


@tool
def return_home(plan_only: bool = False) -> str:
    """将机器人手臂返回到安全的初始位置。
    
    Args:
        plan_only: 是否只规划不执行。默认False，真机模式下规划成功后直接执行。

    Returns:
        执行结果描述
        
    使用场景:
    - 用户说: "回到初始位置"
    - 用户说: "归位"
    - 完成所有任务后的最后一步
    
    注意:
    - 通常作为任务序列的最后一步
    - 确保机器人处于安全状态
    """
    lib = _get_lib()
    scene = _get_scene()
    plan_only = _effective_plan_only(plan_only)
    
    # 执行return_home动作
    try:
        result = lib.execute("return_home", plan_only=plan_only)
        
        if result.success:
            # 更新场景状态
            scene.set_last_action("return_home")
            
            return f"✅ {_mode_prefix(plan_only)}返回初始位置，耗时 {result.duration_sec:.2f}秒"
        else:
            error_msg = result.error_msg or "未知错误"
            return f"❌ 返回初始位置失败: {error_msg}"
    
    except Exception as e:
        return f"❌ 执行return_home时发生错误: {str(e)}"


@tool
def execute_full_pour_sequence(source_object_id: Optional[str] = None, 
                               target_object_id: Optional[str] = None,
                               plan_only: bool = False) -> str:
    """执行完整的倒水任务序列: pick → move_and_pour → place → return_home
    
    Args:
        source_object_id: 源物体ID (要抓取的杯子)
        target_object_id: 目标物体ID (倒水的目标)
        plan_only: 是否只规划不执行。默认False，真机模式下规划成功后直接执行。
        
    Returns:
        完整序列的执行结果
        
    使用场景:
    - 用户说: "把object_1的水倒给object_2" -> execute_full_pour_sequence("object_1", "object_2")
    - 用户说: "给我倒杯水" -> 根据场景推断参数后调用
    - 用户说: "完成倒水任务" -> 使用默认参数
    
    注意:
    - 这是一个复合动作，包含4个步骤
    - 任何一步失败都会停止后续步骤
    - 推荐用于完整的倒水任务
    """
    plan_only = _effective_plan_only(plan_only)
    results = []
    
    # Step 1: Pick
    pick_result = pick_object.invoke({"object_id": source_object_id, "plan_only": plan_only})
    results.append(f"1. 抓取: {pick_result}")
    if "❌" in pick_result:
        return "\n".join(results) + "\n\n⚠️ 序列在pick步骤失败，已停止"
    
    # Step 2: Move and Pour
    pour_result = move_and_pour.invoke({
        "target_object_id": target_object_id,
        "should_pour": True,
        "plan_only": plan_only,
    })
    results.append(f"2. 移动并倒水: {pour_result}")
    if "❌" in pour_result:
        return "\n".join(results) + "\n\n⚠️ 序列在move_and_pour步骤失败，已停止"
    
    # Step 3: Place
    place_result = place_object.invoke({
        "object_id": source_object_id,
        "return_to_origin": True,
        "plan_only": plan_only,
    })
    results.append(f"3. 放置: {place_result}")
    if "❌" in place_result:
        return "\n".join(results) + "\n\n⚠️ 序列在place步骤失败，已停止"
    
    # Step 4: Return Home
    home_result = return_home.invoke({"plan_only": plan_only})
    results.append(f"4. 返回初始位置: {home_result}")
    
    summary = "\n".join(results)
    if "❌" in home_result:
        return summary + "\n\n⚠️ 序列在return_home步骤失败"
    else:
        return summary + "\n\n🎉 完整倒水序列成功完成！"


# ==================== 工具列表导出 ====================

ALL_TOOLS = [
    # 查询工具
    get_scene_objects,
    get_robot_status,
    ask_user_clarification,
    
    # 单个动作
    pick_object,
    place_object,
    move_and_pour,
    return_home,
    
    # 复合动作
    execute_full_pour_sequence,
]


def get_tools() -> List:
    """获取所有可用的工具列表"""
    return ALL_TOOLS


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("Testing Action Tools...")
    
    # 测试场景查询
    print("\n=== 测试场景查询 ===")
    scene = _get_scene()
    scene.manually_add_objects(["object_1", "object_2"])
    
    result = get_scene_objects.invoke({})
    print(f"场景物体: {result}")
    
    result = get_robot_status.invoke({})
    print(f"机器人状态: {result}")
    
    print("\n✅ Action Tools test completed")
    print(f"共有 {len(ALL_TOOLS)} 个工具可用")
    for tool in ALL_TOOLS:
        print(f"  - {tool.name}: {tool.description[:50]}...")
