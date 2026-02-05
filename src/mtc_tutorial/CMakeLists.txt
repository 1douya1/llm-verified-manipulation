cmake_minimum_required(VERSION 3.8)
project(mtc_tutorial)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(moveit_task_constructor_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(mtc_interface REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)

add_executable(mtc_tutorial src/mtc_tutorial.cpp)
ament_target_dependencies(mtc_tutorial 
  moveit_task_constructor_core 
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp 
  tf2_eigen
  tf2_geometry_msgs
)


target_include_directories(mtc_tutorial PUBLIC
$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
$<INSTALL_INTERFACE:include>)
target_compile_features(mtc_tutorial PUBLIC c_std_99 cxx_std_17)


install(TARGETS mtc_tutorial
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch 
  DESTINATION share/${PROJECT_NAME})

install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME})

# Install Python scripts
install(PROGRAMS
  scripts/mtc_mcp_server.py
  scripts/ros_client_tools.py
  scripts/charuco_pose_publisher.py
  scripts/object_single_shot_detection.py
  # scripts/object_florence_visual_detection.py  # File not included in minimal repo
  scripts/object_marker_publisher.py
  scripts/detection_to_planning_scene.py
  scripts/spawn_demo_scene.py
  DESTINATION lib/${PROJECT_NAME}
)
# Install test scripts (placeholder)
install(PROGRAMS
  DESTINATION lib/${PROJECT_NAME}
)
  

if(BUILD_TESTING)
find_package(ament_lint_auto REQUIRED)
ament_lint_auto_find_test_dependencies()
endif()

ament_package()

# Add reusable task builder library
add_library(pour_task_builder
  src/pour_task_builder.cpp
)
target_include_directories(pour_task_builder PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(pour_task_builder
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
  tf2_eigen
  tf2_geometry_msgs
)

# Add modular task builder library (for split action tools)
add_library(modular_task_builders
  src/modular_task_builders.cpp
)
target_include_directories(modular_task_builders PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(modular_task_builders
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
  tf2_eigen
  tf2_geometry_msgs
)
target_link_libraries(modular_task_builders pour_task_builder)

# Server executable linked to library
add_executable(execute_pour_server src/execute_pour_server.cpp)
ament_target_dependencies(execute_pour_server
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
  rclcpp_action
  tf2_eigen
  tf2_geometry_msgs
  mtc_interface
)
target_include_directories(execute_pour_server PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(execute_pour_server pour_task_builder)

target_compile_features(execute_pour_server PUBLIC c_std_99 cxx_std_17)

# Modular task builder test program
add_executable(test_modular_tasks src/test_modular_tasks.cpp)
ament_target_dependencies(test_modular_tasks
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
)
target_include_directories(test_modular_tasks PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(test_modular_tasks modular_task_builders)

target_compile_features(test_modular_tasks PUBLIC c_std_99 cxx_std_17)

# Add pre-pour builder test program
add_executable(test_pre_pour src/test_pre_pour.cpp)
ament_target_dependencies(test_pre_pour
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
)
target_include_directories(test_pre_pour PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
# 直接链接 modular_task_builders 库
target_link_libraries(test_pre_pour modular_task_builders)

target_compile_features(test_pre_pour PUBLIC c_std_99 cxx_std_17)

# Modular task execution server (using existing ExecutePour Action interface)
add_executable(modular_task_server src/modular_task_server.cpp)
ament_target_dependencies(modular_task_server
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  rclcpp
  rclcpp_action
  tf2_eigen
  tf2_geometry_msgs
  mtc_interface
)
target_include_directories(modular_task_server PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(modular_task_server modular_task_builders)

target_compile_features(modular_task_server PUBLIC c_std_99 cxx_std_17)

# Generic MTC task execution server (temporarily commented, testing modular task builders first)
# add_executable(execute_task_server src/execute_task_server.cpp)
# ament_target_dependencies(execute_task_server
#   moveit_task_constructor_core
#   moveit_ros_planning_interface
#   moveit_ros_planning
#   rclcpp
#   rclcpp_action
#   tf2_eigen
#   tf2_geometry_msgs
#   mtc_interface
# )
# target_include_directories(execute_task_server PUBLIC
#   $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
#   $<INSTALL_INTERFACE:include>)
# target_link_libraries(execute_task_server modular_task_builders nlohmann_json::nlohmann_json)
# 
# target_compile_features(execute_task_server PUBLIC c_std_99 cxx_std_17)

install(TARGETS execute_pour_server test_modular_tasks modular_task_server pour_task_builder modular_task_builders
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)
# Install test_pre_pour executable
install(TARGETS test_pre_pour
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)