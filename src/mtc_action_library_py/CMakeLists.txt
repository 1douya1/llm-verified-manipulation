cmake_minimum_required(VERSION 3.8)
project(mtc_action_library_py)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(mtc_action_library_core REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclpy REQUIRED)

# Find Python
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# Find pybind11
find_package(pybind11 REQUIRED)

# pybind11 module
add_library(_mtc_action_library_core MODULE src/bindings.cpp)

target_include_directories(_mtc_action_library_core PRIVATE
  ${Python3_INCLUDE_DIRS}
  ${pybind11_INCLUDE_DIRS}
)

target_link_libraries(_mtc_action_library_core PRIVATE
  mtc_action_library_core::mtc_action_library_core
  ${Python3_LIBRARIES}
  pybind11::module
)

ament_target_dependencies(_mtc_action_library_core PUBLIC
  rclcpp
)

set_target_properties(_mtc_action_library_core PROPERTIES
  PREFIX "${PYTHON_MODULE_PREFIX}"
  SUFFIX "${PYTHON_MODULE_EXTENSION}"
  CXX_STANDARD 17
)

# Install pybind11 module
install(TARGETS _mtc_action_library_core
  DESTINATION lib/python3.10/site-packages/mtc_action_library
)

# Install Python package files
install(DIRECTORY mtc_action_library/
  DESTINATION lib/python3.10/site-packages/mtc_action_library
  FILES_MATCHING PATTERN "*.py"
)

# Install setup files
install(FILES
  resource/${PROJECT_NAME}
  DESTINATION share/${PROJECT_NAME}/resource
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

