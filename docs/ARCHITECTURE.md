# System Architecture

## Overview

This document describes the software architecture of the AI-driven robot manipulation system presented in the RSS paper.

**Key Design Principle**: Hierarchical task planning with natural language interface on top of MoveIt Task Constructor (MTC).

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Layer 5: Natural Language Interface             │
│                  "Pick up the cup and pour"                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 4: AI Agent (Optional)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ LangGraph    │  │ Scene        │  │ Action       │     │
│  │ Agent        │──│ Manager      │──│ Tools        │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 3: ROS2 Interface                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ DetectionMsg │  │ ExecuteTask  │  │ TF2          │     │
│  │ Subscriber   │  │ Action Client│  │ Transform    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 2: MTC Task Planning (Core)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Task Builder │  │ Stage        │  │ Planning     │     │
│  │ (C++)        │──│ Pipeline     │──│ Scene        │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 1: MoveIt2 Planning + Execution           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ MoveIt2      │  │ Robot Driver │  │ Perception   │     │
│  │ Planning     │──│ (Hardware)   │  │ (Hardware)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

**Layers 1-2**: Always present (core contribution)  
**Layer 3**: ROS2 interface (always present)  
**Layer 4**: Agent layer (optional, can be disabled)  
**Layer 5**: Natural language (optional, can use direct API calls)

---

## Module-Level Overview

### Agent Layer (`agent/` directory)

**Purpose**: Natural language interface to robot control (optional component).

#### 1. Entry Point: `agent_app.py`

**Role**: Main application entry point for LLM-based agent.

**Key Functions**:
- `create_claude_model()` - Initialize Claude Sonnet 4 LLM
- `build_system_prompt()` - Dynamic prompt with scene context
- `main()` - Main event loop for natural language interaction

**Dependencies**:
- LangGraph (agent framework)
- LangChain (tool abstraction)
- Claude API (LLM)

**Can be disabled**: Yes (use C++ MTC directly)

```python
# Key workflow
User Input → Claude LLM → Function Call → Action Tool → ROS2 Action
```

#### 2. Action Tools: `action_tools.py`

**Role**: Wraps robot actions as LangChain tools for LLM consumption.

**Exported Functions**:
- `pick_object(object_id)` - Grasp action tool
- `place_object(object_id, return_to_origin)` - Place action tool
- `move_and_pour(target_id, should_pour, velocity)` - Pour action tool
- `return_home()` - Return to home position tool
- `get_scene_objects()` - Query scene state
- `get_robot_status()` - Query robot state

**Bridge**: Converts high-level commands to ROS2 action calls.

**Can be disabled**: Yes (call ROS2 actions directly)

#### 3. State Management: `scene_manager.py`

**Role**: Maintains real-time scene state from ROS2 topics.

**Key Classes**:
- `SceneState` - Data class for scene representation
- `SceneManagerNode` - ROS2 node subscribing to detection results

**Subscribes to**:
- `/object_detection_result` (DetectionResult msg)

**Provides**:
- List of detected objects
- Object positions and properties
- Robot holding state

**Can be disabled**: Yes (scene info not required for planning-only)

#### 4. Task Graphs: `task_graph.py`

**Role**: Defines multi-step task sequences using LangGraph.

**Key Functions**:
- `build_pick_place_pour_graph()` - Main task graph
- `do_pick(state)` - Pick task node
- `do_move_to_pour(state)` - Move task node
- `do_place(state)` - Place task node
- `do_return_home(state)` - Return task node

**Workflow**: Directed graph with error handling and retry logic.

**Can be disabled**: Yes (use single-action commands)

---

### Core ROS2 Packages

#### Package 1: `mtc_interface`

**Location**: `src/mtc_interface/`

**Purpose**: Message and action interface definitions.

**Contents**:
- `msg/DetectedObject.msg` - Single object detection
- `msg/DetectionResult.msg` - Full scene detection
- `action/ExecutePour.action` - Pour task action
- `action/ExecuteTask.action` - Generic task action

**Language**: ROS2 IDL (interface definition language)

**Dependencies**: `geometry_msgs`, `std_msgs`

**Build Output**: Python and C++ bindings

#### Package 2: `mtc_tutorial`

**Location**: `src/mtc_tutorial/`

**Purpose**: MTC task builder implementations (core contribution).

**C++ Components** (`src/mtc_tutorial/src/`):
1. `modular_task_builders.cpp` - Modular task planning logic
2. `execute_pour_server.cpp` - Pour action server
3. `modular_task_server.cpp` - Generic task server
4. `pour_task_builder.cpp` - Pour-specific builder

**Python Components** (`src/mtc_tutorial/scripts/`):
1. `mtc_mcp_server.py` - MCP server (reference, can be disabled)
2. `ros_client_tools.py` - ROS2 client utilities
3. `detection_to_planning_scene.py` - Injects detected objects into planning scene

**Launch Files** (`src/mtc_tutorial/launch/`):
1. `modular_task_server.launch.py` - Main task server
2. `detection_only.launch.py` - Object detection node

**Dependencies**: MoveIt Task Constructor, MoveIt2, rclcpp

## Component Details

### 1. AI Agent Layer

**Purpose**: Interpret natural language and convert to robot actions

**Key Components**:
- **agent_app.py**: Main agent application using Claude Sonnet 4
- **action_tools.py**: Wraps robot actions as LangChain tools
- **scene_manager.py**: Maintains scene state from ROS2 topics
- **task_graph.py**: Defines task execution graphs

**Technology Stack**:
- LangGraph (agent framework)
- LangChain (tool integration)
- Claude Sonnet 4 (LLM)

### 2. Scene Manager

**Purpose**: Real-time scene understanding

**Responsibilities**:
- Subscribe to `/object_detection_result` topic
- Maintain list of detected objects
- Track robot state (what it's holding, last action)
- Provide context to AI agent

**Data Flow**:
```
ROS2 Detection Node → DetectionResult msg → Scene Manager → Agent Context
```

### 3. Action Tools

**Purpose**: Bridge between AI and robot control

**Available Actions**:
- `pick_object(object_id)`: Grasp object
- `place_object(object_id, return_to_origin)`: Place object
- `move_and_pour(target_id, should_pour, velocity)`: Pour action
- `return_home()`: Return to home position

**Execution Flow**:
```
Agent Decision → Action Tool → ROS2 Action Client → MTC Server → Robot
```

### 4. ROS2 Interface Layer

**Purpose**: Communication between Python and C++

**Key Interfaces**:
- **mtc_interface/msg/DetectionResult.msg**: Object detection messages
- **mtc_interface/action/ExecutePour.action**: Pour task action
- **mtc_interface/action/ExecuteTask.action**: Generic task action

### 5. MTC Task Builders

**Purpose**: High-level motion planning

**Task Types**:
- **Pick Task**: Approach → Grasp → Lift
- **Place Task**: Move → Lower → Release → Retreat
- **Pour Task**: Move to target → Tilt → Pour → Return
- **Move Task**: Cartesian path planning

**Stage Pipeline Example (Pick)**:
```
Current State → Open Gripper → Move to Pre-grasp → 
Move to Grasp → Close Gripper → Attach Object → Lift
```

### 6. MoveIt2 Planning

**Purpose**: Low-level motion planning and execution

**Features**:
- Collision avoidance
- Inverse kinematics (IK)
- Path smoothing
- Velocity/acceleration limits

## Data Flow Examples

### Example 1: Simple Pick Command

```
1. User: "Pick up object_1"
2. Agent interprets: Need to call pick_object("object_1")
3. Action Tool: Calls ROS2 action client
4. MTC Server: Builds pick task with stages
5. MoveIt: Plans collision-free trajectory
6. Robot: Executes motion
7. Agent: Reports success to user
```

### Example 2: Pour Sequence

```
1. User: "Pour object_1 into object_2"
2. Agent plans:
   a. pick_object("object_1")
   b. move_and_pour("object_2", should_pour=True)
   c. place_object("object_1", return_to_origin=True)
   d. return_home()
3. Each step executes sequentially
4. Agent provides progress updates
5. Scene manager tracks state changes
```

## Communication Protocols

### ROS2 Topics

- `/object_detection_result` (DetectionResult): Object detection results
- `/planning_scene` (PlanningScene): MoveIt planning scene
- `/joint_states` (JointState): Robot joint positions
- `/tf` (TF2): Coordinate transforms

### ROS2 Actions

- `/execute_pour_task` (ExecutePour): Pour action server
- `/execute_task` (ExecuteTask): Generic task action server

## Error Handling

### Agent Level
- Invalid object ID → Ask user for clarification
- Ambiguous command → Request more details
- Scene mismatch → Update scene and retry

### ROS2 Level
- Action timeout → Report to agent
- Planning failure → Try alternative parameters
- Execution error → Emergency stop and report

### MTC Level
- No IK solution → Adjust target pose
- Collision detected → Replan with different constraints
- Stage failure → Abort task and cleanup

## Scalability Considerations

### Adding New Actions
1. Define action in `action_tools.py`
2. Add corresponding MTC task builder in C++
3. Register with ROS2 action server
4. Update agent system prompt

### Adding New Objects
1. Ensure detection publishes DetectionResult
2. Scene manager automatically tracks
3. No code changes needed in agent

### Multi-Robot Support
- Each robot needs separate namespace
- Scene manager can track multiple robots
- Action tools need robot_id parameter

## Performance Optimization

### Agent Response Time
- Claude API: ~1-3 seconds
- Scene query: <10ms (local)
- Total: ~1-5 seconds per command

### Motion Planning Time
- Simple pick: ~0.5-2 seconds
- Complex pour: ~2-5 seconds
- Depends on IK solutions and collision checking

### Throughput
- Sequential task execution (no parallelism yet)
- ~10-20 seconds per pick-place cycle
- Limited by physical robot speed

## Security Considerations

### API Key Management
- Store in `.env` file (not committed to git)
- Use environment variables
- Rotate keys regularly

### ROS2 Security
- Use ROS2 Security (SROS2) in production
- Limit network access to robot
- Validate all commands before execution

## Future Enhancements

### Planned Features
1. **Vision Integration**: Direct camera feed to Claude (multimodal)
2. **Parallel Execution**: Multiple robots simultaneously
3. **Learning from Demonstration**: Record and replay tasks
4. **Failure Recovery**: Automatic retry with alternative strategies

### Research Directions
1. **Sim-to-Real**: Train in Isaac Sim, deploy on real robot
2. **Active Learning**: Agent requests demonstrations for unknown tasks
3. **Human-in-the-Loop**: Interactive error correction
