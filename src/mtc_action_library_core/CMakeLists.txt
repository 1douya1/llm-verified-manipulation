cmake_minimum_required(VERSION 3.8)
project(mtc_action_library_core)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(moveit_task_constructor_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)

# 创建共享库（供Python绑定使用）
add_library(${PROJECT_NAME} SHARED
  src/action_library.cpp
  src/action_stats.cpp
  src/task_builders.cpp
)

target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>
)

target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)

ament_target_dependencies(${PROJECT_NAME}
  rclcpp
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  tf2_eigen
  tf2_geometry_msgs
  geometry_msgs
)

target_link_libraries(${PROJECT_NAME}
  nlohmann_json::nlohmann_json
)

# 导出头文件和库
install(DIRECTORY include/
  DESTINATION include/${PROJECT_NAME}
)

install(TARGETS ${PROJECT_NAME}
  EXPORT ${PROJECT_NAME}Targets
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# 导出CMake配置（供其他包使用）
ament_export_targets(${PROJECT_NAME}Targets HAS_LIBRARY_TARGET)
ament_export_dependencies(
  rclcpp
  moveit_task_constructor_core
  moveit_ros_planning_interface
  moveit_ros_planning
  tf2_eigen
  tf2_geometry_msgs
  geometry_msgs
  nlohmann_json
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()








