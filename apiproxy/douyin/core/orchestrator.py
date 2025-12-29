#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bộ điều phối tải xuống
Điều phối nhiều chiến lược tải xuống, thực hiện giảm cấp thông minh và quản lý nhiệm vụ
"""

import asyncio
import time
import logging
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from apiproxy.douyin.strategies.base import (
    IDownloadStrategy, 
    DownloadTask, 
    DownloadResult,
    TaskType,
    TaskStatus
)
from apiproxy.douyin.strategies.api_strategy import EnhancedAPIStrategy
from apiproxy.douyin.strategies.retry_strategy import RetryStrategy
from .rate_limiter import AdaptiveRateLimiter, RateLimitConfig

logger = logging.getLogger(__name__)


class OrchestratorConfig:
    """Cấu hình bộ điều phối"""
    def __init__(
        self,
        max_concurrent: int = 5,
        enable_retry: bool = True,
        enable_rate_limit: bool = True,
        rate_limit_config: Optional[RateLimitConfig] = None,
        priority_queue: bool = True,
        save_progress: bool = True
    ):
        self.max_concurrent = max_concurrent
        self.enable_retry = enable_retry
        self.enable_rate_limit = enable_rate_limit
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.priority_queue = priority_queue
        self.save_progress = save_progress


class DownloadOrchestrator:
    """Bộ điều phối nhiệm vụ tải xuống"""
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        """
        Khởi tạo bộ điều phối
        
        Args:
            config: Cấu hình bộ điều phối
        """
        self.config = config or OrchestratorConfig()
        self.strategies: List[IDownloadStrategy] = []
        self.rate_limiter = AdaptiveRateLimiter(self.config.rate_limit_config) if self.config.enable_rate_limit else None
        
        # Hàng đợi nhiệm vụ
        self.pending_queue = asyncio.Queue()
        self.priority_tasks: List[DownloadTask] = []
        self.active_tasks: Dict[str, DownloadTask] = {}
        self.completed_tasks: List[DownloadTask] = []
        self.failed_tasks: List[DownloadTask] = []
        
        # Worker threads
        self.workers: List[asyncio.Task] = []
        self.running = False
        
        # Thông tin thống kê
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'retried_tasks': 0,
            'average_duration': 0.0,
            'success_rate': 0.0
        }
        
        # Khởi tạo chiến lược mặc định
        self._init_default_strategies()
    
    def _init_default_strategies(self):
        """Khởi tạo chiến lược mặc định"""
        # Chiến lược API
        api_strategy = EnhancedAPIStrategy()
        
        # Nếu bật thử lại, bọc chiến lược
        if self.config.enable_retry:
            api_strategy = RetryStrategy(api_strategy)
        
        self.register_strategy(api_strategy)
    
    def register_strategy(self, strategy: IDownloadStrategy):
        """
        Đăng ký chiến lược tải xuống
        
        Args:
            strategy: Instance chiến lược tải xuống
        """
        self.strategies.append(strategy)
        # Sắp xếp theo ưu tiên
        self.strategies.sort(key=lambda s: s.get_priority(), reverse=True)
        logger.info(f"Đăng ký chiến lược: {strategy.name} (ưu tiên: {strategy.get_priority()})")
    
    async def add_task(self, url: str, task_type: Optional[TaskType] = None, priority: int = 0) -> str:
        """
        Thêm nhiệm vụ tải xuống
        
        Args:
            url: URL tải xuống
            task_type: Loại nhiệm vụ
            priority: Ưu tiên (số càng lớn ưu tiên càng cao)
        
        Returns:
            ID nhiệm vụ
        """
        # Tự động nhận diện loại nhiệm vụ
        if task_type is None:
            task_type = self._detect_task_type(url)
        
        # Tạo nhiệm vụ
        task = DownloadTask(
            task_id=str(uuid.uuid4()),
            url=url,
            task_type=task_type,
            priority=priority
        )
        
        # Thêm vào hàng đợi
        if self.config.priority_queue and priority > 0:
            self.priority_tasks.append(task)
            self.priority_tasks.sort(key=lambda t: t.priority, reverse=True)
        else:
            await self.pending_queue.put(task)
        
        self.stats['total_tasks'] += 1
        logger.info(f"Thêm nhiệm vụ: {task.task_id} ({task_type.value}) ưu tiên: {priority}")
        
        return task.task_id
    
    async def add_batch(self, urls: List[str], task_type: Optional[TaskType] = None) -> List[str]:
        """
        Thêm nhiệm vụ hàng loạt
        
        Args:
            urls: Danh sách URL
            task_type: Loại nhiệm vụ
        
        Returns:
            Danh sách ID nhiệm vụ
        """
        task_ids = []
        for i, url in enumerate(urls):
            # Nhiệm vụ hàng loạt sử dụng ưu tiên giảm dần
            priority = len(urls) - i
            task_id = await self.add_task(url, task_type, priority)
            task_ids.append(task_id)
        
        return task_ids
    
    async def start(self):
        """Khởi động bộ điều phối"""
        if self.running:
            logger.warning("Bộ điều phối đang chạy")
            return
        
        self.running = True
        logger.info(f"Khởi động bộ điều phối, số đồng thời tối đa: {self.config.max_concurrent}")
        
        # Tạo worker threads
        for i in range(self.config.max_concurrent):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
    
    async def stop(self):
        """Dừng bộ điều phối"""
        if not self.running:
            return
        
        logger.info("Đang dừng bộ điều phối...")
        self.running = False
        
        # Hủy tất cả worker threads
        for worker in self.workers:
            worker.cancel()
        
        # Chờ worker threads kết thúc
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info("Bộ điều phối đã dừng")
    
    async def wait_completion(self, timeout: Optional[float] = None):
        """
        Chờ tất cả nhiệm vụ hoàn thành
        
        Args:
            timeout: Thời gian chờ (giây)
        """
        start_time = time.time()
        
        while self.running:
            # Kiểm tra xem tất cả nhiệm vụ đã hoàn thành chưa
            if (self.pending_queue.empty() and 
                not self.priority_tasks and 
                not self.active_tasks):
                logger.info("Tất cả nhiệm vụ đã hoàn thành")
                break
            
            # Kiểm tra timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"Chờ quá thời gian ({timeout} giây)")
                break
            
            await asyncio.sleep(1)
        
        # Tính toán thông tin thống kê
        self._calculate_stats()
    
    async def _worker(self, worker_id: int):
        """
        Worker thread
        
        Args:
            worker_id: ID worker thread
        """
        logger.info(f"Worker thread {worker_id} khởi động")
        
        while self.running:
            try:
                # Lấy nhiệm vụ
                task = await self._get_next_task()
                if task is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Đánh dấu là nhiệm vụ đang hoạt động
                self.active_tasks[task.task_id] = task
                
                # Kiểm soát giới hạn tốc độ
                if self.rate_limiter:
                    await self.rate_limiter.acquire()
                
                # Thực thi nhiệm vụ
                logger.info(f"Worker thread {worker_id} bắt đầu xử lý nhiệm vụ: {task.task_id}")
                result = await self._execute_task(task)
                
                # Xóa nhiệm vụ đang hoạt động
                del self.active_tasks[task.task_id]
                
                # Xử lý kết quả
                if result.success:
                    self.completed_tasks.append(task)
                    self.stats['completed_tasks'] += 1
                    logger.info(f"Nhiệm vụ {task.task_id} hoàn thành")
                else:
                    # Kiểm tra xem có cần thử lại không
                    if task.increment_retry():
                        logger.warning(f"Nhiệm vụ {task.task_id} thất bại, chuẩn bị thử lại ({task.retry_count}/{task.max_retries})")
                        await self.pending_queue.put(task)
                        self.stats['retried_tasks'] += 1
                    else:
                        self.failed_tasks.append(task)
                        self.stats['failed_tasks'] += 1
                        logger.error(f"Nhiệm vụ {task.task_id} cuối cùng thất bại: {result.error_message}")
                
                # Lưu tiến độ
                if self.config.save_progress:
                    await self._save_progress()
                
            except asyncio.CancelledError:
                logger.info(f"Worker thread {worker_id} bị hủy")
                break
            except Exception as e:
                logger.error(f"Worker thread {worker_id} lỗi: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"Worker thread {worker_id} kết thúc")
    
    async def _get_next_task(self) -> Optional[DownloadTask]:
        """Lấy nhiệm vụ tiếp theo"""
        # Ưu tiên xử lý nhiệm vụ có ưu tiên cao
        if self.priority_tasks:
            return self.priority_tasks.pop(0)
        
        # Lấy từ hàng đợi thông thường
        try:
            return await asyncio.wait_for(
                self.pending_queue.get(),
                timeout=0.1
            )
        except asyncio.TimeoutError:
            return None
    
    async def _execute_task(self, task: DownloadTask) -> DownloadResult:
        """
        Thực thi nhiệm vụ, thử tất cả các chiến lược
        
        Args:
            task: Nhiệm vụ tải xuống
        
        Returns:
            Kết quả tải xuống
        """
        last_error = None
        
        for strategy in self.strategies:
            try:
                # Kiểm tra xem chiến lược có thể xử lý nhiệm vụ không
                if not await strategy.can_handle(task):
                    continue
                
                logger.info(f"Sử dụng chiến lược {strategy.name} xử lý nhiệm vụ {task.task_id}")
                
                # Thực thi tải xuống
                result = await strategy.download(task)
                
                if result.success:
                    return result
                
                last_error = result.error_message
                logger.warning(f"Chiến lược {strategy.name} thất bại: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Chiến lược {strategy.name} lỗi: {e}")
        
        # Tất cả chiến lược đều thất bại
        return DownloadResult(
            success=False,
            task_id=task.task_id,
            error_message=f"Tất cả chiến lược đều thất bại: {last_error}",
            retry_count=task.retry_count
        )
    
    def _detect_task_type(self, url: str) -> TaskType:
        """
        Tự động phát hiện loại nhiệm vụ
        
        Args:
            url: URL
        
        Returns:
            Loại nhiệm vụ
        """
        url_lower = url.lower()
        
        if '/user/' in url_lower:
            return TaskType.USER
        elif '/video/' in url_lower or '/note/' in url_lower:
            return TaskType.VIDEO
        elif '/music/' in url_lower:
            return TaskType.MUSIC
        elif '/mix/' in url_lower or '/collection/' in url_lower:
            return TaskType.MIX
        elif 'live.douyin.com' in url_lower:
            return TaskType.LIVE
        else:
            return TaskType.VIDEO  # Mặc định là video
    
    def _calculate_stats(self):
        """Tính toán thông tin thống kê"""
        total = self.stats['total_tasks']
        if total > 0:
            self.stats['success_rate'] = self.stats['completed_tasks'] / total * 100
        
        # Tính toán thời lượng trung bình
        durations = []
        for task in self.completed_tasks:
            if hasattr(task, 'duration'):
                durations.append(task.duration)
        
        if durations:
            self.stats['average_duration'] = sum(durations) / len(durations)
    
    async def _save_progress(self):
        """Lưu tiến độ (có thể mở rộng để lưu vào file hoặc database)"""
        # TODO: Triển khai logic lưu tiến độ
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Lấy thông tin thống kê"""
        self._calculate_stats()
        return self.stats.copy()
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Lấy trạng thái nhiệm vụ
        
        Args:
            task_id: ID nhiệm vụ
        
        Returns:
            Trạng thái nhiệm vụ
        """
        # Kiểm tra nhiệm vụ đang hoạt động
        if task_id in self.active_tasks:
            return self.active_tasks[task_id].status
        
        # Kiểm tra nhiệm vụ đã hoàn thành
        for task in self.completed_tasks:
            if task.task_id == task_id:
                return TaskStatus.COMPLETED
        
        # Kiểm tra nhiệm vụ thất bại
        for task in self.failed_tasks:
            if task.task_id == task_id:
                return TaskStatus.FAILED
        
        # Kiểm tra nhiệm vụ đang chờ
        for task in self.priority_tasks:
            if task.task_id == task_id:
                return TaskStatus.PENDING
        
        return None