#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Hệ thống theo dõi tiến độ thời gian thực
Hỗ trợ đẩy WebSocket và giám sát tiến độ
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

# Import động hỗ trợ WebSocket
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logger.warning("websockets chưa được cài đặt, chức năng WebSocket không khả dụng")


class EventType(Enum):
    """Loại sự kiện"""
    TASK_ADDED = "task_added"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRYING = "task_retrying"
    STATS_UPDATE = "stats_update"
    SPEED_UPDATE = "speed_update"
    ERROR = "error"
    INFO = "info"


@dataclass
class ProgressEvent:
    """Sự kiện tiến độ"""
    event_type: EventType
    task_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        """Chuyển đổi sang dictionary"""
        return {
            'event_type': self.event_type.value,
            'task_id': self.task_id,
            'data': self.data,
            'timestamp': self.timestamp
        }
    
    def to_json(self) -> str:
        """Chuyển đổi sang JSON"""
        return json.dumps(self.to_dict())


@dataclass
class TaskProgress:
    """Thông tin tiến độ nhiệm vụ"""
    task_id: str
    url: str
    status: str
    progress: float = 0.0  # 0-100
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0  # bytes/second
    eta: float = 0.0  # seconds
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    
    def get_duration(self) -> float:
        """Lấy thời gian đã dùng"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    def update_progress(self, downloaded: int, total: int):
        """Cập nhật tiến độ"""
        self.downloaded_bytes = downloaded
        self.total_bytes = total
        
        if total > 0:
            self.progress = (downloaded / total) * 100
        
        # Tính toán tốc độ
        duration = self.get_duration()
        if duration > 0:
            self.speed = downloaded / duration
        
        # Tính toán thời gian còn lại
        if self.speed > 0 and total > downloaded:
            self.eta = (total - downloaded) / self.speed
    
    def to_dict(self) -> Dict:
        """Chuyển đổi sang dictionary"""
        return {
            'task_id': self.task_id,
            'url': self.url,
            'status': self.status,
            'progress': round(self.progress, 2),
            'downloaded_bytes': self.downloaded_bytes,
            'total_bytes': self.total_bytes,
            'speed': round(self.speed, 2),
            'eta': round(self.eta, 2),
            'duration': round(self.get_duration(), 2),
            'error_message': self.error_message
        }


class ProgressTracker:
    """Bộ theo dõi tiến độ"""
    
    def __init__(self, enable_websocket: bool = True, ws_port: int = 8765):
        """
        Khởi tạo bộ theo dõi tiến độ
        
        Args:
            enable_websocket: Có bật WebSocket không
            ws_port: Cổng WebSocket
        """
        self.enable_websocket = enable_websocket and WEBSOCKET_AVAILABLE
        self.ws_port = ws_port
        
        # Tiến độ nhiệm vụ
        self.tasks: Dict[str, TaskProgress] = {}
        
        # Trình lắng nghe sự kiện
        self.listeners: List[Callable[[ProgressEvent], None]] = []
        
        # Kết nối WebSocket
        self.websocket_clients: List[WebSocketServerProtocol] = []
        self.websocket_server = None
        self.ws_task = None
        
        # Thông tin thống kê
        self.stats = {
            'total_tasks': 0,
            'active_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_downloaded': 0,
            'average_speed': 0.0,
            'success_rate': 0.0
        }
        
        # Lịch sử tốc độ (dùng để tính tốc độ trung bình)
        self.speed_history = []
        self.max_speed_history = 100
    
    def add_listener(self, listener: Callable[[ProgressEvent], None]):
        """Thêm trình lắng nghe sự kiện"""
        self.listeners.append(listener)
        logger.debug(f"Thêm trình lắng nghe sự kiện: {listener}")
    
    def remove_listener(self, listener: Callable[[ProgressEvent], None]):
        """Xóa trình lắng nghe sự kiện"""
        if listener in self.listeners:
            self.listeners.remove(listener)
    
    async def emit_event(self, event: ProgressEvent):
        """Kích hoạt sự kiện"""
        # Thông báo cho các trình lắng nghe
        for listener in self.listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.error(f"Thực thi trình lắng nghe sự kiện thất bại: {e}")
        
        # Đẩy đến các client WebSocket
        if self.websocket_clients:
            await self._broadcast_websocket(event.to_json())
    
    async def add_task(self, task_id: str, url: str):
        """Thêm nhiệm vụ"""
        self.tasks[task_id] = TaskProgress(
            task_id=task_id,
            url=url,
            status="pending"
        )
        
        self.stats['total_tasks'] += 1
        
        await self.emit_event(ProgressEvent(
            event_type=EventType.TASK_ADDED,
            task_id=task_id,
            data={'url': url}
        ))
    
    async def start_task(self, task_id: str):
        """Bắt đầu nhiệm vụ"""
        if task_id in self.tasks:
            self.tasks[task_id].status = "processing"
            self.tasks[task_id].start_time = time.time()
            
            self.stats['active_tasks'] += 1
            
            await self.emit_event(ProgressEvent(
                event_type=EventType.TASK_STARTED,
                task_id=task_id
            ))
    
    async def update_progress(
        self,
        task_id: str,
        downloaded: int,
        total: int,
        extra_data: Optional[Dict] = None
    ):
        """Cập nhật tiến độ nhiệm vụ"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        task.update_progress(downloaded, total)
        
        # Cập nhật lịch sử tốc độ
        if task.speed > 0:
            self.speed_history.append(task.speed)
            if len(self.speed_history) > self.max_speed_history:
                self.speed_history.pop(0)
            
            # Tính toán tốc độ trung bình
            self.stats['average_speed'] = sum(self.speed_history) / len(self.speed_history)
        
        event_data = task.to_dict()
        if extra_data:
            event_data.update(extra_data)
        
        await self.emit_event(ProgressEvent(
            event_type=EventType.TASK_PROGRESS,
            task_id=task_id,
            data=event_data
        ))
    
    async def complete_task(self, task_id: str, success: bool = True, error: Optional[str] = None):
        """Hoàn thành nhiệm vụ"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        task.end_time = time.time()
        
        if success:
            task.status = "completed"
            task.progress = 100.0
            self.stats['completed_tasks'] += 1
            event_type = EventType.TASK_COMPLETED
        else:
            task.status = "failed"
            task.error_message = error
            self.stats['failed_tasks'] += 1
            event_type = EventType.TASK_FAILED
        
        self.stats['active_tasks'] = max(0, self.stats['active_tasks'] - 1)
        
        # Cập nhật tỷ lệ thành công
        total_finished = self.stats['completed_tasks'] + self.stats['failed_tasks']
        if total_finished > 0:
            self.stats['success_rate'] = (self.stats['completed_tasks'] / total_finished) * 100
        
        await self.emit_event(ProgressEvent(
            event_type=event_type,
            task_id=task_id,
            data=task.to_dict()
        ))
    
    async def retry_task(self, task_id: str, retry_count: int):
        """Thử lại nhiệm vụ"""
        if task_id in self.tasks:
            self.tasks[task_id].status = "retrying"
            
            await self.emit_event(ProgressEvent(
                event_type=EventType.TASK_RETRYING,
                task_id=task_id,
                data={'retry_count': retry_count}
            ))
    
    async def update_stats(self):
        """Cập nhật thông tin thống kê"""
        await self.emit_event(ProgressEvent(
            event_type=EventType.STATS_UPDATE,
            data=self.stats.copy()
        ))
    
    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """Lấy tiến độ nhiệm vụ"""
        return self.tasks.get(task_id)
    
    def get_active_tasks(self) -> List[TaskProgress]:
        """Lấy các nhiệm vụ đang hoạt động"""
        return [
            task for task in self.tasks.values()
            if task.status in ["processing", "retrying"]
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Lấy thông tin thống kê"""
        return self.stats.copy()
    
    def clear_completed_tasks(self):
        """Dọn dẹp các nhiệm vụ đã hoàn thành"""
        completed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in ["completed", "failed"]
        ]
        
        for task_id in completed_ids:
            del self.tasks[task_id]
        
        logger.info(f"Đã dọn dẹp {len(completed_ids)} nhiệm vụ đã hoàn thành")
    
    # Chức năng liên quan WebSocket
    async def start_websocket_server(self):
        """Khởi động server WebSocket"""
        if not self.enable_websocket:
            logger.info("Chức năng WebSocket chưa được bật")
            return
        
        try:
            self.websocket_server = await websockets.serve(
                self._handle_websocket,
                "localhost",
                self.ws_port
            )
            
            logger.info(f"Server WebSocket khởi động tại ws://localhost:{self.ws_port}")
            
        except Exception as e:
            logger.error(f"Khởi động server WebSocket thất bại: {e}")
    
    async def stop_websocket_server(self):
        """Dừng server WebSocket"""
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            self.websocket_server = None
            logger.info("Server WebSocket đã dừng")
    
    async def _handle_websocket(self, websocket: WebSocketServerProtocol, path: str):
        """Xử lý kết nối WebSocket"""
        logger.info(f"Kết nối WebSocket mới: {websocket.remote_address}")
        
        # Thêm client
        self.websocket_clients.append(websocket)
        
        try:
            # Gửi trạng thái hiện tại
            await websocket.send(json.dumps({
                'type': 'init',
                'data': {
                    'tasks': {
                        task_id: task.to_dict()
                        for task_id, task in self.tasks.items()
                    },
                    'stats': self.stats
                }
            }))
            
            # Duy trì kết nối
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_ws_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"Tin nhắn WebSocket không hợp lệ: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Kết nối WebSocket đóng: {websocket.remote_address}")
        finally:
            # Xóa client
            if websocket in self.websocket_clients:
                self.websocket_clients.remove(websocket)
    
    async def _handle_ws_message(self, websocket: WebSocketServerProtocol, data: Dict):
        """Xử lý tin nhắn WebSocket"""
        msg_type = data.get('type')
        
        if msg_type == 'ping':
            await websocket.send(json.dumps({'type': 'pong'}))
        elif msg_type == 'get_stats':
            await websocket.send(json.dumps({
                'type': 'stats',
                'data': self.stats
            }))
        elif msg_type == 'get_tasks':
            await websocket.send(json.dumps({
                'type': 'tasks',
                'data': {
                    task_id: task.to_dict()
                    for task_id, task in self.tasks.items()
                }
            }))
    
    async def _broadcast_websocket(self, message: str):
        """Phát sóng tin nhắn WebSocket"""
        if not self.websocket_clients:
            return
        
        # Gửi đồng thời cho tất cả client
        disconnected = []
        
        for client in self.websocket_clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.append(client)
        
        # Dọn dẹp các kết nối đã ngắt
        for client in disconnected:
            self.websocket_clients.remove(client)
    
    # Context manager
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.start_websocket_server()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        await self.stop_websocket_server()


def create_console_listener(use_rich: bool = True):
    """
    Tạo trình lắng nghe tiến độ console
    
    Args:
        use_rich: Có sử dụng thư viện Rich để làm đẹp đầu ra không
    
    Returns:
        Hàm trình lắng nghe
    """
    if use_rich:
        try:
            from rich.console import Console
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
            from rich.table import Table
            
            console = Console()
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            )
            
            task_map = {}
            
            def rich_listener(event: ProgressEvent):
                if event.event_type == EventType.TASK_ADDED:
                    task_id = event.task_id
                    if task_id not in task_map:
                        task_map[task_id] = progress.add_task(
                            f"[cyan]{event.data.get('url', 'Unknown')}",
                            total=100
                        )
                
                elif event.event_type == EventType.TASK_PROGRESS:
                    task_id = event.task_id
                    if task_id in task_map:
                        progress.update(
                            task_map[task_id],
                            completed=event.data.get('progress', 0)
                        )
                
                elif event.event_type == EventType.TASK_COMPLETED:
                    console.print(f"[green]✓ Nhiệm vụ hoàn thành: {event.task_id}")
                
                elif event.event_type == EventType.TASK_FAILED:
                    console.print(f"[red]✗ Nhiệm vụ thất bại: {event.task_id} - {event.data.get('error_message', 'Lỗi không xác định')}")
            
            return rich_listener
            
        except ImportError:
            pass
    
    # Trình lắng nghe đơn giản mặc định
    def simple_listener(event: ProgressEvent):
        timestamp = datetime.fromtimestamp(event.timestamp).strftime('%H:%M:%S')
        
        if event.event_type == EventType.TASK_PROGRESS:
            progress = event.data.get('progress', 0)
            speed = event.data.get('speed', 0)
            print(f"[{timestamp}] Nhiệm vụ {event.task_id}: {progress:.1f}% ({speed/1024/1024:.2f} MB/s)")
        elif event.event_type == EventType.TASK_COMPLETED:
            print(f"[{timestamp}] ✓ Nhiệm vụ hoàn thành: {event.task_id}")
        elif event.event_type == EventType.TASK_FAILED:
            print(f"[{timestamp}] ✗ Nhiệm vụ thất bại: {event.task_id}")
    
    return simple_listener