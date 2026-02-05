import asyncio, json, os, sys
from langchain_anthropic import ChatAnthropic

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()  # 从当前目录的 .env 文件加载环境变量
except ImportError:
    print("提示: 安装 python-dotenv 可以支持 .env 文件")
    print("运行: pip install python-dotenv")

# ==================== API Key 配置区域 ====================
# 从环境变量读取API Key（安全实践）
# 使用方式：
# 1. export ANTHROPIC_API_KEY="your-key"
# 2. 或创建 .env 文件，内容：ANTHROPIC_API_KEY=your-key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY:
    print("警告: 未找到 ANTHROPIC_API_KEY 环境变量")
    print("请使用以下任一方式设置:")
    print("  1. export ANTHROPIC_API_KEY='your-api-key'")
    print("  2. 创建 .env 文件，内容: ANTHROPIC_API_KEY=your-api-key")
# ========================================================

SYSTEM_PROMPT = """
You are a robot operation agent with direct access to an embedded Action Library.

## System Architecture

Your workflow is controlled by a deterministic Task Graph:
pick → move_to_pour → place → return_home

You directly invoke the Action Library (Python/C++ embedded module), NOT external MCP tools.
The Action Library provides: pick, place, move_to_pour, return_home

Each action accepts:
- object_id (optional string): Target object identifier
- params (optional dict): Action-specific parameters
- Returns: ActionResult with success, duration, error_msg, etc.

## Available Actions

### 1. pick(object_id=None, params={})
Grasps the container from specified object or default position.

Parameters:
- object_id: "object", "object_1", "object_2", etc. (None = default)
- params: approach_height, grasp_offset, etc. (rarely needed)

Example:
```python
result = lib.execute("pick", object_id="object_1", params={})
```

### 2. move_to_pour(object_id=None, params={})
Moves to target position and optionally executes pouring motion.

Parameters:
- object_id: Target cup ID (None = default pouring position)
- params:
  - pour_execute (float): 1.0 = pour, 0.0 = don't pour
  - velocity_scaling (float): Speed 0.05-0.3 (default 0.15)

Example:
```python
# Pour at default position (P2 template)
result = lib.execute("move_to_pour", object_id=None, 
                     params={"pour_execute": 1.0, "velocity_scaling": 0.15})

# Move without pouring (P3 template)
result = lib.execute("move_to_pour", object_id=None,
                     params={"pour_execute": 0.0})

# Pour to specific target (P1 template)
result = lib.execute("move_to_pour", object_id="object_2",
                     params={"pour_execute": 1.0})
```

### 3. place(object_id=None, params={})
Places container at specified location.

Parameters:
- object_id: Target location ID
- params:
  - return_to_origin (float): 1.0 = place back to original position

Example:
```python
result = lib.execute("place", object_id="object_1",
                     params={"return_to_origin": 1.0})
```

### 4. return_home(params={})
Returns robot arm to safe home position.

Parameters:
- params: Usually empty dict

Example:
```python
result = lib.execute("return_home", params={})
```

## Safety Rules

🚫 **STRICTLY FORBIDDEN**:
- NEVER generate coordinate values (x, y, z)
- NEVER generate quaternion orientations (qx, qy, qz, qw)
- NEVER generate velocity/acceleration parameters outside safe range
- NEVER generate joint angles
- NEVER attempt direct hardware control

✅ **ALLOWED OPERATIONS**:
- Semantic understanding of user intent
- Plan selection (P1/P2/P3 templates)
- Specify object_id (string identifiers only)
- Set boolean parameters (pour_execute: 0.0 or 1.0)
- Set scalar parameters within safe ranges (velocity_scaling: 0.05-0.3)
- Interpret execution results

## Execution Flow

User Request → Parse Intent → Select Template (P1/P2/P3) → Execute Action Sequence → Return Results

### Template Types:
- **P1**: Pour to specific target (source + destination specified)
- **P2**: Default pouring (source only or all defaults)
- **P3**: No-pour mode (handover, safety mode)

### Retry Mechanism:
- Each action automatically retries once on failure
- After 2 consecutive failures, user confirmation required for 3rd attempt
- User can skip failed steps

## Your Role

You are responsible for:
1. **Semantic Understanding**: Parse natural language into action parameters
2. **Template Selection**: Choose appropriate execution template
3. **Result Interpretation**: Explain outcomes to users in natural language

You are NOT responsible for:
- Motion planning (handled by MTC)
- Trajectory generation (handled by MTC)
- Collision avoidance (handled by MTC)
- Hardware control (handled by low-level drivers)

## Output Style

- Concise and structured responses
- Focus on high-level task status and results
- Avoid exposing internal technical stack traces
- Use natural language for user communication

## Execution Examples

**Example 1: Simple pouring**
User: "给我倒一杯水"
Parse: source=default, target=default, pour=yes → P2
Actions: pick() → move_to_pour(pour_execute=1.0) → place() → return_home()

**Example 2: Specific pouring**
User: "把object_1的水倒给object_2"
Parse: source=object_1, target=object_2, pour=yes → P1
Actions: pick(object_1) → move_to_pour(object_2, pour=1.0) → place(object_1) → return_home()

**Example 3: Handover**
User: "把杯子递给我，不要倒水"
Parse: source=default, pour=no → P3
Actions: pick() → move_to_pour(pour=0.0) → place() → return_home()
"""

from task_graph import run_main_sequence_cli  # 导入主流程

def create_claude_model():
    """创建Claude Sonnet 4模型实例"""
    if ANTHROPIC_API_KEY:
        return ChatAnthropic(model="claude-sonnet-4-20250514", api_key=ANTHROPIC_API_KEY, temperature=0)
    else:
        # 使用环境变量 ANTHROPIC_API_KEY
        return ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

async def console_reporter(event: dict):
    """控制台事件报告器"""
    t = event.get("type", "event")
    step = event.get("step")
    tool = event.get("tool")
    msg = event.get("message", "")
    attempt = event.get("attempt")
    
    # 支持新的事件类型
    if t in ("before_tool", "after_tool", "fallback_attempt", "fallback_result", "plan_selected", 
             "tool_attempt", "tool_result", "auto_retry", "user_decision_needed", 
             "user_approved_retry", "user_skipped", "execution_plan", "step_starting", "feedback"):
        
        # 特殊格式化执行计划和步骤开始
        if t == "execution_plan":
            print(f"📋 {msg}")
            if event.get("steps"):
                for step_desc in event["steps"]:
                    print(f"   {step_desc}")
            if event.get("estimated_duration"):
                print(f"   ⏱️  {event['estimated_duration']}")
            return
        
        if t == "step_starting":
            print(f"🔧 {msg}")
            if event.get("details"):
                print(f"   💡 {event['details']}")
            return
        
        if t == "feedback":
            print(f"   💬 {msg}")
            return
        
        # 格式化输出
        if attempt:
            print(f"➡️  {t} | step={step or '-'} | attempt={attempt} | {msg}")
        else:
            print(f"➡️  {t} | step={step or '-'} | tool={tool or '-'} | {msg}")
        
        # 显示参数
        if t in ("before_tool", "tool_attempt") and event.get("params"):
            print(f"   📋 params: {json.dumps(event['params'], ensure_ascii=False)}")
        
        # 显示结果
        if t in ("after_tool", "fallback_result", "tool_result") and event.get("result"):
            result = event["result"]
            success = result.get("success", False)
            status = result.get("status", "unknown")
            error = result.get("error", "")
            print(f"   {'✅' if success else '❌'} result: success={success}, status={status}")
            if error and not success:
                print(f"   🚨 error: {error}")
        
        # Additional info for special events
        if t == "user_decision_needed":
            print(f"   ⚠️  User decision needed: action has failed twice consecutively")
        elif t == "auto_retry":
            print(f"   🔄 Auto-retrying...")
        elif t == "user_skipped":
            print(f"   ⏭️  User chose to skip this step")

async def main():
    print("Starting Robot Operation Agent (Direct Action Library Mode)")
    print("=" * 60)
    
    # 初始化action library（确保ROS2环境已初始化）
    try:
        from mtc_action_library import get_action_library
        lib = get_action_library()
        actions = lib.get_actions()
        print(f"✅ Action Library loaded with {len(actions)} actions")
        print(f"   Available actions: {', '.join(actions)}")
    except Exception as e:
        print(f"❌ Failed to initialize Action Library: {e}")
        print("   Please ensure:")
        print("   1. ROS2 workspace is built: colcon build --packages-select mtc_action_library_py")
        print("   2. Workspace is sourced: source install/setup.bash")
        print("   3. Required services are running")
        return

    # Create Claude model（用于conversational responses）
    try:
        llm = create_claude_model()
        print("✅ Claude Sonnet 4 model loaded")
    except Exception as e:
        print(f"❌ Model creation failed: {e}")
        print("   Please set ANTHROPIC_API_KEY environment variable")
        return

    print("\n🤖 Robot Agent Ready (Action Library Mode)!")
    print("=" * 60)
    print("\nAvailable commands:")
    print("- 'run main' or 'execute main ...' - Trigger deterministic task graph")
    print("  Examples:")
    print("    • run main 给我倒一杯水")
    print("    • execute main 把object_1的水倒给object_2")
    print("    • run main 把杯子递给我不要倒水")
    print("\n- Other queries - Conversational Q&A (no robot control)")
    print("\nPress Ctrl+C to exit.\n")
    
    while True:
        try:
            user = input("You: ").strip()
            if not user:
                continue

            if user.lower().startswith("run main") or user.lower().startswith("execute main"):
                print("\n⚙️ Starting task graph (direct Action Library)...")
                print("=" * 60)
                # task_graph不再需要tools参数，因为它内部直接调用get_action_library()
                summary = await run_main_sequence_cli(user, reporter=console_reporter)
                print("=" * 60)
                print("\n🤖 Agent Response:")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                print()
                continue

            # 对于非主流程的问答，可以使用LLM但不给工具
            # 创建简单的聊天响应
            print("\n🤔 Processing conversational query...")
            try:
                response = await llm.ainvoke([{"role": "user", "content": user}])
                print(f"\n🤖 Agent: {response.content}\n")
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!"); break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
