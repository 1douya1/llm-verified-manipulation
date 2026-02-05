# 🚀 从这里开始！

欢迎使用 RSS_Workshop！这是你的快速开始指南。

---

## ⚡ 一分钟快速检查

在终端执行以下命令（复制粘贴即可）：

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop && \
source /opt/ros/humble/setup.bash && \
colcon build --symlink-install && \
echo "" && echo "✅ 构建完成！继续阅读下方说明..."
```

**预期时间**: 约 25 秒

---

## 📚 完整文档索引

根据你的需求选择阅读：

### 🏃 我想快速开始
→ **[MANUAL_BUILD_GUIDE.md](MANUAL_BUILD_GUIDE.md)** - 逐步构建指南（推荐新手）

### 📖 我想了解系统
→ **[README.md](README.md)** - 完整介绍  
→ **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - 系统架构  
→ **[docs/QUICK_START.md](docs/QUICK_START.md)** - 5分钟快速入门

### 🔧 我想查看构建命令
→ **[BUILD_COMMANDS.md](BUILD_COMMANDS.md)** - 所有构建命令  
→ **[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)** - 文件验证报告

### 💻 我想了解 API
→ **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** - 完整 API 文档

### 🤔 我想知道什么被排除了
→ **[docs/EXCLUDED_COMPONENTS.md](docs/EXCLUDED_COMPONENTS.md)** - 排除内容说明

### 📊 我想了解创建过程
→ **[REPOSITORY_SUMMARY.md](REPOSITORY_SUMMARY.md)** - 仓库创建总结

---

## 🎯 三步启动 Demo

### 步骤 1: 构建工作空间

```bash
cd /home/wenhao/RSS_Workshop/RSS_Workshop
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### 步骤 2: 安装 Python 依赖

```bash
cd agent
pip install -r simple_requirements.txt
echo "ANTHROPIC_API_KEY=your-key-here" > .env
```

### 步骤 3: 运行 Demo

```bash
# 返回工作空间根目录
cd ..

# 使用启动脚本
./scripts/run_demo.sh
```

---

## ✅ 验证清单

构建成功的标志：

- [ ] `colcon build` 显示 "2 packages finished"
- [ ] `install/` 目录存在
- [ ] `ros2 pkg list | grep mtc` 显示两个包
- [ ] Agent 可以启动（`python3 agent/agent_app.py --dry-run`）

---

## 🆘 遇到问题？

### 快速诊断

```bash
# 检查 ROS2 环境
echo $ROS_DISTRO  # 应该输出: humble

# 检查包
colcon list  # 应该显示 2 个包

# 检查依赖
ros2 pkg list | grep moveit_task_constructor  # 应该有输出
```

### 常见问题

1. **构建失败**: 参考 [MANUAL_BUILD_GUIDE.md](MANUAL_BUILD_GUIDE.md) 的"常见问题"部分
2. **找不到包**: 确保 `source /opt/ros/humble/setup.bash`
3. **Python 错误**: 检查 `pip install -r agent/simple_requirements.txt`

---

## 📁 目录结构概览

```
RSS_Workshop/
├── agent/              # AI Agent (Python)
├── src/                # ROS2 包 (C++/Python)
├── docs/               # 文档
├── scripts/            # 工具脚本
├── configs/            # 配置文件
└── README.md           # 主文档
```

---

## 🎓 推荐学习路径

**第一天**: 
1. 阅读 [README.md](README.md)
2. 执行构建（上面的"三步启动"）
3. 阅读 [MANUAL_BUILD_GUIDE.md](MANUAL_BUILD_GUIDE.md)

**第二天**:
1. 阅读 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. 尝试运行 demo
3. 查看 [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

**第三天**:
1. 修改 `agent/agent_app.py` 尝试自定义
2. 阅读 C++ 源代码
3. 尝试添加新动作

---

## 🎉 快速命令参考

| 任务 | 命令 |
|------|------|
| **构建** | `colcon build --symlink-install` |
| **清理** | `rm -rf build install log` |
| **Source** | `source install/setup.bash` |
| **列出包** | `colcon list` |
| **运行 Demo** | `./scripts/run_demo.sh` |
| **运行 Agent** | `cd agent && python3 agent_app.py` |
| **Dry-run** | `python3 agent_app.py --dry-run` |

---

## 📞 获取帮助

- **文档**: 查看 `docs/` 文件夹
- **构建问题**: 参考 [MANUAL_BUILD_GUIDE.md](MANUAL_BUILD_GUIDE.md)
- **API 问题**: 参考 [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

---

## ⭐ 关键文件

新位置的重要文件：

- **主 README**: `README.md`
- **构建指南**: `MANUAL_BUILD_GUIDE.md` ⬅️ 从这里开始！
- **验证报告**: `VERIFICATION_REPORT.md`
- **Demo 脚本**: `scripts/run_demo.sh`

---

**准备好了吗？打开终端，复制粘贴上面的"一分钟快速检查"命令开始吧！** 🚀

---

**工作空间位置**: `/home/wenhao/RSS_Workshop/RSS_Workshop`  
**最后更新**: 2026-02-05  
**状态**: ✅ 准备就绪
