#!/usr/bin/env python3
"""
End-to-end diagnostics for the real-robot environment.

Verifies:
  1. mtc_action_library is importable and initializable.
  2. /move_group is up, with key parameters and topics.

Run after sourcing the workspace:

    source install/setup.bash
    python3 scripts/diagnostics/diagnose_robot_env.py
"""

import subprocess
import sys
import time

import rclpy
from rclpy.node import Node

def check_move_group():
    """检查MoveGroup是否运行"""
    print("\n" + "="*60)
    print("🔍 诊断：检查MoveGroup状态")
    print("="*60)
    
    if not rclpy.ok():
        rclpy.init()
    
    node = Node('diagnostics_node')
    move_group_found = False
    try:
        # 1. 检查MoveGroup节点
        print("\n1️⃣  检查MoveGroup节点...")
        # Graph discovery is eventually consistent. Give DDS some time.
        node_names = []
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.2)
            node_names = node.get_node_names()
            move_group_found = any('move_group' in name for name in node_names)
            if move_group_found:
                break
            time.sleep(0.1)

        # Fallback to ROS CLI (same source user usually checks manually).
        if not move_group_found:
            try:
                p = subprocess.run(
                    ['ros2', 'node', 'list'],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3.0
                )
                if p.returncode == 0 and 'move_group' in p.stdout:
                    move_group_found = True
                    print("   [..] 通过 `ros2 node list` 兜底检测到 move_group")
            except Exception:
                pass

        if move_group_found:
            print("   ✅ MoveGroup节点正在运行")
            for name in node_names:
                if 'move_group' in name:
                    print(f"      • {name}")
        else:
            print("   [ERR] No move_group node found")
            print("\n   In another terminal launch one of:")
            print("     ros2 launch xarm_moveit_config uf850_moveit_fake.launch.py    # plan-only")
            print("     ros2 launch xarm_moveit_config uf850_moveit_realmove.launch.py robot_ip:=<IP>  # real robot")
            print("   See docs/REAL_ROBOT_QUICK_START.md for the full launch sequence.")
            return False

        # 2. 检查参数服务器
        print("\n2️⃣  检查MoveGroup参数...")
        try:
            p = subprocess.run(
                ['ros2', 'param', 'list', '/move_group'],
                check=False,
                capture_output=True,
                text=True,
                timeout=4.0
            )
            if p.returncode == 0:
                print("   ✅ 参数服务可用")
                important = [
                    'robot_description',
                    'robot_description_semantic',
                    'robot_description_kinematics.uf850.kinematics_solver',
                ]
                for key in important:
                    flag = "✅" if key in p.stdout else "⚠️"
                    print(f"   {flag} {key}")
            else:
                print("   ❌ 参数服务不可用")
        except Exception as e:
            print(f"   ❌ 检查参数时出错: {e}")

        # 3. 检查话题
        print("\n3️⃣  检查关键话题...")
        topic_names = node.get_topic_names_and_types()

        important_topics = [
            '/joint_states',
            '/move_group/display_planned_path',
            '/planning_scene',
        ]

        for topic in important_topics:
            found = any(t[0] == topic for t in topic_names)
            emoji = "✅" if found else "❌"
            print(f"   {emoji} {topic}")

        # 4. 检查Action服务器
        print("\n4️⃣  检查Action服务器...")
        # 这里可以添加更多检查

        print("\n" + "="*60)

        return move_group_found
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def check_mtc_action_library():
    """检查动作库是否正确安装"""
    print("\n" + "="*60)
    print("🔍 诊断：检查动作库安装")
    print("="*60)
    
    # 1. 检查导入
    print("\n1️⃣  检查Python导入...")
    try:
        from mtc_action_library import get_action_library
        print("   ✅ 动作库可以导入")
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        return False
    
    # 2. 检查初始化
    print("\n2️⃣  检查初始化...")
    try:
        lib = get_action_library()
        print("   ✅ 动作库初始化成功")
        
        actions = lib.get_actions()
        print(f"   ✅ 可用动作: {', '.join(actions)}")
    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
        return False
    
    print("\n" + "="*60)
    return True


def main() -> int:
    print("\n" + "="*70)
    print("🔍 MTC Action Library 环境诊断")
    print("="*70)
    
    # 检查动作库
    lib_ok = check_mtc_action_library()
    
    # 检查MoveGroup
    mg_ok = check_move_group()
    
    # 总结
    print("\n" + "="*70)
    print("📊 诊断总结")
    print("="*70)
    
    if lib_ok and mg_ok:
        print("\n[OK] Environment is fully ready.")
        print("\nNext step: drive a single MTC action through the library, e.g.:")
        print("  python3 -c \"from mtc_action_library import get_action_library;\\")
        print("              lib = get_action_library();\\")
        print("              print(lib.execute('return_home'))\"")
        rc = 0
    elif lib_ok and not mg_ok:
        print("\n[WARN] Action library is installed, but move_group is NOT running.")
        print("\nLaunch move_group first (in another terminal):")
        print("  ros2 launch xarm_moveit_config uf850_moveit_realmove.launch.py robot_ip:=<IP>")
        print("Then re-source this workspace and re-run this script.")
        rc = 1
    elif not lib_ok:
        print("\n[ERR] Action library is not importable.")
        print("\nRebuild:")
        print("  colcon build --packages-select mtc_action_library_core mtc_action_library_py")
        print("  source install/setup.bash")
        rc = 2
    else:
        rc = 1
    
    print("\n" + "="*70 + "\n")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 已中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 诊断过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)








