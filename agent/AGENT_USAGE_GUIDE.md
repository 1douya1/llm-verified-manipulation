# Agent 使用指南 - 如何正确控制机器人

## 🎯 核心概念

### Agent 有两种模式：

1. **机器人控制模式** - 执行实际的机器人动作
2. **对话模式** - 回答问题，但不控制机器人

## 📝 正确的使用方式

### ✅ 机器人控制模式（必须使用特定前缀）

**格式**：必须以 `execute main` 或 `run main` 开头

```bash
# ✅ 正确示例
execute main 把object_1的水倒给object_2
execute main 抓取object_1
execute main 给我倒一杯水
run main 把杯子递给我不要倒水

# ❌ 错误示例（这些会进入对话模式，不会控制机器人）
帮我抓object_1
Can you help me to pick object1?
把object_1的水倒给object_2
```

### ❌ 对话模式（不控制机器人）

不以 `execute main` 或 `run main` 开头的所有输入都会被当作普通对话。

```bash
# 这些都只是聊天，不会控制机器人
Can you help me to pick object1?
How I can use you to execute command on robot?
机器人怎么操作？
```

## 🔧 完整工作流程

### 步骤1：启动系统

```bash
# 终端1：启动机器人和MoveIt
cd /home/wenhao/uf_custom_ws
source install/setup.bash
bash src/scripts/start_calibrated_system.sh
```

### 步骤2：添加检测到的物体到规划场景

```bash
# 终端2：添加物体
cd /home/wenhao/uf_custom_ws
source install/setup.bash
python3 add_detected_objects.py
```

**重要**：每次重启move_group后都需要重新添加物体！

### 步骤3：启动Agent

```bash
# 终端3：启动Agent
cd /home/wenhao/uf_custom_ws/Langraph_Agent
source /home/wenhao/uf_custom_ws/install/setup.bash
export ANTHROPIC_API_KEY="your-key"  # 或使用 .env 文件
python3 agent_app.py
```

### 步骤4：控制机器人

在Agent提示符下输入：

```bash
You: execute main 把object_1的水倒给object_2
```

## 📋 支持的指令模板

### P1 模板：指定源和目标的倾倒

```bash
execute main 把object_1的水倒给object_2
execute main 从object_1倒水到object_2
```

**执行流程**：
1. Pick object_1
2. Move to object_2位置并倾倒
3. Place object_1回原位
4. Return home

### P2 模板：默认倾倒（使用默认位置）

```bash
execute main 给我倒一杯水
execute main 倒水
execute main 抓取object_1并倾倒
```

**执行流程**：
1. Pick (默认object或指定object)
2. Move to 默认倾倒位置并倾倒
3. Place 回原位
4. Return home

### P3 模板：不倾倒（递给用户）

```bash
execute main 把杯子递给我不要倒水
execute main 抓取object_1但不倾倒
```

**执行流程**：
1. Pick object
2. Move to pour位置但**不执行倾倒动作**
3. Place
4. Return home

## 🐛 常见问题排查

### 问题1：`object 'object_1' not in scene`

**原因**：物体没有添加到MoveIt规划场景

**解决**：
```bash
cd /home/wenhao/uf_custom_ws
python3 add_detected_objects.py
```

### 问题2：Agent不理解我的指令

**原因**：没有使用 `execute main` 或 `run main` 前缀

**解决**：
```bash
# ❌ 错误
帮我抓object_1

# ✅ 正确
execute main 抓object_1
```

### 问题3：`CartesianPath: min_fraction not met`

**原因**：机器人无法到达目标位置（可能是：位置太远、有碰撞、关节限制等）

**解决方案**：
1. 检查物体坐标是否正确
2. 调整 `velocity_scaling` 和 `min_cartesian_fraction` 参数
3. 确认机器人当前状态

### 问题4：检测到的物体和规划场景中的名称不匹配

**问题**：
- 检测系统输出：`cup_object`, `cup_object_2`
- Agent使用：`object_1`, `object_2`

**解决**：修改 `add_detected_objects.py` 中的名称映射，或者统一命名规则。

## 🎨 参数调整

如果需要调整执行参数（速度、超时等），可以在命令中指定：

```python
# 在 task_graph.py 中修改参数
result = lib.execute(
    "pick",
    object_id="object_1",
    velocity_scaling=0.2,       # 更慢更安全
    max_solutions=1,            # 只找1个解（快速）
    planner_timeout=5.0         # 增加超时时间
)
```

## 📊 检测系统集成建议

为了让检测系统和MoveIt无缝集成，建议：

### 方案1：自动同步（推荐）

创建一个ROS节点，订阅检测结果并自动更新规划场景：

```python
# 伪代码
def detection_callback(msg):
    for detected_object in msg.objects:
        add_to_planning_scene(
            name=detected_object.id,
            x=detected_object.x,
            y=detected_object.y,
            z=detected_object.z
        )
```

### 方案2：统一命名规则

确保检测系统输出的物体ID和Agent使用的ID一致：

```
检测系统 → object_1, object_2, object_3, ...
Agent    → object_1, object_2, object_3, ...
```

### 方案3：名称映射表

在 `add_detected_objects.py` 中维护映射表：

```python
name_mapping = {
    'cup_object': 'object_1',
    'cup_object_2': 'object_2',
    # ...
}
```

## 🎯 完整示例

```bash
# 1. 启动系统
bash src/scripts/start_calibrated_system.sh

# 2. 等待move_group启动完成，然后添加物体
python3 add_detected_objects.py

# 3. 启动Agent
cd Langraph_Agent
python3 agent_app.py

# 4. 在Agent中输入指令（注意前缀！）
You: execute main 把object_1的水倒给object_2

# Agent会执行：
# ✅ Pick object_1
# ✅ Move to object_2 position and pour
# ✅ Place object_1 back
# ✅ Return home
```

## 💡 最佳实践

1. **总是使用 `execute main` 前缀**来触发机器人控制
2. **每次重启move_group后**都要重新运行 `add_detected_objects.py`
3. **物体名称要一致**：检测、规划场景、Agent指令中的名称必须匹配
4. **先测试简单指令**：`execute main 给我倒一杯水`（使用默认object）
5. **检查规划场景**：使用RViz查看物体是否正确添加

## 🔗 相关文档

- [Action Library使用指南](../MTC_ACTION_LIBRARY_GUIDE.md)
- [参数配置指南](../MTC_PARAMS_INTEGRATION_SUMMARY.md)
- [快速开始](../QUICK_START_ACTION_LIBRARY.md)

---

**关键点总结**：
- ✅ 使用 `execute main` 或 `run main` 前缀
- ✅ 先添加物体到规划场景
- ✅ 确保物体名称一致
- ❌ 不要直接问"帮我抓xxx"






