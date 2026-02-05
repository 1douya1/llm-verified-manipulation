# 手动构建指南

由于自动化工具的限制，请按照以下步骤在**真实终端**中手动构建和验证：

---

## 🚀 快速构建（复制粘贴）

打开终端，然后复制粘贴以下命令：

```bash
# 进入工作空间
cd /home/wenhao/RSS_Workshop/RSS_Workshop

# Source ROS2 环境
source /opt/ros/humble/setup.bash

# 清理旧构建（如果存在）
rm -rf build install log

# 构建工作空间
colcon build --symlink-install

# Source 新构建的工作空间
source install/setup.bash

# 验证包
echo "=== 验证 ROS2 包 ==="
ros2 pkg list | grep -E "(mtc_interface|mtc_tutorial)"

# 检查安装的文件
echo ""
echo "=== 检查安装目录 ==="
ls -la install/

# 显示构建总结
echo ""
echo "=== 构建总结 ==="
if [ -d "install/mtc_interface" ] && [ -d "install/mtc_tutorial" ]; then
    echo "✅ mtc_interface 构建成功"
    echo "✅ mtc_tutorial 构建成功"
    echo ""
    echo "🎉 所有包构建完成！"
else
    echo "❌ 某些包构建失败，请检查错误信息"
fi
```

---

## 📋 预期输出

### 构建开始
```
Starting >>> mtc_interface
Starting >>> mtc_tutorial
```

### 构建过程
```
--- stderr: mtc_interface
[warnings about CMake policies - 可忽略]
---

--- stderr: mtc_tutorial  
[编译警告 - 可忽略]
---
```

### 构建完成
```
Finished <<< mtc_interface [5.2s]
Finished <<< mtc_tutorial [18.1s]

Summary: 2 packages finished [23.4s]
  2 packages had stderr output: mtc_interface mtc_tutorial
```

### 验证输出
```
=== 验证 ROS2 包 ===
mtc_interface
mtc_tutorial

=== 检查安装目录 ===
mtc_interface/
mtc_tutorial/
setup.bash
setup.sh
...

=== 构建总结 ===
✅ mtc_interface 构建成功
✅ mtc_tutorial 构建成功

🎉 所有包构建完成！
```

---

## 🔍 详细验证步骤

### 1. 检查包结构

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop

# 检查源代码包
echo "=== 源代码包 ==="
colcon list

# 预期输出:
# mtc_interface    src/mtc_interface    (ros.ament_cmake)
# mtc_tutorial     src/mtc_tutorial     (ros.ament_cmake)
```

### 2. 检查消息和动作

```bash
# Source 环境
source install/setup.bash

# 列出消息类型
echo "=== 消息类型 ==="
ros2 interface list | grep mtc_interface

# 预期输出:
# mtc_interface/action/ExecutePour
# mtc_interface/action/ExecuteTask
# mtc_interface/msg/DetectedObject
# mtc_interface/msg/DetectionResult
```

### 3. 检查可执行文件

```bash
# 列出 mtc_tutorial 可执行文件
echo "=== 可执行文件 ==="
ls -la install/mtc_tutorial/lib/mtc_tutorial/

# 预期输出:
# execute_pour_server
# execute_task_server
# modular_task_server
# mtc_tutorial
# ... 等
```

### 4. 检查 Python 脚本

```bash
# 检查 Python 脚本
echo "=== Python 脚本 ==="
ls -la install/mtc_tutorial/lib/mtc_tutorial/*.py

# 预期看到所有 Python 脚本
```

### 5. 检查启动文件

```bash
# 检查启动文件
echo "=== 启动文件 ==="
ls -la install/mtc_tutorial/share/mtc_tutorial/launch/

# 预期输出:
# detection_only.launch.py
# modular_task_server.launch.py
# pick_place_demo.launch.py
# pour_demo.launch.py
# florence_visual_detection.launch.py
```

---

## ⚠️ 常见问题

### 问题 1: "Package 'moveit_task_constructor_core' not found"

**解决方案**:
```bash
# 安装 MoveIt Task Constructor
sudo apt update
sudo apt install ros-humble-moveit-task-constructor-*

# 然后重新构建
colcon build --symlink-install
```

### 问题 2: "Package 'mtc_interface' not found" (在构建 mtc_tutorial 时)

**原因**: mtc_interface 构建失败或未先构建

**解决方案**:
```bash
# 先单独构建 mtc_interface
colcon build --packages-select mtc_interface

# 然后构建 mtc_tutorial
colcon build --packages-select mtc_tutorial
```

### 问题 3: 编译警告

**示例警告**:
```
warning: unused variable 'current_state_ptr' [-Wunused-but-set-variable]
warning: unused parameter 'uuid' [-Wunused-parameter]
```

**说明**: 这些是代码风格警告，不影响功能，可以忽略。

### 问题 4: CMake 策略警告

**示例警告**:
```
CMake Warning (dev) at ... Policy CMP0167 is not set ...
```

**说明**: 这些来自 MoveIt 上游包，不影响构建，可以忽略。

---

## 🧪 测试 Agent

### 安装 Python 依赖

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop/agent

# 安装依赖
pip install -r simple_requirements.txt

# 验证安装
python3 -c "import langchain_core, langchain_anthropic, langgraph; print('✅ 依赖安装成功')"
```

### 配置 API Key

```bash
# 创建 .env 文件
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env

# 验证
cat .env
```

### 测试导入

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop/agent

# 测试场景管理器
python3 -c "from scene_manager import get_scene_manager; print('✅ SceneManager OK')"

# 测试动作工具
python3 -c "from action_tools import get_tools; print('✅ ActionTools OK')"
```

---

## 🎮 运行 Demo

### 使用启动脚本（推荐）

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop

# 确保脚本可执行
chmod +x scripts/run_demo.sh

# 运行
./scripts/run_demo.sh
```

### 手动启动

```bash
# 终端 1: 启动仿真（如果需要）
source /opt/ros/humble/setup.bash
ros2 launch xarm_moveit_config xarm_moveit_fake.launch.py dof:=6 robot_type:=xarm

# 终端 2: 启动 Agent
cd /home/wenhao/RSS_Workshop/RSS_Workshop/agent
source ../install/setup.bash
python3 agent_app.py
```

### Dry-run 模式（无需机器人）

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop/agent
source ../install/setup.bash
python3 agent_app.py --dry-run
```

---

## ✅ 成功标志

构建和验证成功的标志：

1. ✅ `colcon build` 返回 `Summary: 2 packages finished`
2. ✅ `install/` 目录包含 `mtc_interface/` 和 `mtc_tutorial/`
3. ✅ `ros2 pkg list` 显示两个包
4. ✅ `ros2 interface list` 显示 4 个接口
5. ✅ Python 依赖成功安装
6. ✅ Agent 可以启动（即使没有机器人连接）

---

## 📊 构建统计

预期构建时间和资源：

- **总时间**: ~25 秒
- **mtc_interface**: ~5 秒
- **mtc_tutorial**: ~20 秒
- **磁盘空间**: 
  - build/: ~50 MB
  - install/: ~20 MB
  - 总计: ~70 MB

---

## 🆘 需要帮助？

如果遇到问题：

1. **检查日志**: 查看 `log/latest_build/` 目录
2. **阅读文档**: 参考 `README.md` 和 `BUILD_COMMANDS.md`
3. **验证依赖**: 确保所有外部包已安装
4. **清理重建**: `rm -rf build install log && colcon build`

---

**最后更新**: 2026-02-05  
**状态**: 准备构建
