# Agent 快速参考 🚀

## ⚡ 三步启动

```bash
# 1️⃣ 启动机器人
bash src/scripts/start_calibrated_system.sh

# 2️⃣ 添加物体（必须！）
python3 add_detected_objects.py

# 3️⃣ 启动Agent
cd Langraph_Agent && python3 agent_app.py
```

## 🎯 正确的指令格式

### ✅ 控制机器人（必须使用前缀）

```bash
execute main 把object_1的水倒给object_2
execute main 抓取object_1
execute main 给我倒一杯水
run main 把杯子递给我不要倒水
```

### ❌ 错误示例（只会聊天，不控制机器人）

```bash
帮我抓object_1          # ❌ 缺少前缀
Can you pick object1?   # ❌ 缺少前缀
把水倒给object_2        # ❌ 缺少前缀
```

## 📋 常用指令

| 指令 | 说明 |
|------|------|
| `execute main 把object_1的水倒给object_2` | P1模板：指定源和目标 |
| `execute main 给我倒一杯水` | P2模板：使用默认位置 |
| `execute main 抓取object_1` | 只抓取，不倾倒 |
| `execute main 把杯子递给我不要倒水` | P3模板：递给用户 |

## 🐛 问题速查

| 错误信息 | 原因 | 解决方法 |
|----------|------|----------|
| `object 'object_1' not in scene` | 物体未添加到场景 | 运行 `add_detected_objects.py` |
| Agent只聊天不执行 | 忘记加前缀 | 使用 `execute main` 开头 |
| `CartesianPath: min_fraction not met` | 路径规划失败 | 检查物体坐标，调整参数 |
| `frame 'object_1' is not attached` | 没有成功抓取 | 确认物体在场景中且位置正确 |

## 📦 物体名称映射

根据你的检测结果：

| 检测系统输出 | 规划场景中的ID | Agent使用 |
|--------------|----------------|-----------|
| cup_object (红框) | object_1 | `object_1` |
| cup_object_2 (黄框) | object_2 | `object_2` |
| - | object | `object` (默认) |

## 🎨 快速测试流程

```bash
# 1. 确认物体已添加
python3 add_detected_objects.py

# 2. 启动Agent
cd Langraph_Agent && python3 agent_app.py

# 3. 测试简单指令
You: execute main 给我倒一杯水

# 4. 测试指定物体
You: execute main 把object_1的水倒给object_2
```

## 💡 提示

- 🔴 **每次重启move_group都要重新添加物体**
- 🔴 **必须使用 `execute main` 或 `run main` 前缀**
- 🟢 物体坐标可以在 `add_detected_objects.py` 中修改
- 🟢 使用RViz查看物体是否正确添加到场景

## 📞 需要帮助？

查看详细文档：`AGENT_USAGE_GUIDE.md`






