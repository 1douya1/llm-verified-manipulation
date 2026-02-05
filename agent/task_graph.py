import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import re

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# 导入 Action Library
try:
    from mtc_action_library import get_action_library, ActionResult, ActionLibrary
    ACTION_LIBRARY_AVAILABLE = True
except ImportError:
    print("⚠️ MTC Action Library not available. Please build and source the workspace.")
    ACTION_LIBRARY_AVAILABLE = False
    ActionLibrary = None
    ActionResult = None


@dataclass
class StepResult:
    step: str
    success: bool
    status: str
    error: str
    duration_sec: float
    raw: Any

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def _call_action_with_retry(
    lib: ActionLibrary,
    action_name: str,
    object_id: Optional[str],
    params: Dict[str, Any],
    step_name: str,
    reporter,
    feedback_callback
) -> ActionResult:
    """
    直接调用action library的重试机制
    保持与原有MCP模式相同的3次重试逻辑
    """
    # First attempt
    await _maybe_report(reporter, {
        "type": "tool_attempt", 
        "step": step_name, 
        "attempt": 1,
        "message": f"Starting {step_name} (attempt 1)",
        "params": _visible_params({"object_id": object_id, **params})
    })
    
    # 调用action library
    result1 = lib.execute(action_name, object_id=object_id, params=params, feedback_callback=feedback_callback)
    success1 = result1.success
    
    await _maybe_report(reporter, {
        "type": "tool_result", 
        "step": step_name, 
        "attempt": 1,
        "success": success1,
        "message": f"{step_name} attempt 1: {'success' if success1 else 'failed'}",
        "result": {"success": success1, "status": "succeeded" if success1 else "failed", "error": result1.error_msg}
    })
    
    if success1:
        return result1
    
    # First attempt failed, auto-retry
    await _maybe_report(reporter, {
        "type": "auto_retry", 
        "step": step_name, 
        "attempt": 2,
        "message": f"{step_name} failed, auto-retrying (attempt 2)"
    })
    
    result2 = lib.execute(action_name, object_id=object_id, params=params, feedback_callback=feedback_callback)
    success2 = result2.success
    
    await _maybe_report(reporter, {
        "type": "tool_result", 
        "step": step_name, 
        "attempt": 2,
        "success": success2,
        "message": f"{step_name} attempt 2: {'success' if success2 else 'failed'}",
        "result": {"success": success2, "status": "succeeded" if success2 else "failed", "error": result2.error_msg}
    })
    
    if success2:
        return result2
    
    # Both attempts failed, ask user
    await _maybe_report(reporter, {
        "type": "user_decision_needed", 
        "step": step_name,
        "message": f"{step_name} failed twice consecutively, user decision needed"
    })
    
    continue_exec = _ask_yes_no(f"{step_name} has failed twice. Continue with attempt 3?")
    
    if continue_exec:
        await _maybe_report(reporter, {
            "type": "user_approved_retry", 
            "step": step_name, 
            "attempt": 3,
            "message": f"User approved to continue, executing {step_name} (attempt 3)"
        })
        
        result3 = lib.execute(action_name, object_id=object_id, params=params, feedback_callback=feedback_callback)
        success3 = result3.success
        
        await _maybe_report(reporter, {
            "type": "tool_result", 
            "step": step_name, 
            "attempt": 3,
            "success": success3,
            "message": f"{step_name} attempt 3: {'success' if success3 else 'failed'}",
            "result": {"success": success3, "status": "succeeded" if success3 else "failed", "error": result3.error_msg}
        })
        
        return result3
    else:
        await _maybe_report(reporter, {
            "type": "user_skipped", 
            "step": step_name,
            "message": f"User chose to skip {step_name}"
        })
        
        # 返回一个失败的ActionResult
        if ActionResult:
            return ActionResult(
                success=False,
                duration_sec=0.0,
                error_msg="User chose to skip execution",
                error_code=-1,
                stage_feedback=[],
                num_solutions=0
            )
        else:
            # 如果ActionResult不可用，返回一个简单的dict（不应该发生，但作为后备）
            class FakeResult:
                success = False
                duration_sec = 0.0
                error_msg = "User chose to skip execution"
                error_code = -1
            return FakeResult()


def _ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(f"{prompt} (yes/no): ").strip().lower()
        if ans in ("y", "yes"): return True
        if ans in ("n", "no"): return False
        print("Please enter yes or no")


def _visible_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Filter parameters that are allowed to be displayed/passed to users (avoiding coordinates/velocity etc.)."""
    if not params:
        return {}
    allow_keys = {"object_id", "pour_execute", "return_to_origin", "plan_only", "velocity_scaling"}
    return {k: v for k, v in params.items() if k in allow_keys}


async def _maybe_report(reporter, event: Dict[str, Any]):
    if reporter is None:
        # 控制台精简打印
        msg = event.get("message") or ""
        prefix = f"[{event.get('type','event')}]"
        print(prefix, msg)
        return
    try:
        # 兼容同步/异步
        if asyncio.iscoroutinefunction(reporter):
            await reporter(event)
        else:
            reporter(event)
    except Exception:
        pass


def build_main_graph(reporter=None):
    """Build deterministic task graph: pick -> move_to_pour -> place -> return (with template selection and event reporting)."""
    
    # 检查Action Library是否可用
    if not ACTION_LIBRARY_AVAILABLE:
        raise RuntimeError("MTC Action Library is not available. Please build and source the workspace.")
    
    # 获取action library实例
    lib = get_action_library()

    def initial_state() -> Dict[str, Any]:
        return {
            "plan": ["pick", "move_to_pour", "place", "return"],
            "results": {},
            "events": [],
            # Parse results
            "object_id": None,            # Source cup
            "target_object_id": None,     # Target cup (optional)
            "do_pour": True,              # Whether to execute pouring
            "plan_template": "P2",       # P1/P2/P3
            "user_prompt": "",
            # Retry statistics
            "retry_counts": {},           # Record retry counts for each step
        }

    def _extract_object_ids(text: str) -> List[str]:
        return re.findall(r"object[_-]?\d+|object", text)

    async def resolve_and_choose_plan(state: Dict[str, Any]):
        text = (state.get("user_prompt") or "").strip().lower()
        ids = _extract_object_ids(text)

        src = ids[0] if ids else None
        dst = None

        # 尝试解析目的地：dst:xxx / to xxx / 给xxx
        m1 = re.search(r"dst[:：]\s*(object[_-]?\d+|object)", text)
        m2 = re.search(r"to\s+(object[_-]?\d+|object)", text)
        m3 = re.search(r"倒给|给\s*(object[_-]?\d+|object)", text)
        if m1:
            dst = m1.group(1)
        elif m2:
            dst = m2.group(1)
        elif m3:
            dst = m3.group(1)
        elif len(ids) >= 2:
            # 若出现两个ID，默认第一个为src，第二个为dst
            dst = ids[1]

        # Identify no-pour/safety mode
        no_pour = any(k in text for k in ["不倒水", "no pour", "nopour", "避险", "handover"])  # P3

        # Select template
        if no_pour:
            tpl = "P3"; do_pour = False
        elif dst:
            tpl = "P1"; do_pour = True
        else:
            tpl = "P2"; do_pour = True

        state["object_id"] = src
        state["target_object_id"] = dst
        state["do_pour"] = do_pour
        state["plan_template"] = tpl

        # 新增：执行计划预告
        steps_desc = []
        if src:
            steps_desc.append(f"1. Pick container from {src}")
        else:
            steps_desc.append("1. Pick container from default position")
        
        if dst:
            steps_desc.append(f"2. Move to {dst} and {'pour' if do_pour else 'approach without pouring'}")
        else:
            steps_desc.append(f"2. Move to pouring position and {'execute pouring' if do_pour else 'approach without pouring'}")
        
        steps_desc.append("3. Place container back to original position")
        steps_desc.append("4. Return robot arm to home position")
        
        plan_msg = f"🎯 Execution Plan ({tpl} template): " + " → ".join([s.split('. ', 1)[1] for s in steps_desc])
        
        await _maybe_report(reporter, {
            "type": "execution_plan",
            "message": plan_msg,
            "template": tpl,
            "steps": steps_desc,
            "estimated_duration": "~60-90 seconds"
        })

        # Event
        evt = {
            "type": "plan_selected",
            "message": f"Template={tpl} Source={src or 'unspecified'} Target={dst or 'default'} Pour={'yes' if do_pour else 'no'}",
            "template": tpl,
            "source": src,
            "target": dst,
            "do_pour": do_pour,
        }
        state["events"].append(evt)
        await _maybe_report(reporter, evt)
        return state

    async def do_pick(state: Dict[str, Any]):
        # 步骤开始提示
        src_info = state.get("object_id") or "default position"
        await _maybe_report(reporter, {
            "type": "step_starting",
            "step": "pick",
            "message": f"🔧 Starting Step 1: Pick container from {src_info}",
            "details": "Moving robot arm to grasp the container"
        })
        
        # 准备反馈回调
        def feedback_cb(msg: str):
            # 在异步环境中报告反馈（不等待）
            try:
                asyncio.create_task(_maybe_report(reporter, {
                    "type": "feedback",
                    "step": "pick",
                    "message": msg
                }))
            except:
                pass
        
        # 准备参数
        params = {}
        object_id = state.get("object_id")
        
        # 使用带重试的action library调用
        result = await _call_action_with_retry(
            lib, "pick", object_id, params, "pick", reporter, feedback_cb
        )
        
        sr = StepResult(
            step="pick",
            success=result.success,
            status="succeeded" if result.success else "failed",
            error=result.error_msg,
            duration_sec=result.duration_sec,
            raw=result,
        )
        state["results"]["pick"] = sr.to_dict()
        return state

    async def do_move_to_pour(state: Dict[str, Any]):
        # 步骤开始提示
        dst_info = state.get("target_object_id") or "pouring position"
        pour_action = "execute pouring" if state.get("do_pour", True) else "approach without pouring"
        await _maybe_report(reporter, {
            "type": "step_starting",
            "step": "move_to_pour",
            "message": f"🔧 Starting Step 2: Move to {dst_info} and {pour_action}",
            "details": "Moving to target position and performing pouring motion"
        })
        
        # 准备反馈回调
        def feedback_cb(msg: str):
            try:
                asyncio.create_task(_maybe_report(reporter, {
                    "type": "feedback",
                    "step": "move_to_pour",
                    "message": msg
                }))
            except:
                pass
        
        # 准备参数
        params = {
            "pour_execute": 1.0 if state.get("do_pour", True) else 0.0,
            "velocity_scaling": 0.15
        }
        object_id = state.get("target_object_id")
        
        # 使用带重试的action library调用
        result = await _call_action_with_retry(
            lib, "move_to_pour", object_id, params, "move_to_pour", reporter, feedback_cb
        )
        
        sr = StepResult(
            step="move_to_pour",
            success=result.success,
            status="succeeded" if result.success else "failed",
            error=result.error_msg,
            duration_sec=result.duration_sec,
            raw=result,
        )
        state["results"]["move_to_pour"] = sr.to_dict()
        return state

    async def do_place(state: Dict[str, Any]):
        # 步骤开始提示
        src_info = state.get("object_id") or "original"
        await _maybe_report(reporter, {
            "type": "step_starting",
            "step": "place",
            "message": f"🔧 Starting Step 3: Place container back to {src_info} position",
            "details": "Returning container to its original location"
        })
        
        # 准备反馈回调
        def feedback_cb(msg: str):
            try:
                asyncio.create_task(_maybe_report(reporter, {
                    "type": "feedback",
                    "step": "place",
                    "message": msg
                }))
            except:
                pass
        
        # 准备参数
        params = {"return_to_origin": 1.0}  # Action library expects float
        object_id = state.get("object_id")
        
        # 使用带重试的action library调用
        result = await _call_action_with_retry(
            lib, "place", object_id, params, "place", reporter, feedback_cb
        )
        
        sr = StepResult(
            step="place",
            success=result.success,
            status="succeeded" if result.success else "failed",
            error=result.error_msg,
            duration_sec=result.duration_sec,
            raw=result,
        )
        state["results"]["place"] = sr.to_dict()
        return state

    async def do_return(state: Dict[str, Any]):
        # 步骤开始提示
        await _maybe_report(reporter, {
            "type": "step_starting",
            "step": "return",
            "message": "🔧 Starting Step 4: Return robot arm to home position",
            "details": "Moving robot arm back to safe home position"
        })
        
        # 准备反馈回调
        def feedback_cb(msg: str):
            try:
                asyncio.create_task(_maybe_report(reporter, {
                    "type": "feedback",
                    "step": "return",
                    "message": msg
                }))
            except:
                pass
        
        # 准备参数
        params = {}
        
        # 使用带重试的action library调用
        result = await _call_action_with_retry(
            lib, "return_home", None, params, "return", reporter, feedback_cb
        )
        
        sr = StepResult(
            step="return",
            success=result.success,
            status="succeeded" if result.success else "failed",
            error=result.error_msg,
            duration_sec=result.duration_sec,
            raw=result,
        )
        state["results"]["return"] = sr.to_dict()
        return state

    graph = StateGraph(dict)

    # Add nodes (confirmation gates removed)
    graph.add_node("resolve_and_choose_plan", resolve_and_choose_plan)
    graph.add_node("do_pick", do_pick)
    graph.add_node("do_move_to_pour", do_move_to_pour)
    graph.add_node("do_place", do_place)
    graph.add_node("do_return", do_return)

    # Set flow (direct execution, no confirmation gates)
    graph.set_entry_point("resolve_and_choose_plan")
    graph.add_edge("resolve_and_choose_plan", "do_pick")
    graph.add_edge("do_pick", "do_move_to_pour")
    graph.add_edge("do_move_to_pour", "do_place")
    graph.add_edge("do_place", "do_return")
    graph.add_edge("do_return", END)

    memory = MemorySaver()
    app = graph.compile(checkpointer=memory)

    return app, memory, initial_state


async def run_main_sequence_cli(user_prompt: str = "", reporter=None) -> Dict[str, Any]:
    """运行主要序列（不再需要tools参数，内部直接使用action library）"""
    app, _memory, initial_state = build_main_graph(reporter=reporter)

    state = initial_state()
    state["user_prompt"] = user_prompt

    config = {"configurable": {"thread_id": "default"}}
    final_state = await app.ainvoke(state, config=config)

    print("\n=== Execution Results (Step by Step) ===")
    for step in ["pick", "move_to_pour", "place", "return"]:
        if step in final_state.get("results", {}):
            print(json.dumps(final_state["results"][step], ensure_ascii=False, indent=2))

    summary = {
        "template": final_state.get("plan_template"),
        "do_pour": final_state.get("do_pour"),
        "source": final_state.get("object_id"),
        "target": final_state.get("target_object_id"),
        "success": all(
            final_state["results"].get(s, {}).get("success", False)
            for s in ["pick", "move_to_pour", "place", "return"]
        ),
        "results": final_state.get("results", {}),
        "events": final_state.get("events", []),
    }

    print("\n=== Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return summary
