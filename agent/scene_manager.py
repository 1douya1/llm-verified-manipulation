"""
场景上下文管理器
订阅ROS2检测结果，维护场景状态，为Agent提供上下文信息
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

try:
    from mtc_interface.msg import DetectionResult
    ROS_AVAILABLE = True
except ImportError:
    print("⚠️ Warning: mtc_interface not available. Scene detection will be disabled.")
    ROS_AVAILABLE = False
    DetectionResult = None


@dataclass
class SceneState:
    """场景状态数据类"""
    objects: List[str] = field(default_factory=list)  # ["object_1", "object_2", ...]
    object_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # 物体详细信息
    robot_holding: Optional[str] = None  # None 或 "object_1"
    last_action: Optional[str] = None  # "pick", "place", etc.
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "objects": self.objects,
            "object_count": len(self.objects),
            "robot_holding": self.robot_holding,
            "last_action": self.last_action,
            "last_updated": self.last_updated.isoformat()
        }
    
    def get_summary(self) -> str:
        """获取人类可读的状态摘要"""
        obj_list = ", ".join(self.objects) if self.objects else "无"
        holding = self.robot_holding or "无"
        return f"场景物体: {obj_list} | 机器人抓取: {holding} | 上次动作: {self.last_action or '无'}"


class SceneManagerNode(Node):
    """ROS2节点，订阅检测结果"""
    
    def __init__(self, scene_state: SceneState):
        super().__init__('scene_manager_node')
        self.scene_state = scene_state
        self.state_lock = threading.Lock()
        
        # 配置QoS（与detection节点保持一致）
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=1
        )
        
        # 订阅检测结果
        self.sub = self.create_subscription(
            DetectionResult,
            'object_detection_result',
            self.detection_callback,
            qos
        )
        
        self.get_logger().info("✅ Scene Manager Node initialized, subscribed to object_detection_result")
    
    def detection_callback(self, msg: DetectionResult):
        """处理检测结果回调"""
        with self.state_lock:
            # 提取物体ID列表（按照detection_to_planning_scene的命名规则）
            # 使用object_1, object_2, ... 的命名方式
            object_ids = []
            object_details = {}
            
            for idx, obj in enumerate(msg.objects, start=1):
                obj_id = f"object_{idx}"
                object_ids.append(obj_id)
                
                # 保存物体详细信息
                object_details[obj_id] = {
                    "class_name": obj.class_name,
                    "confidence": obj.confidence,
                    "position": {
                        "x": obj.position_base.x,
                        "y": obj.position_base.y,
                        "z": obj.position_base.z
                    },
                    "fitted_height": obj.fitted_height if obj.geometry_fitted else None,
                    "fitted_radius": obj.fitted_radius if obj.geometry_fitted else None,
                }
            
            # 更新场景状态
            self.scene_state.objects = object_ids
            self.scene_state.object_details = object_details
            self.scene_state.last_updated = datetime.now()
            
            self.get_logger().debug(f"Updated scene: {len(object_ids)} objects detected")


class SceneManager:
    """场景管理器主类（线程安全，单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.state = SceneState()
        self.state_lock = threading.Lock()
        self.ros_node = None
        self.spin_thread = None
        
        # 尝试初始化ROS2节点
        if ROS_AVAILABLE:
            self._init_ros()
    
    def _init_ros(self):
        """初始化ROS2节点和订阅"""
        try:
            if not rclpy.ok():
                rclpy.init()
            
            self.ros_node = SceneManagerNode(self.state)
            
            # 在单独线程中运行ROS2 spin
            self.spin_thread = threading.Thread(target=self._spin_ros, daemon=True)
            self.spin_thread.start()
            
            print("✅ Scene Manager initialized with ROS2 detection subscription")
        except Exception as e:
            print(f"⚠️ Failed to initialize ROS2 scene detection: {e}")
            print("   Scene manager will work without real-time detection")
    
    def _spin_ros(self):
        """在后台线程中运行ROS2 spin"""
        try:
            rclpy.spin(self.ros_node)
        except Exception as e:
            print(f"⚠️ ROS2 spin error: {e}")
    
    # ==================== 查询接口 ====================
    
    def get_state(self) -> SceneState:
        """获取当前场景状态（返回副本）"""
        with self.state_lock:
            return SceneState(
                objects=self.state.objects.copy(),
                object_details=self.state.object_details.copy(),
                robot_holding=self.state.robot_holding,
                last_action=self.state.last_action,
                last_updated=self.state.last_updated
            )
    
    def get_objects(self) -> List[str]:
        """获取场景中的物体ID列表"""
        with self.state_lock:
            return self.state.objects.copy()
    
    def get_object_count(self) -> int:
        """获取场景中的物体数量"""
        with self.state_lock:
            return len(self.state.objects)
    
    def get_object_details(self, object_id: str) -> Optional[Dict[str, Any]]:
        """获取指定物体的详细信息"""
        with self.state_lock:
            return self.state.object_details.get(object_id)
    
    def is_robot_holding(self) -> bool:
        """检查机器人是否正在抓取物体"""
        with self.state_lock:
            return self.state.robot_holding is not None
    
    def get_robot_holding(self) -> Optional[str]:
        """获取机器人当前抓取的物体ID"""
        with self.state_lock:
            return self.state.robot_holding
    
    def get_last_action(self) -> Optional[str]:
        """获取上次执行的动作"""
        with self.state_lock:
            return self.state.last_action
    
    def get_summary(self) -> str:
        """获取场景状态摘要"""
        with self.state_lock:
            return self.state.get_summary()
    
    # ==================== 更新接口 ====================
    
    def update_robot_holding(self, object_id: Optional[str]):
        """更新机器人抓取状态"""
        with self.state_lock:
            self.state.robot_holding = object_id
            self.state.last_updated = datetime.now()
    
    def set_last_action(self, action: str):
        """设置上次执行的动作"""
        with self.state_lock:
            self.state.last_action = action
            self.state.last_updated = datetime.now()
    
    def clear_robot_holding(self):
        """清除机器人抓取状态"""
        self.update_robot_holding(None)
    
    # ==================== 手动添加物体（用于测试）====================
    
    def manually_add_objects(self, object_ids: List[str]):
        """手动添加物体到场景（用于测试，不依赖ROS2检测）"""
        with self.state_lock:
            self.state.objects = object_ids.copy()
            self.state.last_updated = datetime.now()
            print(f"✅ Manually added {len(object_ids)} objects to scene: {object_ids}")
    
    # ==================== 清理资源 ====================
    
    def shutdown(self):
        """清理资源"""
        if self.ros_node:
            self.ros_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


# ==================== 全局单例访问 ====================

_global_scene_manager: Optional[SceneManager] = None

def get_scene_manager() -> SceneManager:
    """获取全局场景管理器实例"""
    global _global_scene_manager
    if _global_scene_manager is None:
        _global_scene_manager = SceneManager()
    return _global_scene_manager


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("Testing Scene Manager...")
    
    manager = get_scene_manager()
    
    # 手动添加测试物体
    manager.manually_add_objects(["object_1", "object_2"])
    
    # 测试查询
    print(f"\n场景状态: {manager.get_summary()}")
    print(f"物体列表: {manager.get_objects()}")
    print(f"物体数量: {manager.get_object_count()}")
    
    # 模拟抓取
    manager.update_robot_holding("object_1")
    manager.set_last_action("pick")
    print(f"\n执行pick后: {manager.get_summary()}")
    
    # 模拟放置
    manager.clear_robot_holding()
    manager.set_last_action("place")
    print(f"执行place后: {manager.get_summary()}")
    
    print("\n✅ Scene Manager test completed")





