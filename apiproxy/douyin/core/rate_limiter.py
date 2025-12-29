#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bộ giới hạn tốc độ thông minh
Ngăn chặn request quá nhanh dẫn đến bị chặn
"""

import asyncio
import time
import logging
from collections import deque
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """Enum chiến lược giới hạn tốc độ"""
    FIXED = "fixed"          # Tốc độ cố định
    ADAPTIVE = "adaptive"    # Tốc độ tự thích ứng
    BURST = "burst"          # Chế độ bùng nổ


@dataclass
class RateLimitConfig:
    """Cấu hình giới hạn tốc độ"""
    max_per_second: int = 2
    max_per_minute: int = 30
    max_per_hour: int = 1000
    burst_size: int = 5
    strategy: RateLimitStrategy = RateLimitStrategy.ADAPTIVE
    cooldown_time: int = 60  # Thời gian làm mát sau khi kích hoạt giới hạn (giây)


class AdaptiveRateLimiter:
    """Bộ giới hạn tốc độ tự thích ứng"""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Khởi tạo bộ giới hạn tốc độ
        
        Args:
            config: Cấu hình giới hạn tốc độ
        """
        self.config = config or RateLimitConfig()
        self.requests = deque()
        self.failures = deque()
        self.lock = asyncio.Lock()
        
        # Giá trị giới hạn hiện tại (có thể điều chỉnh động)
        self.current_max_per_second = self.config.max_per_second
        self.current_max_per_minute = self.config.max_per_minute
        self.current_max_per_hour = self.config.max_per_hour
        
        # Thông tin thống kê
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'rate_adjustments': 0,
            'current_rate': self.current_max_per_second,
            'failure_rate': 0.0
        }
        
        # Trạng thái làm mát
        self.cooldown_until = 0
    
    async def acquire(self) -> bool:
        """
        Lấy quyền request
        
        Returns:
            Có được quyền không
        """
        async with self.lock:
            now = time.time()
            
            # Kiểm tra xem có đang trong thời gian làm mát không
            if self.cooldown_until > now:
                remaining = self.cooldown_until - now
                logger.warning(f"Bộ giới hạn tốc độ đang trong thời gian làm mát, cần chờ thêm {remaining:.1f} giây")
                await asyncio.sleep(remaining)
                self.cooldown_until = 0
            
            # Dọn dẹp các bản ghi đã hết hạn
            self._clean_old_records(now)
            
            # Kiểm tra giới hạn tốc độ
            while not self._can_proceed(now):
                # Tính toán thời gian cần chờ
                wait_time = self._calculate_wait_time(now)
                if wait_time > 0:
                    logger.debug(f"Giới hạn tốc độ, chờ {wait_time:.2f} giây")
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self._clean_old_records(now)
                else:
                    # Không thể tiếp tục, ghi lại request bị chặn
                    self.stats['blocked_requests'] += 1
                    return False
            
            # Ghi lại request
            self.requests.append(now)
            self.stats['total_requests'] += 1
            
            # Điều chỉnh tự thích ứng
            if self.config.strategy == RateLimitStrategy.ADAPTIVE:
                self._adjust_rate()
            
            return True
    
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        if exc_type is not None:
            # Xảy ra lỗi, ghi lại thất bại
            self.record_failure()
    
    def record_failure(self):
        """Ghi lại request thất bại"""
        now = time.time()
        self.failures.append(now)
        
        # Điều chỉnh tự thích ứng
        if self.config.strategy == RateLimitStrategy.ADAPTIVE:
            self._handle_failure()
    
    def _can_proceed(self, now: float) -> bool:
        """Kiểm tra xem có thể tiếp tục request không"""
        # Kiểm tra giới hạn mỗi giây
        recent_second = [r for r in self.requests if now - r < 1]
        if len(recent_second) >= self.current_max_per_second:
            return False
        
        # Kiểm tra giới hạn mỗi phút
        recent_minute = [r for r in self.requests if now - r < 60]
        if len(recent_minute) >= self.current_max_per_minute:
            return False
        
        # Kiểm tra giới hạn mỗi giờ
        recent_hour = [r for r in self.requests if now - r < 3600]
        if len(recent_hour) >= self.current_max_per_hour:
            return False
        
        # Kiểm tra chế độ bùng nổ
        if self.config.strategy == RateLimitStrategy.BURST:
            recent_burst = [r for r in self.requests if now - r < 0.1]
            if len(recent_burst) >= self.config.burst_size:
                return False
        
        return True
    
    def _calculate_wait_time(self, now: float) -> float:
        """Tính toán thời gian cần chờ"""
        wait_times = []
        
        # Tính toán thời gian chờ cho giới hạn mỗi giây
        recent_second = [r for r in self.requests if now - r < 1]
        if len(recent_second) >= self.current_max_per_second:
            oldest_in_second = min(recent_second)
            wait_times.append(1 - (now - oldest_in_second))
        
        # Tính toán thời gian chờ cho giới hạn mỗi phút
        recent_minute = [r for r in self.requests if now - r < 60]
        if len(recent_minute) >= self.current_max_per_minute:
            oldest_in_minute = min(recent_minute)
            wait_times.append(60 - (now - oldest_in_minute))
        
        # Trả về thời gian chờ tối thiểu
        return min(wait_times) if wait_times else 0.1
    
    def _clean_old_records(self, now: float):
        """Dọn dẹp các bản ghi đã hết hạn"""
        # Giữ lại bản ghi request trong 1 giờ gần đây
        while self.requests and now - self.requests[0] > 3600:
            self.requests.popleft()
        
        # Giữ lại bản ghi thất bại trong 10 phút gần đây
        while self.failures and now - self.failures[0] > 600:
            self.failures.popleft()
    
    def _adjust_rate(self):
        """Điều chỉnh tốc độ tự thích ứng"""
        now = time.time()
        
        # Tính toán tỷ lệ thất bại
        recent_failures = [f for f in self.failures if now - f < 60]
        recent_requests = [r for r in self.requests if now - r < 60]
        
        if len(recent_requests) > 10:
            failure_rate = len(recent_failures) / len(recent_requests)
            self.stats['failure_rate'] = failure_rate
            
            if failure_rate > 0.3:
                # Tỷ lệ thất bại quá cao, giảm tốc độ
                self._decrease_rate()
            elif failure_rate < 0.05 and len(recent_requests) > 20:
                # Tỷ lệ thất bại rất thấp, thử tăng tốc độ
                self._increase_rate()
    
    def _handle_failure(self):
        """Xử lý thất bại, điều chỉnh chiến lược giới hạn tốc độ"""
        now = time.time()
        recent_failures = [f for f in self.failures if now - f < 10]
        
        # Nếu số lần thất bại trong thời gian ngắn quá nhiều, kích hoạt làm mát
        if len(recent_failures) >= 5:
            logger.warning(f"Phát hiện thất bại thường xuyên, vào thời gian làm mát {self.config.cooldown_time} giây")
            self.cooldown_until = now + self.config.cooldown_time
            self._decrease_rate()
    
    def _decrease_rate(self):
        """Giảm tốc độ request"""
        old_rate = self.current_max_per_second
        
        self.current_max_per_second = max(1, int(self.current_max_per_second * 0.7))
        self.current_max_per_minute = max(10, int(self.current_max_per_minute * 0.7))
        self.current_max_per_hour = max(100, int(self.current_max_per_hour * 0.7))
        
        if old_rate != self.current_max_per_second:
            self.stats['rate_adjustments'] += 1
            self.stats['current_rate'] = self.current_max_per_second
            logger.info(f"Giảm tốc độ request: {old_rate}/s -> {self.current_max_per_second}/s")
    
    def _increase_rate(self):
        """Tăng tốc độ request"""
        old_rate = self.current_max_per_second
        
        # Không vượt quá giá trị tối đa trong cấu hình
        self.current_max_per_second = min(
            self.config.max_per_second,
            int(self.current_max_per_second * 1.2)
        )
        self.current_max_per_minute = min(
            self.config.max_per_minute,
            int(self.current_max_per_minute * 1.2)
        )
        self.current_max_per_hour = min(
            self.config.max_per_hour,
            int(self.current_max_per_hour * 1.2)
        )
        
        if old_rate != self.current_max_per_second:
            self.stats['rate_adjustments'] += 1
            self.stats['current_rate'] = self.current_max_per_second
            logger.info(f"Tăng tốc độ request: {old_rate}/s -> {self.current_max_per_second}/s")
    
    def get_stats(self) -> Dict[str, Any]:
        """Lấy thông tin thống kê"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Đặt lại thông tin thống kê"""
        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'rate_adjustments': 0,
            'current_rate': self.current_max_per_second,
            'failure_rate': 0.0
        }
    
    def set_cooldown(self, seconds: int):
        """Thiết lập thời gian làm mát thủ công"""
        self.cooldown_until = time.time() + seconds
        logger.info(f"Thiết lập thời gian làm mát thủ công {seconds} giây")


class SimpleRateLimiter:
    """Bộ giới hạn tốc độ đơn giản (tốc độ cố định)"""
    
    def __init__(self, requests_per_second: float = 1.0):
        """
        Khởi tạo bộ giới hạn tốc độ đơn giản
        
        Args:
            requests_per_second: Số request cho phép mỗi giây
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Lấy quyền request"""
        async with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = time.time()
    
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        pass