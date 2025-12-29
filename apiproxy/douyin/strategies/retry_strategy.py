#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chiến lược thử lại thông minh
Bọc các chiến lược khác và cung cấp cơ chế thử lại thông minh
"""

import asyncio
import time
import logging
from typing import Optional, List
from functools import wraps

from .base import IDownloadStrategy, DownloadTask, DownloadResult, TaskStatus

logger = logging.getLogger(__name__)


class RetryStrategy(IDownloadStrategy):
    """Chiến lược thử lại thông minh, bọc các chiến lược khác và cung cấp cơ chế thử lại"""
    
    def __init__(
        self,
        strategy: IDownloadStrategy,
        max_retries: int = 3,
        retry_delays: Optional[List[float]] = None,
        exponential_backoff: bool = True
    ):
        """
        Khởi tạo chiến lược thử lại
        
        Args:
            strategy: Chiến lược được bọc
            max_retries: Số lần thử lại tối đa
            retry_delays: Danh sách độ trễ thử lại tùy chỉnh
            exponential_backoff: Có sử dụng exponential backoff không
        """
        self.strategy = strategy
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [1, 2, 5, 10, 30]
        self.exponential_backoff = exponential_backoff
        self.retry_stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_retries': 0
        }
    
    @property
    def name(self) -> str:
        return f"Retry({self.strategy.name})"
    
    def get_priority(self) -> int:
        """Kế thừa ưu tiên của chiến lược được bọc"""
        return self.strategy.get_priority()
    
    async def can_handle(self, task: DownloadTask) -> bool:
        """Đánh giá xem có thể xử lý nhiệm vụ không"""
        return await self.strategy.can_handle(task)
    
    async def download(self, task: DownloadTask) -> DownloadResult:
        """Thực thi nhiệm vụ tải xuống, có cơ chế thử lại"""
        original_retry_count = task.retry_count
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Cập nhật trạng thái nhiệm vụ
                if attempt > 0:
                    task.status = TaskStatus.RETRYING
                    logger.info(f"Nhiệm vụ {task.task_id} lần thử lại thứ {attempt + 1}/{self.max_retries}")
                
                # Thực thi tải xuống
                result = await self.strategy.download(task)
                
                if result.success:
                    if attempt > 0:
                        self.retry_stats['successful_retries'] += 1
                        logger.info(f"Nhiệm vụ {task.task_id} thử lại thành công (lần {attempt + 1})")
                    return result
                
                # Tải xuống thất bại, chuẩn bị thử lại
                last_error = result.error_message
                
                # Kiểm tra xem có nên thử lại không
                if not self._should_retry(result, attempt):
                    logger.warning(f"Nhiệm vụ {task.task_id} không đáp ứng điều kiện thử lại, dừng thử lại")
                    return result
                
                # Tính toán thời gian trễ
                delay = self._calculate_delay(attempt)
                logger.info(f"Nhiệm vụ {task.task_id} sẽ thử lại sau {delay} giây")
                await asyncio.sleep(delay)
                
                # Tăng số đếm thử lại
                task.retry_count += 1
                self.retry_stats['total_retries'] += 1
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Nhiệm vụ {task.task_id} thực thi lỗi: {e}")
                
                if attempt < self.max_retries - 1:
                    delay = self._calculate_delay(attempt)
                    logger.info(f"Nhiệm vụ {task.task_id} sẽ thử lại sau {delay} giây")
                    await asyncio.sleep(delay)
                    task.retry_count += 1
                    self.retry_stats['total_retries'] += 1
                else:
                    self.retry_stats['failed_retries'] += 1
                    break
        
        # Tất cả các lần thử lại đều thất bại
        task.status = TaskStatus.FAILED
        self.retry_stats['failed_retries'] += 1
        
        return DownloadResult(
            success=False,
            task_id=task.task_id,
            error_message=f"Vẫn thất bại sau {self.max_retries} lần thử lại: {last_error}",
            retry_count=task.retry_count
        )
    
    def _should_retry(self, result: DownloadResult, attempt: int) -> bool:
        """Đánh giá xem có nên thử lại không"""
        # Nếu đã đạt số lần thử lại tối đa, không thử lại
        if attempt >= self.max_retries - 1:
            return False
        
        # Nếu không có thông báo lỗi, có thể là lỗi không xác định, nên thử lại
        if not result.error_message:
            return True
        
        # Kiểm tra xem có phải lỗi có thể thử lại không
        retryable_errors = [
            'timeout',
            'connection',
            'network',
            '429',  # Too Many Requests
            '503',  # Service Unavailable
            '502',  # Bad Gateway
            '504',  # Gateway Timeout
            'phản hồi rỗng',
            'trả về rỗng',
            'empty response',
            'temporary'
        ]
        
        error_lower = result.error_message.lower()
        for error in retryable_errors:
            if error in error_lower:
                return True
        
        # Kiểm tra xem có phải lỗi không thể thử lại không
        non_retryable_errors = [
            '404',  # Not Found
            '403',  # Forbidden
            '401',  # Unauthorized
            'invalid',
            'not found',
            'deleted',
            'đã xóa',
            'không tồn tại'
        ]
        
        for error in non_retryable_errors:
            if error in error_lower:
                return False
        
        # Mặc định thử lại
        return True
    
    def _calculate_delay(self, attempt: int) -> float:
        """Tính toán thời gian trễ thử lại"""
        if self.exponential_backoff:
            # Exponential backoff: 2^attempt giây, tối đa 30 giây
            delay = min(2 ** attempt, 30)
        else:
            # Sử dụng danh sách độ trễ được định nghĩa trước
            if attempt < len(self.retry_delays):
                delay = self.retry_delays[attempt]
            else:
                delay = self.retry_delays[-1]
        
        # Thêm một chút ngẫu nhiên để tránh thử lại đồng thời
        import random
        jitter = random.uniform(0, 0.3 * delay)
        
        return delay + jitter
    
    def get_stats(self) -> dict:
        """Lấy thông tin thống kê thử lại"""
        return self.retry_stats.copy()
    
    def reset_stats(self):
        """Đặt lại thông tin thống kê"""
        self.retry_stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_retries': 0
        }


def with_retry(
    max_retries: int = 3,
    retry_delays: Optional[List[float]] = None,
    exponential_backoff: bool = True
):
    """
    Decorator: Thêm cơ chế thử lại cho hàm bất đồng bộ
    
    Usage:
        @with_retry(max_retries=3)
        async def download_file(url):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delays = retry_delays or [1, 2, 5, 10, 30]
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        if exponential_backoff:
                            delay = min(2 ** attempt, 30)
                        else:
                            delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        
                        logger.warning(f"Hàm {func.__name__} thất bại (thử {attempt + 1}/{max_retries}): {e}")
                        logger.info(f"Sẽ thử lại sau {delay} giây")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Hàm {func.__name__} vẫn thất bại sau {max_retries} lần thử lại")
            
            raise last_exception
        
        return wrapper
    return decorator