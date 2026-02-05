cmake_minimum_required(VERSION 3.8)
project(mtc_interface)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)

# Ensure package.xml is parsed so that *_MEMBER_OF_GROUPS variables are available
ament_package_xml()

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/ExecutePour.action"
  "action/ExecuteTask.action"
  "msg/DetectedObject.msg"
  "msg/DetectionResult.msg"
  DEPENDENCIES
  geometry_msgs
  std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
