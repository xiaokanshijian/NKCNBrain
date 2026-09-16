"""
响应中断管理器
用于管理流式响应的中断状态
"""
import asyncio
from typing import Dict, Set
import threading


class InterruptManager:
    """响应中断管理器"""
    
    def __init__(self):
        self._interrupt_events: Dict[str, asyncio.Event] = {}
        self._active_sessions: Set[str] = set()
        self._lock = threading.Lock()
        # 新增：存储强制中断标记（用于卡住时的强制中断）
        self._force_interrupt: Set[str] = set()
        # 新增：存储会话开始时间（用于超时检测）
        self._session_start_times: Dict[str, float] = {}
    
    def create_session(self, session_id: str) -> asyncio.Event:
        """创建新的会话中断事件"""
        import time
        with self._lock:
            if session_id not in self._interrupt_events:
                self._interrupt_events[session_id] = asyncio.Event()
            self._active_sessions.add(session_id)
            # 记录会话开始时间
            self._session_start_times[session_id] = time.time()
            # 清除可能存在的强制中断标记
            self._force_interrupt.discard(session_id)
            return self._interrupt_events[session_id]
    
    def interrupt_session(self, session_id: str, force: bool = False) -> bool:
        """中断指定会话
        
        Args:
            session_id: 会话ID
            force: 是否强制中断（即使会话可能卡住）
        """
        with self._lock:
            if force:
                # 强制中断模式：即使没有找到会话事件也标记为中断
                self._force_interrupt.add(session_id)
                print(f"[中断管理器] 强制中断会话: {session_id}")
            
            if session_id in self._interrupt_events:
                self._interrupt_events[session_id].set()
                return True
            elif force:
                # 强制中断时即使没有事件也返回成功
                return True
            return False
    
    def cleanup_session(self, session_id: str):
        """清理会话资源"""
        with self._lock:
            if session_id in self._interrupt_events:
                del self._interrupt_events[session_id]
            self._active_sessions.discard(session_id)
            self._force_interrupt.discard(session_id)
            if session_id in self._session_start_times:
                del self._session_start_times[session_id]
    
    def is_interrupted(self, session_id: str) -> bool:
        """检查会话是否被中断"""
        with self._lock:
            # 首先检查是否被强制中断
            if session_id in self._force_interrupt:
                return True
            # 然后检查事件标记
            if session_id in self._interrupt_events:
                return self._interrupt_events[session_id].is_set()
            return False
    
    def get_active_sessions(self) -> Set[str]:
        """获取活跃会话列表"""
        with self._lock:
            return self._active_sessions.copy()
    
    def interrupt_all_user_sessions(self, username: str, force: bool = True) -> int:
        """中断指定用户的所有会话
        
        Args:
            username: 用户名
            force: 是否强制中断
            
        Returns:
            成功中断的会话数量
        """
        with self._lock:
            count = 0
            sessions_to_interrupt = [s for s in self._active_sessions if s.startswith(f"{username}_")]
            for session_id in sessions_to_interrupt:
                if force:
                    self._force_interrupt.add(session_id)
                if session_id in self._interrupt_events:
                    self._interrupt_events[session_id].set()
                count += 1
            if count > 0:
                print(f"[中断管理器] 中断用户 {username} 的 {count} 个会话（强制模式: {force}）")
            return count
    
    def check_session_timeout(self, session_id: str, timeout_seconds: int = 300) -> bool:
        """检查会话是否超时
        
        Args:
            session_id: 会话ID
            timeout_seconds: 超时时间（秒），默认5分钟
            
        Returns:
            是否超时
        """
        import time
        with self._lock:
            if session_id in self._session_start_times:
                elapsed = time.time() - self._session_start_times[session_id]
                return elapsed > timeout_seconds
            return False


# 全局中断管理器实例
interrupt_manager = InterruptManager()