#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>
#include <mtc_action_library/action_library.hpp>
#include <mtc_action_library/action_result.hpp>
#include <mtc_action_library/action_params.hpp>
#include <mtc_action_library/action_stats.hpp>

namespace py = pybind11;
using namespace mtc_action_library;

PYBIND11_MODULE(_mtc_action_library_core, m) {
    m.doc() = "MTC Action Library - Python bindings";
    
    // ActionResult
    py::class_<ActionResult>(m, "ActionResult")
        .def(py::init<>())
        .def_readwrite("success", &ActionResult::success)
        .def_readwrite("duration_sec", &ActionResult::duration_sec)
        .def_readwrite("error_msg", &ActionResult::error_msg)
        .def_readwrite("error_code", &ActionResult::error_code)
        .def_readwrite("stage_feedback", &ActionResult::stage_feedback)
        .def_readwrite("num_solutions", &ActionResult::num_solutions)
        .def_readwrite("planning_time_breakdown", &ActionResult::planning_time_breakdown)
        .def("to_json", &ActionResult::toJson, "Convert to JSON")
        .def("to_string", &ActionResult::toString, "Convert to string")
        .def("__str__", &ActionResult::toString)
        .def("__repr__", [](const ActionResult& r) {
            return "<ActionResult success=" + std::string(r.success ? "True" : "False") + 
                   " duration=" + std::to_string(r.duration_sec) + "s>";
        });
    
    // ActionParams
    py::class_<ActionParams>(m, "ActionParams")
        .def(py::init<>())
        .def_readwrite("object_id", &ActionParams::object_id)
        .def_readwrite("numeric_params", &ActionParams::numeric_params)
        .def_readwrite("string_params", &ActionParams::string_params)
        .def_readwrite("plan_only", &ActionParams::plan_only)
        // Task级别参数
        .def_readwrite("max_solutions", &ActionParams::max_solutions)
        // Planner级别参数
        .def_readwrite("planner_timeout", &ActionParams::planner_timeout)
        .def_readwrite("velocity_scaling", &ActionParams::velocity_scaling)
        .def_readwrite("acceleration_scaling", &ActionParams::acceleration_scaling)
        // IK级别参数
        .def_readwrite("max_ik_solutions", &ActionParams::max_ik_solutions)
        .def_readwrite("min_solution_distance", &ActionParams::min_solution_distance)
        .def_readwrite("ik_timeout", &ActionParams::ik_timeout)
        // Cartesian级别参数
        .def_readwrite("cartesian_step_size", &ActionParams::cartesian_step_size)
        .def_readwrite("cartesian_jump_threshold", &ActionParams::cartesian_jump_threshold)
        // Stage级别参数
        .def_readwrite("connect_timeout", &ActionParams::connect_timeout)
        // 辅助方法
        .def_static("from_json", &ActionParams::fromJson, "Create from JSON string")
        .def("to_json", &ActionParams::toJson, "Convert to JSON")
        .def("get_numeric", &ActionParams::getNumeric, 
            py::arg("key"), py::arg("default_value") = 0.0,
            "Get numeric parameter with default")
        .def("get_string", &ActionParams::getString,
            py::arg("key"), py::arg("default_value") = "",
            "Get string parameter with default");
    
    // ActionStats
    py::class_<ActionStats>(m, "ActionStats")
        .def(py::init<>())
        .def_readwrite("action_name", &ActionStats::action_name)
        .def_readwrite("total_executions", &ActionStats::total_executions)
        .def_readwrite("successful_executions", &ActionStats::successful_executions)
        .def_readwrite("total_duration_sec", &ActionStats::total_duration_sec)
        .def_readwrite("average_duration_sec", &ActionStats::average_duration_sec)
        .def_readwrite("success_rate", &ActionStats::success_rate)
        .def_readwrite("last_execution_time", &ActionStats::last_execution_time)
        .def("to_json", &ActionStats::toJson, "Convert to JSON");
    
    // ExecutionLog
    py::class_<ExecutionLog>(m, "ExecutionLog")
        .def(py::init<>())
        .def_readwrite("timestamp", &ExecutionLog::timestamp)
        .def_readwrite("action_name", &ExecutionLog::action_name)
        .def_readwrite("success", &ExecutionLog::success)
        .def_readwrite("duration_sec", &ExecutionLog::duration_sec)
        .def_readwrite("error_msg", &ExecutionLog::error_msg)
        .def("to_json", &ExecutionLog::toJson, "Convert to JSON");
    
    // ActionLibrary - 主要接口
    py::class_<ActionLibrary>(m, "ActionLibrary")
        .def(py::init([](const std::string& node_name) {
            // 确保rclcpp已初始化
            if (!rclcpp::ok()) {
                rclcpp::init(0, nullptr);
            }
            
            // 在C++侧创建rclcpp节点
            rclcpp::NodeOptions options;
            options.automatically_declare_parameters_from_overrides(true);
            auto node = std::make_shared<rclcpp::Node>(node_name, options);
            return new ActionLibrary(node);
        }), py::arg("node_name") = "action_library_node")
        .def("execute", 
            [](ActionLibrary& lib, const std::string& action, 
               const ActionParams& params,
               py::object callback) {
                std::function<void(const std::string&)> cpp_callback = nullptr;
                
                if (!callback.is_none()) {
                    cpp_callback = [callback](const std::string& msg) {
                        py::gil_scoped_acquire acquire;
                        try {
                            callback(msg);
                        } catch (const py::error_already_set& e) {
                            // 忽略Python回调错误
                        }
                    };
                }
                
                py::gil_scoped_release release;  // 释放GIL提高性能
                auto result = lib.execute(action, params, cpp_callback);
                return result;
            },
            py::arg("action_name"),
            py::arg("params"),
            py::arg("feedback_callback") = py::none(),
            "Execute an action synchronously")
        .def("get_action_list", &ActionLibrary::getActionList,
            "Get list of available actions")
        .def("get_stats", &ActionLibrary::getStats,
            py::arg("action_name"),
            "Get statistics for a specific action")
        .def("get_all_stats", &ActionLibrary::getAllStats,
            "Get statistics for all actions")
        .def("get_history", &ActionLibrary::getHistory, 
            py::arg("limit") = 100,
            "Get execution history")
        .def("export_debug_report", &ActionLibrary::exportDebugReport,
            py::arg("filepath"),
            "Export debug report to file")
        .def("clear_history", &ActionLibrary::clearHistory,
            "Clear execution history")
        .def("reset_all_stats", &ActionLibrary::resetAllStats,
            "Reset all statistics");
}

