"""
MTC Action Library - Python Interface
为Agent提供易用的Python接口
"""

import rclpy
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
import json

try:
    from ._mtc_action_library_core import (
        ActionLibrary as _ActionLibrary,
        ActionParams as _ActionParams,
        ActionResult as _ActionResult
    )
except ImportError:
    # 如果导入失败，提供占位符
    print("Warning: Could not import C++ bindings. Please build mtc_action_library_py package.")
    _ActionLibrary = None
    _ActionParams = None
    _ActionResult = None

@dataclass
class ActionResult:
    """Python友好的结果类"""
    success: bool
    duration_sec: float
    error_msg: str = ""
    error_code: int = 0
    stage_feedback: List[str] = None
    num_solutions: int = 0
    
    def __post_init__(self):
        if self.stage_feedback is None:
            self.stage_feedback = []
    
    def __str__(self):
        emoji = "✅" if self.success else "❌"
        return f"{emoji} {self.duration_sec:.2f}s"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ActionLibrary:
    """Agent友好的动作库接口"""
    
    def __init__(self, node_name: str = "action_library_node"):
        if _ActionLibrary is None:
            raise RuntimeError("C++ bindings not available. Please build mtc_action_library_py package.")
        
        # 确保rclpy已初始化（C++侧的rclcpp会检查）
        if not rclpy.ok():
            rclpy.init()
        
        # C++侧会创建自己的rclcpp节点
        self._lib = _ActionLibrary(node_name)
        
        print(f"✅ Action Library initialized")
        actions = self.get_actions()
        print(f"📋 Available actions: {', '.join(actions)}")
    
    def execute(self, 
                action_name: str,
                object_id: Optional[str] = None,
                feedback_callback: Optional[Callable[[str], None]] = None,
                **kwargs) -> ActionResult:
        """
        执行动作（Agent友好接口）
        
        Args:
            action_name: pick, place, move_to_pour, return_home
            object_id: 目标对象ID
            feedback_callback: 反馈回调函数
            **kwargs: 参数配置
                - plan_only: 仅规划不执行（默认False）
                - max_solutions: 最多找多少个解（默认1）
                - velocity_scaling: 速度缩放（默认0.3）
                - acceleration_scaling: 加速度缩放（默认0.5）
                - max_ik_solutions: IK最多解数（默认2）
                - min_solution_distance: IK解之间最小距离（默认0.5）
                - ik_timeout: IK超时（默认8.0）
                - cartesian_step_size: 笛卡尔步长（默认0.008）
                - cartesian_jump_threshold: 跳跃阈值（默认0.0）
                - connect_timeout: Connect超时（默认15.0）
                - planner_timeout: 规划器超时（默认3.0）
                - 其他numeric/string参数通过numeric_params传递
        
        Returns:
            ActionResult with debug information
        """
        # 构建参数
        cpp_params = _ActionParams()
        
        # 基础参数
        if object_id:
            cpp_params.object_id = object_id
        cpp_params.plan_only = kwargs.get('plan_only', False)
        
        # Task级别参数（使用mtc_tutorial默认值）
        cpp_params.max_solutions = kwargs.get('max_solutions', 1)
        
        # Planner级别参数（使用mtc_tutorial默认值）
        cpp_params.planner_timeout = kwargs.get('planner_timeout', 3.0)
        cpp_params.velocity_scaling = kwargs.get('velocity_scaling', 0.3)
        cpp_params.acceleration_scaling = kwargs.get('acceleration_scaling', 0.5)
        
        # IK级别参数（使用mtc_tutorial默认值）
        cpp_params.max_ik_solutions = kwargs.get('max_ik_solutions', 2)
        cpp_params.min_solution_distance = kwargs.get('min_solution_distance', 0.5)
        cpp_params.ik_timeout = kwargs.get('ik_timeout', 8.0)
        
        # Cartesian级别参数（使用mtc_tutorial默认值）
        cpp_params.cartesian_step_size = kwargs.get('cartesian_step_size', 0.008)
        cpp_params.cartesian_jump_threshold = kwargs.get('cartesian_jump_threshold', 0.0)
        
        # Stage级别参数（使用mtc_tutorial默认值）
        cpp_params.connect_timeout = kwargs.get('connect_timeout', 15.0)
        
        # 其他参数通过numeric_params/string_params传递
        # 注意：pybind11 对 STL map 的 def_readwrite 往往是值语义，
        # 不能依赖 `cpp_params.numeric_params[key] = ...` 这种原地修改。
        # 先构造本地 dict，再一次性回写到 C++ 成员，避免参数丢失。
        known_params = {'plan_only', 'max_solutions', 'planner_timeout', 'velocity_scaling', 
                       'acceleration_scaling', 'max_ik_solutions', 'min_solution_distance', 
                       'ik_timeout', 'cartesian_step_size', 'cartesian_jump_threshold', 
                       'connect_timeout'}

        numeric_params = {}
        string_params = {}
        for key, value in kwargs.items():
            if key not in known_params:
                if isinstance(value, (int, float)):
                    numeric_params[key] = float(value)
                else:
                    string_params[key] = str(value)
        cpp_params.numeric_params = numeric_params
        cpp_params.string_params = string_params
        
        # 执行
        cpp_result = self._lib.execute(action_name, cpp_params, feedback_callback)
        
        # 转换为Python友好格式
        return ActionResult(
            success=cpp_result.success,
            duration_sec=cpp_result.duration_sec,
            error_msg=cpp_result.error_msg,
            error_code=cpp_result.error_code,
            stage_feedback=list(cpp_result.stage_feedback),
            num_solutions=cpp_result.num_solutions
        )
    
    def get_actions(self) -> List[str]:
        """获取所有可用动作"""
        return self._lib.get_action_list()
    
    def get_stats(self, action_name: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        if action_name:
            stats = self._lib.get_stats(action_name)
            return {
                "action_name": stats.action_name,
                "total_executions": stats.total_executions,
                "successful_executions": stats.successful_executions,
                "total_duration_sec": stats.total_duration_sec,
                "average_duration_sec": stats.average_duration_sec,
                "success_rate": stats.success_rate
            }
        else:
            all_stats = self._lib.get_all_stats()
            return {
                name: {
                    "total_executions": stat.total_executions,
                    "successful_executions": stat.successful_executions,
                    "success_rate": stat.success_rate,
                    "average_duration_sec": stat.average_duration_sec
                }
                for name, stat in all_stats.items()
            }
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取执行历史"""
        history = self._lib.get_history(limit)
        return [
            {
                "action_name": log.action_name,
                "success": log.success,
                "duration_sec": log.duration_sec,
                "error_msg": log.error_msg
            }
            for log in history
        ]
    
    def debug_export(self, filepath: str = "debug_report.json"):
        """导出debug报告"""
        self._lib.export_debug_report(filepath)
        print(f"📊 Debug report exported to {filepath}")
    
    def clear_history(self):
        """清除执行历史"""
        self._lib.clear_history()
    
    def reset_stats(self):
        """重置统计信息"""
        self._lib.reset_all_stats()

# 全局单例
_global_lib: Optional[ActionLibrary] = None

def get_action_library() -> ActionLibrary:
    """获取全局动作库实例"""
    global _global_lib
    if _global_lib is None:
        _global_lib = ActionLibrary()
    return _global_lib

