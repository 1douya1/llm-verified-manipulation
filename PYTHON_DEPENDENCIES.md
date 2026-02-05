# Python Dependencies Guide

This document clarifies Python dependency requirements for different use cases.

---

## Summary

**For reviewers running Plan-Only mode**: Python dependencies are **OPTIONAL**.

The core ROS2 packages (`mtc_tutorial`, `mtc_interface`) are written in C++ and do not require Python agent dependencies.

---

## Dependency Breakdown

### 1. Core ROS2 Packages (NO Python dependencies)

**Packages**:
- `src/mtc_interface/` - Message/Action definitions
- `src/mtc_tutorial/src/` - C++ MTC task builders

**Dependencies**: None (standard ROS2 + MoveIt)

**Use case**: Plan-Only mode, simulation, real robot

**Install**: Not applicable (C++ only)

---

### 2. Agent Layer (Python dependencies REQUIRED)

**Files**:
- `agent/agent_app.py` - LLM agent application
- `agent/action_tools.py` - LangChain tool wrappers
- `agent/scene_manager.py` - Scene state management
- `agent/task_graph.py` - Task graph definitions

**Dependencies**: See `agent/simple_requirements.txt`
- `langchain-core>=0.3.0`
- `langchain-anthropic>=0.3.0`  
- `langgraph>=0.2.0`
- `fastapi>=0.116.0` (for web interface)
- `python-dotenv>=1.0.0`

**Use case**: Natural language agent control

**Install**:
```bash
cd agent
pip install -r simple_requirements.txt
```

**API Key**: Also requires `ANTHROPIC_API_KEY` environment variable

---

### 3. ROS2 Python Scripts (Standard ROS2 Python)

**Files**:
- `src/mtc_tutorial/scripts/*.py` - Detection, utilities

**Dependencies**: Standard ROS2 Python (rclpy, etc.)

**Installed automatically with ROS2 workspace build**

---

## When Do You Need Python Dependencies?

| Use Case | Python Agent Deps | API Key |
|----------|-------------------|---------|
| **Plan-Only verification** | ❌ Not needed | ❌ Not needed |
| **MoveIt simulation** | ❌ Not needed | ❌ Not needed |
| **Real robot (C++ only)** | ❌ Not needed | ❌ Not needed |
| **Agent dry-run** | ✅ Required | ⚠️ Optional* |
| **Full agent + robot** | ✅ Required | ✅ Required |

\* Agent can run in test mode without API key, but LLM features won't work.

---

## Installation Options

### Option A: Minimal (Plan-Only)

```bash
# No Python dependencies needed
# Just build ROS2 workspace
colcon build --symlink-install
```

### Option B: With Agent (Full Features)

```bash
# Install agent dependencies
cd agent
pip install -r simple_requirements.txt

# Configure API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env
```

### Option C: Virtual Environment (Recommended for Development)

```bash
# Create virtual environment
python3 -m venv ~/venvs/rss_workshop
source ~/venvs/rss_workshop/bin/activate

# Install dependencies
cd agent
pip install -r simple_requirements.txt

# Remember to activate venv before running agent
source ~/venvs/rss_workshop/bin/activate
```

---

## Dependency Details

### Core Agent Dependencies

From `agent/simple_requirements.txt`:

```
fastapi>=0.116.0           # Web interface (optional)
uvicorn[standard]>=0.35.0  # ASGI server (optional)
websockets>=12.0           # WebSocket support (optional)
pydantic>=2.11.0           # Data validation
anyio>=4.5.0               # Async utilities
python-dotenv>=1.0.0       # Environment variables

# AI Agent core dependencies (REQUIRED for agent)
langchain-core>=0.3.0      # LangChain framework
langchain-anthropic>=0.3.0 # Claude integration
langgraph>=0.2.0           # Agent workflow
```

**Web interface dependencies** (`fastapi`, `uvicorn`, `websockets`) are optional even for agent mode.

---

## Common Issues

### "ImportError: No module named 'langchain_core'"

**Solution**: Install agent dependencies
```bash
cd agent
pip install -r simple_requirements.txt
```

**Note**: Only needed if running agent layer

### "ModuleNotFoundError: No module named 'rclpy'"

**Solution**: Source ROS2 environment
```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

**Note**: This is ROS2, not Python agent deps

### Mixing System and Virtual Environment Packages

**Problem**: Agent dependencies in venv, but ROS2 in system Python

**Solution**: Use `--system-site-packages` when creating venv:
```bash
python3 -m venv --system-site-packages ~/venvs/rss_workshop
```

This allows venv to access system ROS2 packages while isolating agent dependencies.

---

## For Reviewers

**Recommended approach**:

1. **For Plan-Only verification**: Skip Python agent dependencies entirely
   ```bash
   colcon build --symlink-install
   ./scripts/run_demo.sh  # Select option 1
   ```

2. **To test agent integration** (optional): Install agent dependencies
   ```bash
   pip install -r agent/simple_requirements.txt
   ./scripts/run_demo.sh  # Select option 2
   ```

The core contribution (MTC-based planning) is in C++ and does not require Python agent dependencies.

---

## Summary

- ✅ **Core ROS2 packages**: No Python dependencies beyond standard ROS2
- ⚠️ **Agent layer**: Optional, only for LLM integration testing
- ❌ **NOT required for reviewing core contribution**

See [EXECUTION_MODES.md](EXECUTION_MODES.md) for mode-specific requirements.

---

**Last Updated**: 2026-02-05
