# Safety Checklist

**Read this document fully BEFORE powering the arm or running any
`--real-robot` script.** Every item below has caused an incident at least
once in development. The list is intentionally terse so you can skim it
before each session.

---

## Before powering on the arm

- [ ] Workspace is clear of coffee mugs, cables, laptops, and humans.
- [ ] The E-stop is within arm's reach of the operator. Test it: press it
      with the arm powered, verify the arm goes limp, then re-arm.
- [ ] The arm is bolted to the table or a heavy base plate. If it isn't,
      stop here.
- [ ] The gripper (or tool) is tight. If you can wiggle it, tighten the
      mounting screws.
- [ ] Nothing is draped over the joint-five range of motion. UF850 joint 5
      has a wide swept volume; easy to forget.

## Before `colcon build`

- [ ] `git submodule update --init --recursive` has been run at least once
      since cloning.
- [ ] You have `source /opt/ros/humble/setup.bash` in the current shell.
      Building under the wrong ROS distribution produces misleading errors.

## Before launching MoveIt

- [ ] Verify the arm is NOT in a state that would collide with itself if
      it moves to the home pose. UF850 can pre-trip a collision if it is
      folded inside itself.
- [ ] `ros2 node list | grep -v "move_group"` to make sure there is no
      stale node from a previous run still holding the controller.

## Before hand-eye calibration

- [ ] The ChArUco board is rigidly attached -- even a 1 mm wiggle will add
      to the RMS error.
- [ ] Lighting is diffuse. Hard shadows across the board cause marker
      detection failures (and bad samples).
- [ ] For eye-to-hand: the camera tripod cannot be bumped during the
      calibration. Tape the legs to the floor if possible.

## Before any motion (plan-only OR real robot)

- [ ] Velocity scaling is at 30 % or below for the FIRST run after any of
      the following: recalibration, new pose set, changed planning scene,
      changed gripper. Crank up only after one clean cycle.
- [ ] The emergency stop is tested AGAIN this session.
- [ ] You can see the arm. If you're looking only at RViz, you're flying
      blind.

## Before enabling the LLM agent

- [ ] Know what actions the agent has access to. A human should review
      `agent/action_tools.py` once before letting the agent drive.
- [ ] The agent's temperature is low (the default in `agent_app.py` is
      0.0); higher temperatures make it likelier to generate surprising
      plans.
- [ ] The conversation log is being captured. `agent/simple_backend.py`
      writes to `~/.rss_logs/` by default.

## During operation

- [ ] One operator has an unobstructed line of sight to the arm and a hand
      on the E-stop at all times. No exceptions.
- [ ] If the MoveIt collision checker logs a WARN about objects being
      inside the robot, stop and investigate -- the planning scene is
      wrong, the arm WILL collide.
- [ ] Do not override safety limits in the controller config to "make the
      plan succeed". Fix the plan instead.

## After a crash (arm hit something unexpectedly)

- [ ] Power-cycle the arm. Do NOT just clear the fault and keep driving --
      the gearbox may have backlash now.
- [ ] Re-zero the joint encoders per UFACTORY's procedure.
- [ ] Re-run the hand-eye calibration before trusting perception again.
- [ ] Inspect the gripper. A crash often loosens the mounting screws.

## Data hygiene

- [ ] Do not commit `~/.ros/easy_handeye2_calibrations/*.calib`,
      `recorded_poses.yaml`, or any file matching
      `**/*camera_intrinsics*.yaml` -- `.gitignore` already blocks these,
      but verify with `git status` before pushing.
- [ ] Do not commit YOLO weights (`*.pt`, `*.pth`, `*.onnx`). The repo
      stays small.

---

If you are unsure whether something is safe, it isn't. Stop, ask, then
proceed.
