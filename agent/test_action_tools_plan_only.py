import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


class ToolWrapper:
    def __init__(self, fn):
        self.fn = fn
        self.name = fn.__name__
        self.description = fn.__doc__ or ""

    def invoke(self, tool_input):
        return self.fn(**tool_input)

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class FakeResult:
    success = True
    duration_sec = 0.01
    error_msg = ""


class FakeScene:
    def __init__(self):
        self.robot_holding = "object_1"
        self.last_action = None
        self.update_robot_holding = Mock()
        self.clear_robot_holding = Mock()

    def get_robot_holding(self):
        return self.robot_holding

    def set_last_action(self, action):
        self.last_action = action


class ActionToolsPlanOnlyTest(unittest.TestCase):
    def setUp(self):
        self.repo_agent_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(self.repo_agent_dir))

        self.fake_lib = Mock()
        self.fake_lib.execute.return_value = FakeResult()
        self.fake_scene = FakeScene()

        langchain_core = types.ModuleType("langchain_core")
        langchain_tools = types.ModuleType("langchain_core.tools")
        langchain_tools.tool = lambda fn: ToolWrapper(fn)
        sys.modules["langchain_core"] = langchain_core
        sys.modules["langchain_core.tools"] = langchain_tools

        mtc_action_library = types.ModuleType("mtc_action_library")
        mtc_action_library.get_action_library = lambda: self.fake_lib
        sys.modules["mtc_action_library"] = mtc_action_library

        scene_manager = types.ModuleType("scene_manager")
        scene_manager.get_scene_manager = lambda: self.fake_scene
        sys.modules["scene_manager"] = scene_manager

        sys.modules.pop("action_tools", None)
        os.environ.pop("AGENT_DRY_RUN", None)
        self.action_tools = importlib.import_module("action_tools")

    def tearDown(self):
        os.environ.pop("AGENT_DRY_RUN", None)
        sys.modules.pop("action_tools", None)
        if str(self.repo_agent_dir) in sys.path:
            sys.path.remove(str(self.repo_agent_dir))

    def test_default_direct_execution_keeps_plan_only_false(self):
        self.action_tools.pick_object.invoke({"object_id": "object_1"})

        self.fake_lib.execute.assert_called_once_with(
            "pick", object_id="object_1", plan_only=False
        )
        self.fake_scene.update_robot_holding.assert_called_once_with("object_1")

    def test_explicit_plan_only_true_is_forwarded(self):
        self.action_tools.pick_object.invoke({
            "object_id": "object_1",
            "plan_only": True,
        })

        self.fake_lib.execute.assert_called_once_with(
            "pick", object_id="object_1", plan_only=True
        )
        self.fake_scene.update_robot_holding.assert_not_called()

    def test_dry_run_forces_plan_only(self):
        os.environ["AGENT_DRY_RUN"] = "true"

        self.action_tools.return_home.invoke({})

        self.fake_lib.execute.assert_called_once_with("return_home", plan_only=True)


if __name__ == "__main__":
    unittest.main()
