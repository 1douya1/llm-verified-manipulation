# API Reference

## Agent API

### Action Tools

All robot actions are exposed as LangChain tools that the AI agent can call.

#### `pick_object(object_id: Optional[str] = None) -> str`

Grasp a specified object.

**Parameters**:
- `object_id` (str, optional): ID of the object to pick (e.g., "object_1")

**Returns**:
- str: Execution result description

**Example**:
```python
from action_tools import pick_object

result = pick_object("object_1")
print(result)  # "✅ Successfully picked up object_1"
```

**Natural Language Examples**:
- "Pick up object_1"
- "Grasp the cup"
- "Pick the red object"

---

#### `place_object(object_id: Optional[str] = None, return_to_origin: bool = True) -> str`

Place a currently held object at a target location.

**Parameters**:
- `object_id` (str, optional): Target object ID or location
- `return_to_origin` (bool): Whether to return object to its original position (default: True)

**Returns**:
- str: Execution result description

**Example**:
```python
from action_tools import place_object

result = place_object("object_1", return_to_origin=True)
print(result)  # "✅ Successfully placed object"
```

**Natural Language Examples**:
- "Place it back"
- "Put down the cup"
- "Place object_1 at its original position"

---

#### `move_and_pour(target_object_id: Optional[str] = None, should_pour: bool = True, velocity_scaling: float = 0.15) -> str`

Move to a target position and optionally perform a pouring action.

**Parameters**:
- `target_object_id` (str, optional): ID of the target object to pour into
- `should_pour` (bool): Whether to execute the pour motion (default: True)
- `velocity_scaling` (float): Speed multiplier 0.0-1.0 (default: 0.15 for safety)

**Returns**:
- str: Execution result description

**Example**:
```python
from action_tools import move_and_pour

result = move_and_pour("object_2", should_pour=True, velocity_scaling=0.1)
print(result)  # "✅ Pour action completed successfully"
```

**Natural Language Examples**:
- "Pour into object_2"
- "Pour water into the cup"
- "Tilt over object_1"

---

#### `return_home() -> str`

Return the robot to its home position.

**Parameters**: None

**Returns**:
- str: Execution result description

**Example**:
```python
from action_tools import return_home

result = return_home()
print(result)  # "✅ Returned to home position"
```

**Natural Language Examples**:
- "Go home"
- "Return to start"
- "Reset position"

---

### Query Tools

#### `get_scene_objects() -> str`

Get a list of all objects currently detected in the scene.

**Parameters**: None

**Returns**:
- str: Description of scene objects

**Example**:
```python
from action_tools import get_scene_objects

result = get_scene_objects()
print(result)  # "Scene has 2 objects: object_1, object_2"
```

**Natural Language Examples**:
- "What's in the scene?"
- "List all objects"
- "What can you see?"

---

#### `get_robot_status() -> str`

Get the current status of the robot.

**Parameters**: None

**Returns**:
- str: Robot status description

**Example**:
```python
from action_tools import get_robot_status

result = get_robot_status()
print(result)  # "Robot is holding: object_1 | Last action: pick"
```

**Natural Language Examples**:
- "What are you holding?"
- "Robot status"
- "What's the current state?"

---

#### `ask_user_clarification(question: str, options: List[str]) -> str`

Ask the user for clarification when a command is ambiguous.

**Parameters**:
- `question` (str): Question to ask the user
- `options` (List[str]): List of possible options

**Returns**:
- str: User's selected option

**Example**:
```python
from action_tools import ask_user_clarification

result = ask_user_clarification(
    "Which object do you want to pick?",
    ["object_1", "object_2", "object_3"]
)
print(result)  # User's choice
```

---

## Scene Manager API

### SceneManager Class

Manages the scene state by subscribing to ROS2 detection topics.

#### `get_scene_manager() -> SceneManager`

Get the singleton scene manager instance.

**Example**:
```python
from scene_manager import get_scene_manager

scene = get_scene_manager()
```

---

#### `get_objects() -> List[str]`

Get list of all detected object IDs.

**Returns**:
- List[str]: List of object IDs (e.g., ["object_1", "object_2"])

**Example**:
```python
scene = get_scene_manager()
objects = scene.get_objects()
print(objects)  # ["object_1", "object_2"]
```

---

#### `get_object_details(object_id: str) -> Optional[Dict[str, Any]]`

Get detailed information about a specific object.

**Parameters**:
- `object_id` (str): Object ID

**Returns**:
- Dict with object details:
  - `class_name` (str): Object class
  - `confidence` (float): Detection confidence
  - `position` (dict): {x, y, z} coordinates
  - `fitted_height` (float, optional): Height if geometry fitted
  - `fitted_radius` (float, optional): Radius if geometry fitted

**Example**:
```python
scene = get_scene_manager()
details = scene.get_object_details("object_1")
print(details["class_name"])  # "cup"
print(details["position"])  # {"x": 0.5, "y": -0.3, "z": 0.1}
```

---

#### `get_robot_holding() -> Optional[str]`

Get the ID of the object the robot is currently holding.

**Returns**:
- str or None: Object ID or None if not holding anything

**Example**:
```python
scene = get_scene_manager()
holding = scene.get_robot_holding()
if holding:
    print(f"Holding: {holding}")
else:
    print("Not holding anything")
```

---

#### `set_robot_holding(object_id: Optional[str])`

Update what object the robot is holding.

**Parameters**:
- `object_id` (str or None): Object ID or None to clear

**Example**:
```python
scene = get_scene_manager()
scene.set_robot_holding("object_1")  # Robot picked up object_1
scene.set_robot_holding(None)  # Robot released the object
```

---

## ROS2 Message Interfaces

### DetectionResult.msg

Published by object detection nodes.

**Fields**:
```
std_msgs/Header header
DetectedObject[] objects
```

### DetectedObject.msg

Information about a single detected object.

**Fields**:
```
string object_id
string class_name
float32 confidence
geometry_msgs/Point position_base
geometry_msgs/Point position_camera
bool geometry_fitted
float32 fitted_height
float32 fitted_radius
```

### ExecutePour.action

Action definition for pour tasks.

**Goal**:
```
# Pour task parameters
float32 tilt_start_deg
float32 tilt_end_deg
float32 tilt_speed_deg_s
float32 pour_hold_sec
# ... additional parameters
```

**Result**:
```
bool success
string status
float32 duration_sec
```

**Feedback**:
```
string current_stage
float32 progress
```

---

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY`: Anthropic API key (required)
- `AGENT_DRY_RUN`: Set to "true" to run without robot (optional)
- `AGENT_NO_ROS`: Set to "true" to disable ROS2 (testing only)

### Config File

See `configs/agent_config.yaml` for all configurable parameters.

**Key sections**:
- `agent.model`: LLM configuration
- `agent.scene`: Scene manager settings
- `agent.actions`: Action parameters
- `agent.safety`: Safety limits

---

## Error Handling

### Common Error Codes

- **PlanningError**: Motion planning failed
- **ExecutionError**: Action execution failed
- **TimeoutError**: Action exceeded timeout
- **ObjectNotFoundError**: Specified object not in scene
- **RobotBusyError**: Robot is executing another action

### Example Error Handling

```python
from action_tools import pick_object

try:
    result = pick_object("object_1")
    print(result)
except Exception as e:
    print(f"Error: {e}")
    # Handle error (retry, ask user, etc.)
```

---

## Agent Prompting Guide

### Best Practices

1. **Be Specific**: Use exact object IDs when known
   - Good: "Pick up object_1"
   - Bad: "Pick up the thing"

2. **Check Scene First**: Query scene before acting
   - "What objects are in the scene?"
   - "Is object_1 visible?"

3. **Sequential Commands**: Agent handles multi-step tasks
   - "Pick up object_1, pour into object_2, then go home"

4. **Natural Language**: No special syntax required
   - "Can you grab the cup and pour it?"
   - "Put that down gently"

### Advanced Prompting

**Conditional Logic**:
```
If object_1 is in the scene, pick it up and pour into object_2. 
Otherwise, just go to home position.
```

**Parameter Control**:
```
Move to object_1 very slowly (use low velocity)
```

**Error Recovery**:
```
Try to pick object_1. If that fails, try object_2 instead.
```

---

## Development

### Adding New Actions

1. Define tool in `action_tools.py`:
```python
@tool
def my_new_action(param1: str) -> str:
    """Action description for the agent"""
    # Implementation
    return "Result"
```

2. Update system prompt in `agent_app.py` to include the new action

3. Test with agent:
```
You: Execute my new action with param1
```

### Extending Scene Manager

Add custom fields to `SceneState` dataclass:

```python
@dataclass
class SceneState:
    objects: List[str]
    custom_field: str = ""  # Your addition
```

### Custom Message Types

1. Define in `src/mtc_interface/msg/`
2. Build with `colcon build`
3. Import in Python: `from mtc_interface.msg import MyMessage`
