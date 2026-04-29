"""
Natural Language Robot Agent - Using Function Calling and Scene Context
Supports single actions and complete task sequences with intelligent execution
"""

import asyncio
import os
import sys
import argparse
from typing import List, Dict, Any
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Tip: Install python-dotenv to support .env files")
    print("Run: pip install python-dotenv")

# 导入场景管理器和动作工具
try:
    from scene_manager import get_scene_manager
    from action_tools import get_tools
    TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"❌ 无法导入必要模块: {e}")
    print("请确保:")
    print("  1. scene_manager.py 存在于当前目录")
    print("  2. action_tools.py 存在于当前目录")
    print("  3. 已安装 langchain-anthropic 和 langgraph")
    TOOLS_AVAILABLE = False

# ==================== API Key 配置 ====================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY:
    print("警告: 未找到 ANTHROPIC_API_KEY 环境变量")
    print("请使用以下任一方式设置:")
    print("  1. export ANTHROPIC_API_KEY='your-api-key'")
    print("  2. 创建 .env 文件，内容: ANTHROPIC_API_KEY=your-api-key")


# ==================== 动态System Prompt ====================

def build_system_prompt() -> str:
    """构建包含场景上下文的系统提示"""
    
    scene = get_scene_manager()
    state = scene.get_state()
    
    # 格式化物体列表
    if state.objects:
        objects_str = ", ".join(state.objects)
        object_details = []
        for obj_id in state.objects:
            details = scene.get_object_details(obj_id)
            if details:
                object_details.append(
                    f"  - {obj_id}: {details['class_name']} (置信度: {details['confidence']:.2f})"
                )
        objects_detail_str = "\n".join(object_details) if object_details else objects_str
    else:
        objects_str = "无"
        objects_detail_str = "当前场景中没有检测到物体"
    
    # 格式化机器人状态
    robot_holding = state.robot_holding or "无"
    last_action = state.last_action or "无"
    
    return f"""你是一个智能机器人控制助手，专门帮助用户控制机械臂完成抓取、倒水等任务。

## 当前场景状态（实时更新）

📦 **场景中的物体**: {objects_str}
{objects_detail_str}

🤖 **机器人状态**: 
  - 当前抓取: {robot_holding}
  - 上次动作: {last_action}
  - 更新时间: {state.last_updated.strftime('%H:%M:%S')}

## 可用工具

你有以下工具可以调用来完成任务:

### 查询工具
- **get_scene_objects**: 获取场景中的所有物体
- **get_robot_status**: 查询机器人当前状态
- **ask_user_clarification**: 当信息不明确时询问用户

### 单个动作工具
- **pick_object(object_id)**: 抓取指定物体
- **place_object(object_id, return_to_origin)**: 放置物体
- **move_and_pour(target_object_id, should_pour, velocity_scaling)**: 移动并倒水
- **return_home()**: 返回初始位置

### 复合动作工具
- **execute_full_pour_sequence(source_object_id, target_object_id)**: 执行完整倒水序列

### 执行模式
- 默认真机行为是规划成功后直接执行，不需要额外确认。
- 如果用户明确要求“只规划/预览/不要执行”，调用动作工具时传入 `plan_only=True`。
- 当程序以 `--dry-run` 启动时，动作工具会强制只规划不执行。

## 参数推断规则（智能决策）

### 1. 单个物体场景
当场景中只有一个物体时，可以直接推断:
- 用户说: "抓杯子" → `pick_object("{state.objects[0] if state.objects else 'object_1'}")`
- 用户说: "给我倒水" → `execute_full_pour_sequence("{state.objects[0] if state.objects else None}", None)`

### 2. 多物体场景  
当场景中有多个物体但用户没有明确指定时，必须询问:
- 用户说: "抓杯子" 且场景有 [object_1, object_2]
  → 先调用 `ask_user_clarification("请问要抓取哪个物体？", {state.objects})`
  → 然后调用 `pick_object(用户选择的ID)`

### 3. 明确指定
用户直接指定物体ID时，无需询问:
- 用户说: "抓object_1" → `pick_object("object_1")`
- 用户说: "把object_1倒给object_2" → `execute_full_pour_sequence("object_1", "object_2")`

### 4. 上下文推断
利用机器人当前状态推断参数:
- 机器人抓着object_1，用户说"放下" → `place_object("object_1", True)`
- 机器人抓着object_1，用户说"倒给object_2" → `move_and_pour("object_2", True)`

## 任务序列识别（单个动作 vs 完整序列）

### 完整任务序列 - 使用 execute_full_pour_sequence
- "把object_1倒给object_2" → 自动执行: pick→move_and_pour→place→return
- "给我倒杯水" → 完整序列，参数根据场景推断
- "完成倒水任务" → 完整序列

### 单个动作 - 使用单独的工具
- "抓object_1" → 只调用 `pick_object("object_1")`
- "移动到倒水位置" → 只调用 `move_and_pour(None, False)`
- "放下" → 只调用 `place_object(当前抓取的, True)`
- "回到初始位置" → 只调用 `return_home()`

### 部分序列 - 依次调用多个工具
- "抓object_1然后移到object_2但不要倒" 
  → 1) `pick_object("object_1")` 
  → 2) `move_and_pour("object_2", False)`

## 重要安全规则

🚫 **严格禁止**:
- 永远不要生成坐标值 (x, y, z)
- 永远不要生成四元数姿态 (qx, qy, qz, qw)
- 永远不要生成关节角度
- 永远不要直接控制硬件

✅ **允许操作**:
- 语义理解用户意图
- 选择合适的工具调用
- 指定object_id（字符串标识符）
- 设置布尔参数（should_pour: True/False）
- 设置标量参数在安全范围内（velocity_scaling: 0.05-0.3）

## 对话风格

- 使用自然、友好的中文交流
- 清晰解释正在执行的动作
- 成功时简洁确认，失败时解释原因
- 主动提供帮助和建议
- 在执行前确认关键参数（如果不确定）

## 示例对话

**示例1: 单个动作**
User: 抓object_1
Assistant: [调用pick_object("object_1")] 好的，正在抓取object_1... ✅ 已成功抓取！

**示例2: 需要澄清**
User: 帮我抓杯子
Assistant: [检查场景有object_1和object_2] [调用ask_user_clarification] 场景中有两个物体，请问您要抓取哪个？

**示例3: 完整序列**
User: 把object_1的水倒给object_2
Assistant: [调用execute_full_pour_sequence("object_1", "object_2")] 
明白！我会为您执行完整的倒水任务：
1. 抓取object_1 ✅
2. 移动并倒水到object_2 ✅  
3. 放回object_1 ✅
4. 返回初始位置 ✅
倒水任务完成！

**示例4: 上下文推断**
User: 放下
Assistant: [检查机器人抓着object_1] [调用place_object("object_1", True)]
好的，正在将object_1放回原位... ✅ 已放置完成！

## 错误处理

- 如果工具调用失败，向用户解释原因
- 询问用户是否要重试或采取其他措施
- 保持友好和helpful的态度
"""


# ==================== Agent创建 ====================

def create_robot_agent():
    """创建机器人控制Agent"""
    
    if not TOOLS_AVAILABLE:
        raise RuntimeError("工具不可用，无法创建Agent")
    
    # #region agent log
    import json
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"agent_app.py:create_robot_agent:entry","message":"Entering create_robot_agent","data":{"tools_available":TOOLS_AVAILABLE},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # 创建Claude模型
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=ANTHROPIC_API_KEY,
        temperature=0
    )
    
    # #region agent log
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"agent_app.py:create_robot_agent:llm_created","message":"LLM created","data":{"model":"claude-sonnet-4-20250514"},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # 获取工具列表
    tools = get_tools()
    
    # #region agent log
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A,C","location":"agent_app.py:create_robot_agent:tools_loaded","message":"Tools loaded","data":{"tool_count":len(tools),"tool_names":[t.name for t in tools]},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # #region agent log
    # 检查create_react_agent的签名
    import inspect
    sig = inspect.signature(create_react_agent)
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A,B","location":"agent_app.py:create_robot_agent:check_signature","message":"create_react_agent signature","data":{"parameters":list(sig.parameters.keys())},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # #region agent log
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"agent_app.py:create_robot_agent:create_with_prompt","message":"Creating agent with prompt parameter","data":{},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # 创建带有System Prompt的Agent（使用prompt参数）
    # 构建System Prompt模板
    system_prompt = build_system_prompt()
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    # #region agent log
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"agent_app.py:create_robot_agent:prompt_template_created","message":"Prompt template created","data":{"system_prompt_length":len(system_prompt)},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    # 使用prompt参数创建Agent
    agent = create_react_agent(llm, tools, prompt=prompt_template)
    
    # #region agent log
    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"agent_app.py:create_robot_agent:agent_created","message":"Agent created successfully","data":{},"timestamp":__import__('time').time()*1000}) + '\n')
    # #endregion
    
    return agent, tools


# ==================== 主循环 ====================

async def main():
    """主程序入口"""
    
    print("=" * 70)
    print("🤖 智能机器人Agent - 自然语言控制")
    print("=" * 70)
    
    # 检查API Key
    if not ANTHROPIC_API_KEY:
        print("❌ 未设置ANTHROPIC_API_KEY，无法启动")
        return
    
    # 初始化场景管理器
    print("\n📡 正在初始化场景管理器...")
    try:
        scene = get_scene_manager()
        print("✅ 场景管理器已就绪")
        print(f"   {scene.get_summary()}")
    except Exception as e:
        print(f"❌ 场景管理器初始化失败: {e}")
        return
    
    # 初始化Action Library
    print("\n🔧 正在初始化Action Library...")
    try:
        from mtc_action_library import get_action_library
        lib = get_action_library()
        actions = lib.get_actions()
        print(f"✅ Action Library已就绪，可用动作: {', '.join(actions)}")
    except Exception as e:
        print(f"❌ Action Library初始化失败: {e}")
        print("   请确保:")
        print("   1. ROS2环境已source")
        print("   2. mtc_action_library_py已编译")
        print("   3. move_group正在运行")
        return
    
    # 创建Agent
    print("\n🧠 正在创建AI Agent...")
    try:
        agent, tools = create_robot_agent()
        print(f"✅ Agent已就绪，加载了 {len(tools)} 个工具")
        print(f"   工具列表: {', '.join([t.name for t in tools])}")
    except Exception as e:
        print(f"❌ Agent创建失败: {e}")
        return
    
    print("\n" + "=" * 70)
    print("🎉 系统启动完成！")
    print("=" * 70)
    print("\n💡 使用提示:")
    print("  - 直接用自然语言交流，无需特殊命令格式")
    print("  - 示例: '抓object_1', '把object_1倒给object_2', '场景里有什么'")
    print("  - 输入 'quit' 或 'exit' 退出")
    print("  - Ctrl+C 也可以退出")
    print()
    
    # 对话历史
    chat_history = []
    
    # 主循环
    while True:
        try:
            # 获取用户输入
            user_input = input("👤 You: ").strip()
            
            if not user_input:
                continue
            
            # 退出命令
            if user_input.lower() in ['quit', 'exit', '退出', '再见']:
                print("\n👋 再见！机器人Agent已关闭。")
                break
            
            # 特殊命令：查看场景
            if user_input.lower() in ['scene', 'status', '状态', '场景']:
                print(f"\n📊 {scene.get_summary()}")
                print(f"   更新时间: {scene.get_state().last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
                continue
            
            # 调用Agent
            print("\n🤖 Agent: ", end="", flush=True)
            
            try:
                # 构建输入
                inputs = {
                    "messages": chat_history + [HumanMessage(content=user_input)]
                }
                
                # 执行Agent（流式输出）
                response_content = ""
                for chunk in agent.stream(inputs):
                    # #region agent log
                    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F,G","location":"agent_app.py:main:chunk_received","message":"Received chunk","data":{"chunk_keys":list(chunk.keys())},"timestamp":__import__('time').time()*1000}) + '\n')
                    # #endregion
                    
                    # 提取agent的响应
                    if "agent" in chunk:
                        messages = chunk["agent"].get("messages", [])
                        for msg in messages:
                            if hasattr(msg, "content") and msg.content:
                                # #region agent log
                                with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
                                    content_type = type(msg.content).__name__
                                    content_preview = str(msg.content)[:100] if isinstance(msg.content, str) else str(msg.content)[:100]
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"agent_app.py:main:message_content","message":"Message content type check","data":{"content_type":content_type,"content_preview":content_preview,"is_string":isinstance(msg.content, str)},"timestamp":__import__('time').time()*1000}) + '\n')
                                # #endregion
                                
                                # 只处理字符串内容，跳过工具调用（列表）
                                if isinstance(msg.content, str):
                                    # #region agent log
                                    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
                                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"G","location":"agent_app.py:main:string_content","message":"Processing string content","data":{"content_length":len(msg.content)},"timestamp":__import__('time').time()*1000}) + '\n')
                                    # #endregion
                                    
                                    # 实时打印
                                    print(msg.content, end="", flush=True)
                                    response_content += msg.content
                                else:
                                    # #region agent log
                                    with open('/home/wenhao/uf_custom_ws/.cursor/debug.log', 'a') as f:
                                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"agent_app.py:main:non_string_content","message":"Skipping non-string content (tool call)","data":{"content_type":type(msg.content).__name__},"timestamp":__import__('time').time()*1000}) + '\n')
                                    # #endregion
                                    # 工具调用，不打印
                                    pass
                
                print()  # 换行
                
                # 更新对话历史
                chat_history.append(HumanMessage(content=user_input))
                if response_content:
                    chat_history.append(AIMessage(content=response_content))
                
                # 限制历史长度（保留最近10轮对话）
                if len(chat_history) > 20:
                    chat_history = chat_history[-20:]
            
            except Exception as e:
                print(f"\n❌ Agent执行出错: {e}")
                import traceback
                traceback.print_exc()
        
        except KeyboardInterrupt:
            print("\n\n👋 收到中断信号，正在退出...")
            break
        
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    # 清理资源
    print("\n🔄 正在清理资源...")
    try:
        scene.shutdown()
        print("✅ 资源清理完成")
    except:
        pass


# ==================== 入口点 ====================

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Natural Language Robot Control Agent")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Run in dry-run mode (no robot commands)")
    parser.add_argument("--no-ros", action="store_true",
                       help="Disable ROS2 integration (testing only)")
    args = parser.parse_args()
    
    # Set environment variables based on args
    if args.dry_run:
        os.environ["AGENT_DRY_RUN"] = "true"
        print("🔧 Running in DRY-RUN mode (no robot commands will be executed)")
    
    if args.no_ros:
        os.environ["AGENT_NO_ROS"] = "true"
        print("🔧 Running with ROS2 disabled (testing only)")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        import traceback
        traceback.print_exc()
