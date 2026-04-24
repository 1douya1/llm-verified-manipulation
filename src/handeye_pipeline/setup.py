from glob import glob
from setuptools import find_packages, setup

package_name = "handeye_pipeline"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml", "README.md"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/examples", glob("examples/*.yaml")),
        (f"share/{package_name}/docs", glob("docs/*.md")),
        ("bin", glob("bin/handeye-*")),
    ],
    install_requires=["setuptools", "numpy", "PyYAML"],
    zip_safe=True,
    maintainer="wenhao",
    maintainer_email="wenhao@todo.todo",
    description="Reusable ChArUco hand-eye calibration pipeline for ROS2 Humble labs.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "handeye-init-config = handeye_pipeline.cli:init_config_main",
            "handeye-collect = handeye_pipeline.cli:collect_main",
            "handeye-solve = handeye_pipeline.cli:solve_main",
            "handeye-validate = handeye_pipeline.cli:validate_main",
            "handeye-export-tf = handeye_pipeline.cli:export_tf_main",
            "handeye_collect_samples_node = handeye_pipeline.ros_nodes.collect_samples_node:main",
            "handeye_publish_calibration_tf_node = handeye_pipeline.ros_nodes.publish_calibration_tf_node:main",
        ],
    },
)
