# MTC Action Library

`mtc_action_library_core` (C++) + `mtc_action_library_py` (pybind11 wrapper)
is a **second, independent entry point** into the same MTC task builders
that `mtc_tutorial` exposes to the LLM agent. It exists for two reasons:

1. **Paper baseline** -- a deterministic, LLM-free way to exercise
   `pick`, `place`, `move_to_pour`, and `return_home`. The reviewer can
   compare the agent-driven pipeline to the baseline in a controlled
   experiment, holding the motion stack constant.
2. **Single-action testing** -- during bring-up or regression, you often
   want to smoke-test one atomic action at a time without standing up the
   full agent + MCP + perception pipeline.

The action library and the MCP main chain are **intentionally decoupled**.
The MCP path (`mtc_tutorial::ModularTaskServer` invoked via
`mtc_mcp_server.py`, wrapped by the agent's `action_tools.py`) is
unchanged. `mtc_action_library_core` and `mtc_action_library_py` are
colcon packages that live next to `mtc_tutorial` in the same workspace
but do not link against it.

```
                Natural-language prompt
                        |
                        v
               +--------+---------+
               |  LangGraph agent |
               | (agent/*.py)     |
               +--------+---------+
                        |
                   LangChain tools
                        |
                        v
               +--------+---------+          ACTION LIBRARY (baseline)
               |  mtc_mcp_server  |          +-----------------------+
               |  (MCP protocol)  |          | mtc_action_library_py |
               +--------+---------+          |  Python / pybind11    |
                        |                    +-----------+-----------+
                   RPC request                           |
                        |                                v
                        v                    +-----------+-----------+
               +--------+---------+          | mtc_action_library_   |
               | ModularTaskServer| <---+    |         core          |
               |   (mtc_tutorial) |    |    |  C++  shared library  |
               +--------+---------+    |    +-----------+-----------+
                        |              |                |
                        +--------------+----------------+
                                       |
                                       v
                                 MoveIt Task
                                  Constructor
                                       |
                                       v
                              plan -> execute
```

The two chains share everything *below* MTC (the C++ task-builders in
`mtc_tutorial/src/modular_task_builders.cpp` are reused in shape, not
imported directly; the action library re-implements the same stage
sequences in its own C++ classes). There is no code path where the agent
invokes the action library nor where the action library invokes the
agent.

---

## Package layout

```
src/
  mtc_action_library_core/        # C++ shared library
    include/mtc_action_library/
      action_library.hpp          # public C++ API
      action_params.hpp           # parameter struct
      action_result.hpp           # result struct
      action_stats.hpp
      task_builders.hpp           # pick / place / pour / return_home
    src/
      action_library.cpp
      task_builders.cpp
      action_stats.cpp
    CMakeLists.txt
    package.xml                   # depends on moveit_task_constructor_core,
                                  #   moveit_ros_planning_interface,
                                  #   nlohmann_json

  mtc_action_library_py/          # pybind11 wrapper + Python outer shell
    src/bindings.cpp              # pybind11 glue
    mtc_action_library/
      __init__.py                 # re-exports ActionLibrary, ActionResult
      action_library.py           # Python-level wrapper
      debug_tools.py              # print_stats, interactive_test, ...
    CMakeLists.txt
    package.xml
    setup.py / setup.cfg
```

These two packages are built by colcon alongside `mtc_tutorial`; none of
them is modified.

---

## Python API

```python
from mtc_action_library import ActionLibrary, ActionResult

lib = ActionLibrary(node_name="baseline_runner")

# pick -- grasp object with id="cup_1"
result: ActionResult = lib.execute(
    "pick",
    object_id="cup_1",
    plan_only=False,            # True = plan without executing
    velocity_scaling=0.3,
    acceleration_scaling=0.5,
    max_solutions=1,
    max_ik_solutions=2,
)

if result.success:
    print(f"pick succeeded in {result.duration_sec:.2f}s "
          f"({result.num_solutions} solutions found)")
else:
    print(f"pick failed: {result.error_msg} (code {result.error_code})")
    for line in result.stage_feedback:
        print("  " + line)

# move_to_pour -- move to bowl_1 for pouring (does not execute the pour motion)
lib.execute("move_to_pour", object_id="bowl_1")

# place -- release object over bowl_1
lib.execute("place", object_id="bowl_1")

# return_home -- drive the arm to the home joint configuration
lib.execute("return_home")
```

### Parameters (kwargs)

| kwarg | Default | Description |
|-------|---------|-------------|
| `plan_only` | `False` | If `True`, plan and visualize but do not send to the controller. |
| `max_solutions` | `1` | Upper bound on MTC solution candidates. |
| `velocity_scaling` | `0.3` | 0 < v <= 1.0. Conservative default for first runs. |
| `acceleration_scaling` | `0.5` | 0 < a <= 1.0. |
| `max_ik_solutions` | `2` | IK solver branching factor. |
| `feedback_callback` | `None` | Optional `Callable[[str], None]` to tail stage feedback live. |

### Supported actions

| Name | Required args | Notes |
|------|---------------|-------|
| `pick` | `object_id` | Must reference an object in the current planning scene. |
| `place` | `object_id` (target) | The object held by the gripper is released over `object_id`. |
| `move_to_pour` | `object_id` (target) | Moves over the target without tilting. |
| `return_home` | -- | Uses `xarm_moveit_config`'s named target. |

---

## Running the baseline

Build (once) and source:

```bash
colcon build --symlink-install --packages-up-to mtc_action_library_py
source install/setup.bash
```

Run a minimal smoke test (see `agent/` for an analogous run with the LLM
agent):

```python
# scripts/action_library_smoke.py
import rclpy
from mtc_action_library import ActionLibrary

rclpy.init()
lib = ActionLibrary("baseline_smoke")
for action in ("pick", "move_to_pour", "place", "return_home"):
    r = lib.execute(action, object_id="cup_1", plan_only=True)
    print(action, r)
rclpy.shutdown()
```

The `plan_only=True` flag means nothing is sent to the controller, so
this script is safe to run against a headless MoveIt or against the
plan-only demo (`./scripts/run_demo.sh --plan-only`). Drop `plan_only`
once the arm is ready.

---

## What the action library does NOT do

- It does not accept LLM prompts -- call `execute(action_name, ...)`
  directly from Python.
- It does not implement the MCP protocol. If you want an MCP server,
  use `mtc_tutorial/scripts/mtc_mcp_server.py` (that is the agent path).
- It does not touch `mtc_tutorial`'s build -- you can rip either side out
  without breaking the other.
- It does not ship its own perception. Populate the MoveIt planning scene
  yourself (use the real-robot pipeline's `detection_to_planning_scene.py`
  or a static `.yaml` of objects) before calling `execute`.

If you find yourself routing action-library calls through the agent or
vice versa, you are fighting the design. Keep them as two comparable
baselines.

---

## Related

- [EXECUTION_MODES.md](../EXECUTION_MODES.md)
- [REAL_ROBOT_QUICK_START.md](REAL_ROBOT_QUICK_START.md)
- `src/mtc_tutorial/src/modular_task_builders.cpp` -- the MTC task-building
  logic that the agent path uses, and that the action library re-implements
  in `mtc_action_library_core/src/task_builders.cpp`.
