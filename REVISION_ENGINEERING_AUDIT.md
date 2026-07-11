# SG-VTA Engineering Audit (paper revision)

Repo state: branch `claude/robotics-codebase-audit-GhNAV`, working tree clean.

The proposed paper framing — *SG-VTA: A Scene-Grounded Verify-Then-Act
Safety Layer for Foundation-Model-Guided Robotic Manipulation* — calls for
five validation stages between the LLM tool call and the MTC executor:
schema, scene grounding, physical bounds, task-state preconditions, and
MoveIt/MTC motion verification. This audit walks through what exists in
the current code, what is partial, and what has to be built before
submission. **No source files are modified by this audit.**

Status legend per item: ✅ implemented · 🟡 partial · ❌ missing ·
🟢 easy to add · 🔴 hard to add.

---

## 1. Currently implemented robot tools

The "agent-facing" surface lives in `agent/action_tools.py` (LangChain
`@tool` decorators, registered in `ALL_TOOLS` at lines 410–423):

| Tool | File:line | Category |
|---|---|---|
| `get_scene_objects` | `agent/action_tools.py:46` | query |
| `get_robot_status` | `agent/action_tools.py:77` | query |
| `ask_user_clarification` | `agent/action_tools.py:106` | query |
| `pick_object` | `agent/action_tools.py:145` | action |
| `place_object` | `agent/action_tools.py:189` | action |
| `move_and_pour` | `agent/action_tools.py:247` | action |
| `return_home` | `agent/action_tools.py:304` | action |
| `execute_full_pour_sequence` | `agent/action_tools.py:344` | composite |

Underneath, the C++ `ActionLibrary` (`src/mtc_action_library_core/src/action_library.cpp:25`)
hard-codes the available action set as
`{"pick", "place", "move_to_pour", "return_home"}`. Tasks are dispatched
to `build_pick_task` / `build_place_task` / `build_move_to_pour_task` /
`build_return_task` in `task_builders.cpp`. The composite
`execute_full_pour_sequence` is purely a Python-side chain
(`agent/action_tools.py:368–405`).

**`setup_scene` does NOT exist as an agent-callable tool.** Scene
construction is performed by:
- `setup_planning_scene(...)` in `src/mtc_tutorial/scripts/ros_client_tools.py:341`
  (~600 lines, called from a ROS bridge node, not the agent);
- the bridge node `src/mtc_tutorial/scripts/detection_to_planning_scene.py`
  that subscribes to `object_detection_result` and forwards it to
  `setup_planning_scene`;
- the MCP-server wrapper at
  `src/mtc_tutorial/scripts/mtc_mcp_server.py:113` (`setup_planning_scene`
  tool), which is part of the legacy MCP path and not wired into
  `action_tools.py`.

There is also a deprecated/legacy MCP toolset
(`mtc_mcp_server.py`: `set_cup_pose`, `set_gripper_close_ratio`,
`update_cup_pose`, `pick_container`, `move_to_pour_position`,
`move_to_secure_place`, `place_container`, `return_to_home`,
`get_task_state`, `abort_and_reset`, `check_object_exists`) — useful for
the paper's "baseline (LLM+JSON only)" track but currently disconnected
from the LangGraph agent.

**Status:** ✅ four core actions exposed; ❌ no `setup_scene` agent tool;
🟡 a parallel MCP toolset exists but is dormant.

---

## 2. Existing tool schemas

**Where arguments are defined:**
- LangChain side (Python): function signatures of `@tool`-decorated
  functions in `agent/action_tools.py`. LangChain converts these into
  Pydantic schemas using the type hints (e.g., `pick_object(object_id:
  Optional[str], plan_only: bool)`).
- C++ side: `ActionParams` struct at
  `src/mtc_action_library_core/include/mtc_action_library/action_params.hpp:14`,
  with typed fields (`object_id: string`, `plan_only: bool`,
  `velocity_scaling: double`, `tilt_*`, etc.) plus generic
  `numeric_params` / `string_params` maps for everything else.
- Per-task structs: `PickTaskParams`, `PlaceTaskParams`,
  `MoveToPourTaskParams`, `ReturnTaskParams` in `task_builders.hpp`
  (lines 13–108).

**Type checks:**
- LangChain validates basic Python types via Pydantic *before* invoking
  the tool. Out-of-range numbers, however, are not bounded.
- Python wrapper `ActionLibrary.execute()`
  (`mtc_action_library/action_library.py:63`) accepts arbitrary
  `**kwargs` and silently routes unknown keys into
  `numeric_params` / `string_params` — there is **no schema validation
  of "is this argument actually consumed"**. Misspelled keys are
  silently ignored downstream.
- The JSON `ActionParams::fromJson` (`action_params.hpp:45`) swallows
  any parse error and returns defaults — malformed JSON is silently
  accepted.

**Invalid tool name rejection:**
- ✅ `ActionLibrary::execute` rejects unknown action names with
  `error_code = -1` and `error_msg = "Unknown action: …"`
  (`action_library.cpp:48-53`).

**Malformed argument rejection:** ❌ effectively absent. Wrong types
either coerce (e.g., `bool` → `float`), get dropped, or silently fall
back to defaults.

**Status:** 🟡 partial. Function-signature typing exists; argument
*name* whitelisting and *value* validation do not. 🟢 easy to add a
single Pydantic schema layer in `action_tools.py` that runs before
`lib.execute`.

---

## 3. Scene grounding

**Where detected objects are stored:**
- `agent/scene_manager.py:23` — `SceneState` dataclass holding
  `objects: List[str]`, `object_details: Dict[str, dict]`,
  `robot_holding`, `last_action`.
- Populated by the ROS subscriber `SceneManagerNode.detection_callback`
  (`scene_manager.py:74`), which listens on
  `/object_detection_result` (msg type `mtc_interface/DetectionResult`).
- A second copy lives in the MoveIt PlanningScene, written by
  `setup_planning_scene` (`ros_client_tools.py:341`).

**Object ID representation:** Sequential strings `object_1`, `object_2`,
… assigned by index regardless of class
(`scene_manager.py:84`,`ros_client_tools.py:515`). For non-cup classes
the bridge re-prefixes (`bowl_1`, `bottle_1`, `orange_1`, `apple_1`) at
`ros_client_tools.py:659–676`. **The ID returned to the agent is the
`object_N` form** (only-cup or first-pass naming), but the planning
scene may carry `bowl_N` / `bottle_N` IDs that the agent never sees.
This is a known fragility.

**source_id / target_id checks against current scene objects:** ❌ not
performed by the agent path. `pick_object`, `place_object`,
`move_and_pour` accept *any* string and pass it straight to the C++
task builder, which then queries node parameters
(`place.origin.<object_id>.{x,y,z}`) and falls back silently if
missing. There is a stand-alone helper `check_object_exists`
(`ros_client_tools.py:1004`) and an MCP wrapper
(`mtc_mcp_server.py:148`), but neither is invoked before calling
`pick`/`place`/`move_to_pour`.

**Nonexistent-object rejection:** ❌ not rejected up front. Failure
manifests later as either an MTC planning failure or a "default-pose
fallback" that the operator may not notice.

**Status:** 🟡 ground truth is available (`scene_manager.get_objects`,
`check_object_exists`); the wiring into the verify layer is missing.
🟢 easy to add: a 5-line guard at the top of each `@tool`. Note ID
naming inconsistency (`object_N` vs `bowl_N`) needs to be resolved at
the same time.

---

## 4. Physical parameter bounds

**Where physical parameters are defined:**
- `MoveToPourTaskParams` in
  `src/mtc_action_library_core/include/mtc_action_library/task_builders.hpp:38`:
  `tilt_start_deg = 15`, `tilt_end_deg = 140`, `tilt_speed_deg_s = 25`,
  `pour_hold_sec = 2.0`, `velocity_scaling = 0.15`,
  `acceleration_scaling = 0.3`, `min_cartesian_fraction = 0.85`,
  `gripper_open_ratio = 1.0`, `step_size = 0.008`, `timeout_sec = 60`.
- `PickTaskParams` (`task_builders.hpp:13`):
  `approach_min/max = 0.05/0.15`, `lift_height = 0.12`,
  `safe_approach_height = 0.18`.
- `PlaceTaskParams`: `lower_min/max`, `retreat_min/max`.
- `ActionParams` defaults (`action_params.hpp:14`): `planner_timeout`,
  `ik_timeout`, `cartesian_step_size`, `connect_timeout`, etc.
- The agent system prompt (`agent/agent_app.py:166`) advertises
  `velocity_scaling: 0.05-0.3` — but this is a soft hint to the LLM,
  not enforced.

**Bounds checking before execution:** ❌ none. The numeric fields are
copied into `numeric_params` and consumed downstream as-is. The agent
could send `tilt_end_deg = 720` or `velocity_scaling = 5.0` and the
code would forward it.

**Material-dependent bounds:** ❌ not modeled. Geometry-fitted radius/
height per object exists (`scene_manager.object_details[*]
.fitted_height/fitted_radius`), but there is no "max tilt for a bowl"
or "max speed when carrying a fragile cup" table anywhere.

**Status:** ❌ missing. 🟢 easy to add: a single
`PHYSICAL_BOUNDS = {key: (lo, hi)}` table + `assert_in_bounds(...)`
helper, optionally indexed by `class_name`.

---

## 5. Task-state preconditions

**Tracked state:** `SceneManager` keeps
`robot_holding: Optional[str]` and `last_action: Optional[str]`
(`scene_manager.py:209,215`). Mutators are
`update_robot_holding(...)`, `clear_robot_holding()`,
`set_last_action(...)`.

**What is enforced today:**
- `place_object` *does* check `if not holding and not object_id:`
  and refuses with "机器人没有抓取任何物体" (`action_tools.py:217`).
  ✅ This is the only proper precondition guard.
- `move_and_pour` only **warns** if the gripper is empty
  (`action_tools.py:277`); it still executes.
- `pick_object` does **not** check whether the gripper is already
  holding something, so a second pick silently overwrites the
  bookkeeping entry without ungrasping.
- After-success bookkeeping: `pick` calls `update_robot_holding(id)`
  (line 176) when not in plan-only mode; `place` calls
  `clear_robot_holding()` (line 234). That side of the state machine
  is fine.

**Wrong-order blocks:**
- pour-before-grasp: 🟡 warns only.
- place-without-holding: ✅ blocked.
- pick-while-holding: ❌ allowed.
- return_home / move_and_pour: no precondition.

**Status:** 🟡 partial. The state vector is right; the guard logic is
ad-hoc and lives only inside the LangChain wrappers (the C++ side has
no awareness). 🟢 easy to add: a `Preconditions.check(action,
state) -> Result` helper invoked uniformly at the top of every tool.

---

## 6. MTC motion verification

**Where MoveIt/MTC planning is called:**
- `ActionLibrary::Impl::execute` in
  `src/mtc_action_library_core/src/action_library.cpp:38`:
  `task.init()` → `task.plan(params.max_solutions)` →
  `task.execute(*solution)`.
- All four task builders (`build_pick_task`, `build_place_task`,
  `build_move_to_pour_task`, `build_return_task`) live in
  `task_builders.cpp`.

**plan_only mode:** ✅ exists.
- C++ side: `params.plan_only` short-circuits the executor branch
  (`action_library.cpp:122-148`) — it still runs `init()` + `plan()`,
  reports `num_solutions`, but skips `task.execute(...)`.
- Python side: `_effective_plan_only(plan_only)`
  (`action_tools.py:35`) honors a `plan_only=True` argument *and* the
  global env var `AGENT_DRY_RUN`.
- Launch-time entry point: `scripts/plan_only/launch_plan_only.sh`,
  `src/mtc_tutorial/launch/plan_only_demo.launch.py`.

**Reachability / joint-limit / collision failure detection:** 🟡
partial.
- The `plan()` call returns a `MoveItErrorCodes` value which is stored
  in `result.error_code` (`action_library.cpp:112`). MoveIt does
  distinguish `PLANNING_FAILED` / `INVALID_MOTION_PLAN` /
  `GOAL_IN_COLLISION` / `GOAL_CONSTRAINTS_VIOLATED` / `TIMED_OUT` /
  `NO_IK_SOLUTION` etc., so the *raw code* is preserved.
- However, `result.error_msg` is hard-coded to `"Planning failed"` —
  no human-readable mapping. The Python `ActionResult` carries
  `error_code: int` but neither the agent nor the logger translates it.
- There is no per-stage diagnostic ("failed at IK stage of grasp pose"
  vs "failed at Cartesian retreat"). `stage_feedback` carries only
  high-level messages like "Planning succeeded with N solutions".

**Failure logging:**
- ✅ Every execution is appended to `execution_log_` with
  `{timestamp, action_name, success, duration_sec, error_msg}`
  (`action_library.cpp:373`, capped at 1000 entries).
- ✅ `exportDebugReport(filepath)` (line 202) writes statistics +
  full history to JSON.

**Status:** 🟡. Verification call pattern is correct; the failure
*classification* the paper needs (reachability vs joint-limit vs
collision) is technically available in `error_code` but not surfaced.
🟢 easy to add: an enum→string mapper of `MoveItErrorCodes` plus
optional per-stage hooks via `task.stages()` traversal. 🔴 attaching
*pre-flight* reachability/collision checks (without a full MTC plan)
would require a separate `moveit::core::PlanningSceneMonitor` pass and
is meaningfully harder.

---

## 7. setup_scene: detections → collision primitives

**Conversion path:**
1. `object_single_shot_detection.py` runs YOLO (line 137), extracts a
   per-object point cloud, and calls
   `pointcloud_fitter.fit_cylinder_6d_pose(...)` (line 472) producing
   `fitted_height`, `fitted_radius`, plus a 6D pose. Results are
   transformed to `link_base` and published as
   `mtc_interface/DetectionResult` on `/object_detection_result`.
2. `detection_to_planning_scene.py` filters by class + confidence
   (`min_confidence=0.3`, `allowed_classes=[cup, bowl, bottle, orange,
   apple]`) and calls `setup_planning_scene`.
3. `setup_planning_scene` (`ros_client_tools.py:341`) constructs
   `moveit_msgs/CollisionObject`s and applies them via
   `/apply_planning_scene` service.

**Geometry approximations** (`ros_client_tools.py:692–852`):
| Class | Primitive | Default `[height, radius]` (m) | Z default |
|---|---|---|---|
| table_surface | BOX `[1.0, 1.5, 0.01]` | — | -0.01 |
| cup | CYLINDER | `[0.10, 0.02]` (or fitted) | from detection |
| bowl | CYLINDER | `[0.07, 0.04]` | 0.0 |
| bottle | CYLINDER | `[0.15, 0.025]` | 0.13 |
| orange | CYLINDER (sphere proxy) | `[0.07, 0.02]` | 0.05 |
| apple | CYLINDER (sphere proxy) | `[0.07, 0.035]` | 0.05 |
| no_go_wall (optional) | BOX | from `wall_*` params | center |

The 6D orientation from cylinder fitting is propagated only for `cup`
(`ros_client_tools.py:713-719`); other classes are forced to the
identity quaternion. Spherical fruit are *not* approximated as MoveIt
`SPHERE` primitives — they are short cylinders, which over-estimates
collision footprint along one axis.

**Centroids and transforms:** Computed inside the detection node — the
fitter returns a centroid in camera frame, then a TF lookup converts
to `link_base` and stores it as `o.position_base`
(consumed at `ros_client_tools.py:511`). Setup node trusts
`transform_valid` flag and falls back to camera frame if absent.

**What the paper should call "approximate planning scene":**
- All graspables collapsed to upright cylinders;
- Default per-class fallback dimensions when geometry-fitting is not
  available (cup falls back to 10 cm × 2 cm; bottle to 15 cm ×
  2.5 cm);
- Identity orientation for all classes except cup;
- Hard-coded table BOX of 1.0 m × 1.5 m × 1 cm;
- Apples/oranges treated as cylinders, not spheres.

**Status:** ✅ exists end-to-end; honest description for the paper is
straightforward.

---

## 8. Recovery

**Existing safe-pose recovery:** `abort_and_reset(...)` in
`src/mtc_tutorial/scripts/ros_client_tools.py:2150` (~150 lines).
- Cancels the active `/execute_pour` action via the
  `ABORT_REQUEST` poison-goal pattern.
- Sends a `MoveGroup` joint-space goal to
  `[0,0,0,0,0,0]` (UF850 home, line 2246) at 0.3 velocity scaling.
- Surfaced as MCP tool `abort_and_reset` (`mtc_mcp_server.py:576`).
- ❌ **Not wired into the LangGraph agent** — `action_tools.py`
  contains no recovery tool, and the agent system prompt does not
  describe one.

**Retry logic:** in `agent/task_graph.py:34` — the deterministic
LangGraph FSM has a 3-attempt retry policy with a yes/no human prompt
between attempts 2 and 3. The interactive `agent_app.py` path has no
retry (the LLM has to decide).

**Status:** 🟡 components exist but are not orchestrated as a
"safe-pose recovery on verification failure". 🟢 easy to add: expose
`abort_and_reset` as a LangChain tool, and call it from within
`_call_action_with_retry` after the third failed attempt.

---

## 9. Baseline support

| Baseline | Status | How to run |
|---|---|---|
| Direct LLM-to-action (raw motion params from LLM) | ❌ blocked by design | The system prompt explicitly forbids the LLM from emitting coordinates / quaternions / joint angles (`agent_app.py:155-164`). Allowing this would require a new tool whose schema accepts a `Pose`. |
| LLM + JSON / function calling only | 🟡 partial | The LangChain agent in `agent_app.py` already operates this way *if* we strip the scene-grounding hints. Trivial to fork into an "ablation" prompt. |
| No scene check | 🟢 easy | Toggle a flag that skips the (yet-to-be-built) scene-grounding guard. |
| No task precondition check | 🟢 easy | Toggle a flag that skips precondition guard. |
| No MTC verification | 🔴 hard | Real execution still goes through MTC; truly "no MTC" means bypassing `task.plan()` and driving the controller directly, which the current code path does not support. Could be approximated by `plan_only=False, max_solutions=1, planner_timeout=0.1` to make planning effectively a no-op rubber-stamp. |
| Hand-coded FSM / BT | ✅ implemented | `agent/task_graph.py` (`build_main_graph`) is a deterministic 4-node LangGraph: `resolve_and_choose_plan → do_pick → do_move_to_pour → do_place → do_return`. Templates `P1`/`P2`/`P3` chosen by regex. This *is* the FSM baseline. |
| Full SG-VTA | ❌ to be built | Schema/grounding/bounds/precondition/MTC layers don't yet wrap a single uniform call site. |

The deterministic action library at
`src/mtc_action_library_py/mtc_action_library/action_library.py:45` is
also documented in `docs/ACTION_LIBRARY.md` as a "paper baseline … a
deterministic, LLM-free way to exercise the same task pipeline".

**Status:** 🟡. We have FSM and a function-calling agent end-to-end;
the *ablation flags* needed to produce the table the paper requires
have to be added.

---

## 10. Metrics and logging

**Currently captured (per-action, in C++):**
- `ActionStats` (`action_stats.hpp` and
  `src/mtc_action_library_core/src/action_stats.cpp`):
  `total_executions`, `successful_executions`, `total_duration_sec`,
  `average_duration_sec`, `success_rate`, `last_execution_time`.
- `ExecutionLog` per call: timestamp, action name, success, duration,
  `error_msg`.
- `exportDebugReport(filepath)` writes the lot to JSON.
- Python wrapper exposes `get_stats`, `get_history`, `debug_export`.

**Currently captured (Python side):**
- LangGraph FSM emits `tool_attempt`, `tool_result`, `auto_retry`,
  `user_decision_needed`, `step_starting`, `feedback`, `execution_plan`
  events through a `reporter` callback (`task_graph.py`). These are
  printed to stdout by default; they are *not* persisted.
- `agent_app.py` writes a JSON-line debug log to a hard-coded path
  `/home/wenhao/uf_custom_ws/.cursor/debug.log`
  (lines 219, 232, 240, 247, 252, 266, 274, 376, 387, 396, 404). This
  is developer instrumentation, not an experiment log, and the path
  will not exist on the reviewer's machine.

**Specifically required by the paper:**

| Metric | Currently logged? |
|---|---|
| Rejected tool calls | ❌ — there is no reject layer yet, so nothing emits rejection events. |
| Rejection reason (which of the five layers fired) | ❌ — same. |
| Planning failures | 🟡 — captured as `success=False, error_msg="Planning failed", error_code=<MoveIt enum>` in `ExecutionLog`, but not split by failure type. |
| Spills | ❌ — no spill detector exists. Would need either a force/torque threshold on the pour stage or a vision check. 🔴 hard. |
| Emergency stops | 🟡 — `abort_and_reset` runs but does not increment a counter or write a log entry. |
| Safe-pose recoveries | 🟡 — same as emergency stops (count is recoverable from log lines but not aggregated). |
| Verification time | ❌ — nothing measures the per-layer overhead of the (not-yet-built) verify pipeline. The total `duration_sec` exists, planning vs execution split does not. |

**Status:** 🟡. Action-level success/duration stats are solid; the
verify-layer-specific instrumentation (rejections, per-layer cost, spill,
e-stop counts) has to be added *together with* the verify layers
themselves. 🟢 easy to add per-layer counters; 🔴 spill detection is a
research task in itself — recommend deferring or doing a Wizard-of-Oz
annotation.

---

## Cross-cutting observations

1. **Two parallel agent surfaces.** `agent/action_tools.py` (LangChain,
   used by `agent_app.py` and `task_graph.py`) and
   `src/mtc_tutorial/scripts/mtc_mcp_server.py` (FastMCP, with richer
   guard-rail tools like `check_object_exists` and
   `abort_and_reset`). The paper should pick one and prune the other,
   or explicitly position them as "interactive vs MCP".
2. **Object-ID schema drift.** `scene_manager` exposes `object_N`,
   while the planning scene may carry `bowl_N` / `bottle_N`. A
   grounding guard has to know about both.
3. **Hard-coded debug log path.** `agent_app.py` writes to
   `/home/wenhao/uf_custom_ws/.cursor/debug.log` unconditionally and
   will crash on any other machine. This must be fixed before the
   reviewer artifact ships.
4. **JSON parse silently swallows errors** in `ActionParams::fromJson`
   (`action_params.hpp:61`). For SG-VTA's "schema validation" claim
   this needs to *raise* on malformed input.

---

## Minimum code tasks before paper submission

Ordered roughly by dependency and effort. Paths refer to the *target*
file for the change; sizes are rough LoC budgets.

1. **Add a `safety_layer.py` module** under `agent/` (~250 LoC).
   Implements five guards as plain functions returning a structured
   `Verdict(passed: bool, reason: str, layer: str)`:
   - `validate_schema(tool_name, args)` — Pydantic schema per tool.
   - `validate_scene(args, scene_state)` — `object_id` ∈
     `scene.get_objects()`.
   - `validate_bounds(tool_name, args)` — table of
     `(param, lo, hi[, class_name])`.
   - `validate_preconditions(tool_name, scene_state)` —
     pick-while-empty, place-while-holding, pour-while-holding, etc.
   - `validate_motion(tool_name, args)` — wraps `lib.execute(...,
     plan_only=True)` and inspects `error_code`.

2. **Wrap every action in `agent/action_tools.py`** with the verify
   layer (~80 LoC of edits). Each `@tool` becomes:
   ```python
   verdict = run_safety_layer(tool, args, scene)
   if not verdict.passed:
       log_rejection(verdict)
       return f"❌ Rejected ({verdict.layer}): {verdict.reason}"
   # … then the existing lib.execute(...) call
   ```

3. **Add a rejection log** (`agent/verify_metrics.py`, ~80 LoC):
   in-memory ring buffer + JSONL append, with helpers
   `log_rejection`, `log_planning_failure`, `log_recovery`,
   `log_estop`, plus `record_layer_latency(layer, ms)`. Replace the
   hard-coded `/home/wenhao/...` path in `agent_app.py` with this.

4. **Surface `MoveItErrorCodes` as text** in `action_library.cpp`
   (~30 LoC). Map `error_code` → `error_msg` so the paper can quote
   "rejected: kinematics → NO_IK_SOLUTION" instead of "Planning
   failed". Mirror the mapping in
   `mtc_action_library/action_library.py`.

5. **Expose `abort_and_reset` and `setup_scene` as LangChain tools**
   in `action_tools.py` (~60 LoC). Wire `abort_and_reset` into the
   `task_graph.py` retry loop after the third failure.

6. **Add ablation flags** (`agent/agent_app.py`,
   `agent/task_graph.py`, ~40 LoC):
   `--ablate=schema|grounding|bounds|preconditions|motion|none|all`.
   Use these to populate the baseline columns of the paper.

7. **Document the "approximate planning scene"** assumptions
   (cylinder-only, identity orientation for non-cup, fixed
   table BOX, fitted-vs-default fallback) — reuse the table in
   §7 above as a paper subsection. No code change.

8. **Optional but recommended:** add a `preflight_reachability(pose)`
   wrapper that calls
   `moveit::core::RobotState::setFromIK(...)` once before invoking
   the full MTC plan, and treats failure as a layer-5 rejection
   distinct from a real planning failure (~150 LoC, C++ side). This
   is what lets the paper claim "we reject infeasible calls **before**
   committing planner time". Skip if time is tight; the existing
   `plan_only=True` round-trip is a defensible substitute.

9. **Optional spill / e-stop bookkeeping:** at minimum, increment
   counters from `abort_and_reset` and from a manual operator-flag
   tool (~20 LoC). Real spill detection is out of scope.

Estimated total: ~700 LoC of net additions, no risky refactors. Items
1–6 are sufficient to support every claim in the proposed framing.
