#include <rclcpp/rclcpp.hpp>
#include <mtc_tutorial/modular_task_builders.hpp>
#include <moveit_msgs/msg/move_it_error_codes.hpp>

#include <chrono>
#include <string>

/**
 * Test program for modular MTC task builders.
 *
 * Default: plan AND execute a complete pick -> pour -> place -> return workflow
 *          on the fake (or real) controllers managed by move_group.
 *
 * Usage:
 *   ros2 run mtc_tutorial test_modular_tasks              # plan + execute
 *   ros2 run mtc_tutorial test_modular_tasks --plan-only   # plan only (no execution)
 *
 * Prerequisites:
 *   The plan_only_demo.launch.py (or equivalent) must be running so that
 *   move_group, the planning scene, and fake controllers are available.
 */

// Helper: plan (and optionally execute) a single MTC task.
// Returns true on success.
static bool run_task(
    const rclcpp::Logger& logger,
    const std::string& label,
    moveit::task_constructor::Task& task,
    bool plan_only)
{
    RCLCPP_INFO(logger, "--- %s: initialising ---", label.c_str());
    try {
        task.init();
    } catch (const std::exception& e) {
        RCLCPP_ERROR(logger, "%s: init failed: %s", label.c_str(), e.what());
        return false;
    }

    RCLCPP_INFO(logger, "--- %s: planning ---", label.c_str());
    auto t0 = std::chrono::steady_clock::now();
    if (!task.plan(5 /* max solutions */)) {
        RCLCPP_ERROR(logger, "%s: planning failed (no valid solution found)", label.c_str());
        return false;
    }
    auto t1 = std::chrono::steady_clock::now();
    double plan_sec = std::chrono::duration<double>(t1 - t0).count();
    RCLCPP_INFO(logger, "%s: planning succeeded -- %zu solution(s), %.2fs",
                label.c_str(), task.solutions().size(), plan_sec);

    if (plan_only) {
        RCLCPP_INFO(logger, "%s: --plan-only mode, skipping execution", label.c_str());
        return true;
    }

    RCLCPP_INFO(logger, "--- %s: executing ---", label.c_str());
    auto t2 = std::chrono::steady_clock::now();
    const auto& solution = *task.solutions().front();
    auto exec_result = task.execute(solution);
    auto t3 = std::chrono::steady_clock::now();
    double exec_sec = std::chrono::duration<double>(t3 - t2).count();

    if (exec_result.val != moveit_msgs::msg::MoveItErrorCodes::SUCCESS) {
        RCLCPP_ERROR(logger, "%s: execution failed (MoveIt error code %d), %.2fs",
                     label.c_str(), exec_result.val, exec_sec);
        return false;
    }

    RCLCPP_INFO(logger, "%s: execution succeeded, %.2fs", label.c_str(), exec_sec);
    return true;
}

int main(int argc, char** argv) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("test_modular_tasks");

    // Parse --plan-only flag
    bool plan_only = false;
    for (int i = 1; i < argc; ++i) {
        if (std::string(argv[i]) == "--plan-only") {
            plan_only = true;
        }
    }

    auto logger = node->get_logger();
    RCLCPP_INFO(logger, "========================================");
    RCLCPP_INFO(logger, "  MTC Modular Tasks Demo");
    RCLCPP_INFO(logger, "  Mode: %s", plan_only ? "PLAN ONLY" : "PLAN + EXECUTE");
    RCLCPP_INFO(logger, "========================================");

    int successes = 0;
    int failures  = 0;

    try {
        // ================================================================
        // Step 1: PICK -- grab the cup from the table
        // ================================================================
        RCLCPP_INFO(logger, "\n====== Step 1/4: PICK ======");
        {
            mtc_tutorial::PickTaskParams params;
            params.object_id = "object";           // matches demo_scene.yaml cup id
            params.plan_only = plan_only;

            auto task = mtc_tutorial::build_pick_task(node, params);
            RCLCPP_INFO(logger, "Pick task built: %s (%zu stages)",
                        task.stages()->name().c_str(), task.stages()->numChildren());

            if (run_task(logger, "PICK", task, plan_only)) {
                ++successes;
            } else {
                ++failures;
                RCLCPP_WARN(logger, "PICK failed -- subsequent steps may also fail");
            }
        }

        // ================================================================
        // Step 2: POUR -- move above the bowl and pour
        // ================================================================
        RCLCPP_INFO(logger, "\n====== Step 2/4: POUR ======");
        {
            mtc_tutorial::MoveToPourTaskParams params;
            // Target: above the bowl (bowl is at [0.15, -0.45, 0.05] in demo_scene.yaml)
            params.target_x = 0.15;
            params.target_y = -0.45;
            params.target_z = 0.25;   // above the bowl
            // Use defaults for pouring action
            params.pour_execute = true;       // execute tilt sequence after reaching position
            // tilt_start_deg  = 15.0  (default)
            // tilt_end_deg    = 140.0 (default)
            // tilt_speed_deg_s = 25.0 (default)
            // pour_hold_sec   = 2.0   (default)
            params.plan_only = plan_only;

            auto task = mtc_tutorial::build_move_to_pour_task(node, params);
            RCLCPP_INFO(logger, "Pour task built: %s (%zu stages)",
                        task.stages()->name().c_str(), task.stages()->numChildren());

            if (run_task(logger, "POUR", task, plan_only)) {
                ++successes;
            } else {
                ++failures;
                RCLCPP_WARN(logger, "POUR failed -- continuing to PLACE");
            }
        }

        // ================================================================
        // Step 3: PLACE -- put the cup back down
        // ================================================================
        RCLCPP_INFO(logger, "\n====== Step 3/4: PLACE ======");
        {
            mtc_tutorial::PlaceTaskParams params;
            params.object_id = "object";
            params.plan_only = plan_only;
            // Place back near the original position
            geometry_msgs::msg::Pose target;
            target.position.x = 0.0;
            target.position.y = -0.40;
            target.position.z = 0.10;
            target.orientation.w = 1.0;
            params.target_pose = target;

            auto task = mtc_tutorial::build_place_task(node, params);
            RCLCPP_INFO(logger, "Place task built: %s (%zu stages)",
                        task.stages()->name().c_str(), task.stages()->numChildren());

            if (run_task(logger, "PLACE", task, plan_only)) {
                ++successes;
            } else {
                ++failures;
            }
        }

        // ================================================================
        // Step 4: RETURN -- move arm back to home configuration
        // ================================================================
        RCLCPP_INFO(logger, "\n====== Step 4/4: RETURN ======");
        {
            mtc_tutorial::ReturnTaskParams params;
            params.plan_only = plan_only;
            params.timeout_sec = 15.0;

            auto task = mtc_tutorial::build_return_task(node, params);
            RCLCPP_INFO(logger, "Return task built: %s (%zu stages)",
                        task.stages()->name().c_str(), task.stages()->numChildren());

            if (run_task(logger, "RETURN", task, plan_only)) {
                ++successes;
            } else {
                ++failures;
            }
        }

        // ================================================================
        // Summary
        // ================================================================
        RCLCPP_INFO(logger, "\n========================================");
        RCLCPP_INFO(logger, "  Demo complete -- %d/%d steps succeeded",
                    successes, successes + failures);
        if (failures == 0) {
            RCLCPP_INFO(logger, "  ALL STEPS PASSED");
        } else {
            RCLCPP_WARN(logger, "  %d step(s) FAILED", failures);
        }
        RCLCPP_INFO(logger, "========================================");

    } catch (const std::exception& e) {
        RCLCPP_ERROR(logger, "Unhandled exception: %s", e.what());
        rclcpp::shutdown();
        return 1;
    }

    rclcpp::shutdown();
    return failures == 0 ? 0 : 1;
}
