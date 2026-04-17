"""
Debug和监控工具
"""

from typing import Optional
import json


def print_stats(action_name: Optional[str] = None):
    """打印动作统计"""
    from .action_library import get_action_library
    
    lib = get_action_library()
    stats = lib.get_stats(action_name)
    
    if action_name:
        print(f"\n📊 {action_name} Statistics:")
        print(f"  Total executions: {stats.get('total_executions', 0)}")
        print(f"  Successful executions: {stats.get('successful_executions', 0)}")
        print(f"  Success rate: {stats.get('success_rate', 0):.1%}")
        print(f"  Average duration: {stats.get('average_duration_sec', 0):.2f}s")
    else:
        print("\n📊 All Actions Statistics:")
        for action, stat in stats.items():
            print(f"\n  {action}:")
            print(f"    Total: {stat['total_executions']}")
            print(f"    Success rate: {stat['success_rate']:.1%}")
            print(f"    Avg duration: {stat['average_duration_sec']:.2f}s")


def print_history(action_name: Optional[str] = None, limit: int = 20):
    """打印执行历史"""
    from .action_library import get_action_library
    
    lib = get_action_library()
    history = lib.get_history(limit=1000)  # 先获取全部
    
    # 过滤特定动作
    if action_name:
        history = [log for log in history if log['action_name'] == action_name]
    
    # 限制数量
    history = history[-limit:]
    
    print(f"\n📜 Execution History (最近{len(history)}条):")
    for log in history:
        status_emoji = "✅" if log['success'] else "❌"
        print(f"  {status_emoji} {log['action_name']}: {log['duration_sec']:.2f}s")
        if log['error_msg']:
            print(f"     ⚠️  {log['error_msg']}")


def export_debug_report(filepath: str = "debug_report.json"):
    """导出完整的调试报告"""
    from .action_library import get_action_library
    
    lib = get_action_library()
    lib.debug_export(filepath)
    print(f"✅ 调试报告已导出到: {filepath}")


def interactive_test():
    """交互式测试工具"""
    from .action_library import get_action_library
    
    lib = get_action_library()
    
    actions = lib.get_actions()
    print("\n🧪 Interactive Action Test")
    print("Available actions:")
    for i, action in enumerate(actions, 1):
        print(f"  {i}. {action}")
    
    try:
        choice = input("\nSelect action (number): ")
        action_idx = int(choice) - 1
        if action_idx < 0 or action_idx >= len(actions):
            print("Invalid choice")
            return
        
        action_name = actions[action_idx]
    except (ValueError, IndexError):
        print("Invalid choice")
        return
    
    object_id = input("Object ID (press enter for default): ").strip()
    
    # 获取参数
    params_str = input(f"Additional params as JSON (press enter to skip): ")
    params = {}
    if params_str.strip():
        try:
            params = json.loads(params_str)
        except:
            print("Invalid JSON, using empty params")
            params = {}
    
    # 定义反馈回调
    def feedback(msg: str):
        print(f"  💬 {msg}")
    
    # 执行
    print(f"\n🔧 Executing {action_name}...")
    result = lib.execute(
        action_name, 
        object_id=object_id or None,
        params=params,
        feedback_callback=feedback
    )
    
    print(f"\n{result}")
    print(f"\nDetails:")
    print(f"  Success: {result.success}")
    print(f"  Duration: {result.duration_sec:.2f}s")
    print(f"  Error code: {result.error_code}")
    print(f"  Solutions: {result.num_solutions}")
    
    if result.error_msg:
        print(f"  Error: {result.error_msg}")
    
    if result.stage_feedback:
        print(f"\n  Stage Feedback:")
        for fb in result.stage_feedback:
            print(f"    - {fb}")


def show_quick_stats():
    """显示快速统计摘要"""
    from .action_library import get_action_library
    
    lib = get_action_library()
    stats = lib.get_stats()
    
    print("\n" + "="*60)
    print("MTC Action Library - Quick Stats")
    print("="*60)
    
    for action_name, stat in stats.items():
        success_rate = stat.get('success_rate', 0)
        total = stat.get('total_executions', 0)
        avg_time = stat.get('average_duration_sec', 0)
        
        # 状态表情
        if success_rate >= 0.9:
            status = "🟢"
        elif success_rate >= 0.7:
            status = "🟡"
        else:
            status = "🔴"
        
        print(f"{status} {action_name:15s} | Exec: {total:3d} | Success: {success_rate:5.1%} | Avg: {avg_time:5.2f}s")
    
    print("="*60)








