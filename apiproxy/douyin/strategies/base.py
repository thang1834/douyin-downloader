#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Lớp cơ sở và định nghĩa interface cho chiến lược tải xuống
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class TaskType(Enum):
    """Enum loại nhiệm vụ"""
    VIDEO = "video"
    IMAGE = "image"
    MUSIC = "music"
    USER = "user"
    MIX = "mix"
    LIVE = "live"


class TaskStatus(Enum):
    """Enum trạng thái nhiệm vụ"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class DownloadTask:
    """Lớp dữ liệu nhiệm vụ tải xuống"""
    task_id: str
    url: str
    task_type: TaskType
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    
    def increment_retry(self) -> bool:
        """Tăng số lần thử lại, trả về xem còn có thể thử lại không"""
        self.retry_count += 1
        self.updated_at = time.time()
        return self.retry_count < self.max_retries
    
    def to_dict(self) -> Dict:
        """Chuyển đổi sang dictionary"""
        return {
            'task_id': self.task_id,
            'url': self.url,
            'task_type': self.task_type.value,
            'priority': self.priority,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'status': self.status.value,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'error_message': self.error_message
        }


@dataclass
class DownloadResult:
    """Lớp dữ liệu kết quả tải xuống"""
    success: bool
    task_id: str
    file_paths: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    retry_count: int = 0
    
    def to_dict(self) -> Dict:
        """Chuyển đổi sang dictionary"""
        return {
            'success': self.success,
            'task_id': self.task_id,
            'file_paths': self.file_paths,
            'error_message': self.error_message,
            'metadata': self.metadata,
            'duration': self.duration,
            'retry_count': self.retry_count
        }


class IDownloadStrategy(ABC):
    """Lớp cơ sở trừu tượng cho chiến lược tải xuống"""
    
    @abstractmethod
    async def can_handle(self, task: DownloadTask) -> bool:
        """Đánh giá xem có thể xử lý nhiệm vụ này không"""
        pass
    
    @abstractmethod
    async def download(self, task: DownloadTask) -> DownloadResult:
        """Thực hiện nhiệm vụ tải xuống"""
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """Lấy độ ưu tiên của chiến lược, giá trị càng lớn độ ưu tiên càng cao"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tên chiến lược"""
        pass
    
    def __str__(self) -> str:
        return f"{self.name} (Priority: {self.get_priority()})"