#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Quản lý hàng đợi
Hỗ trợ lưu trữ nhiệm vụ và khôi phục điểm dừng
"""

import asyncio
import json
import sqlite3
import time
import logging
import pickle
from typing import List, Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from apiproxy.douyin.strategies.base import DownloadTask, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class PersistentQueue:
    """Quản lý hàng đợi lưu trữ"""
    
    def __init__(
        self,
        db_path: str = "download_queue.db",
        max_size: int = 10000,
        checkpoint_interval: int = 60
    ):
        """
        Khởi tạo quản lý hàng đợi
        
        Args:
            db_path: Đường dẫn file database
            max_size: Dung lượng tối đa hàng đợi
            checkpoint_interval: Khoảng thời gian lưu checkpoint (giây)
        """
        self.db_path = Path(db_path)
        self.max_size = max_size
        self.checkpoint_interval = checkpoint_interval
        
        self.conn: Optional[sqlite3.Connection] = None
        self.queue = asyncio.Queue(maxsize=max_size)
        self._checkpoint_task = None
        self._lock = asyncio.Lock()
        
        # Khởi tạo database
        self._init_database()
        
        # Khôi phục các nhiệm vụ chưa hoàn thành
        self._restore_tasks()
    
    def _init_database(self):
        """Khởi tạo database"""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        cursor = self.conn.cursor()
        
        # Tạo bảng nhiệm vụ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                task_type TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                metadata TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL,
                error_message TEXT,
                result TEXT
            )
        ''')
        
        # Tạo index
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_priority ON tasks(priority DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at)')
        
        # Tạo bảng tiến độ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                total_tasks INTEGER,
                pending_tasks INTEGER,
                active_tasks INTEGER,
                completed_tasks INTEGER,
                failed_tasks INTEGER,
                success_rate REAL,
                average_duration REAL
            )
        ''')
        
        self.conn.commit()
        logger.info(f"Khởi tạo database hoàn tất: {self.db_path}")
    
    def _restore_tasks(self):
        """Khôi phục các nhiệm vụ chưa hoàn thành từ database"""
        cursor = self.conn.cursor()
        
        # Đặt lại tất cả nhiệm vụ có trạng thái PROCESSING thành PENDING
        cursor.execute('''
            UPDATE tasks 
            SET status = ?, updated_at = ?
            WHERE status = ?
        ''', (TaskStatus.PENDING.value, time.time(), TaskStatus.PROCESSING.value))
        
        # Lấy tất cả nhiệm vụ đang chờ xử lý
        cursor.execute('''
            SELECT task_id, url, task_type, priority, retry_count, max_retries, metadata, created_at
            FROM tasks
            WHERE status IN (?, ?)
            ORDER BY priority DESC, created_at ASC
        ''', (TaskStatus.PENDING.value, TaskStatus.RETRYING.value))
        
        restored_count = 0
        for row in cursor.fetchall():
            task = self._row_to_task(row)
            if task:
                try:
                    self.queue.put_nowait(task)
                    restored_count += 1
                except asyncio.QueueFull:
                    break
        
        self.conn.commit()
        
        if restored_count > 0:
            logger.info(f"Đã khôi phục {restored_count} nhiệm vụ chưa hoàn thành từ database")
    
    def _row_to_task(self, row: tuple) -> Optional[DownloadTask]:
        """Chuyển đổi hàng database thành đối tượng nhiệm vụ"""
        try:
            task_id, url, task_type, priority, retry_count, max_retries, metadata_str, created_at = row
            
            metadata = {}
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                except:
                    pass
            
            return DownloadTask(
                task_id=task_id,
                url=url,
                task_type=TaskType(task_type),
                priority=priority,
                retry_count=retry_count,
                max_retries=max_retries,
                metadata=metadata,
                created_at=created_at
            )
        except Exception as e:
            logger.error(f"Chuyển đổi nhiệm vụ thất bại: {e}")
            return None
    
    async def add_task(self, task: DownloadTask) -> bool:
        """
        Thêm nhiệm vụ vào hàng đợi
        
        Args:
            task: Nhiệm vụ tải xuống
        
        Returns:
            Có thêm thành công không
        """
        async with self._lock:
            try:
                # Lưu vào database
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO tasks (
                        task_id, url, task_type, priority, status, 
                        retry_count, max_retries, metadata, 
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task.task_id,
                    task.url,
                    task.task_type.value,
                    task.priority,
                    task.status.value,
                    task.retry_count,
                    task.max_retries,
                    json.dumps(task.metadata),
                    task.created_at,
                    task.updated_at
                ))
                self.conn.commit()
                
                # Thêm vào hàng đợi bộ nhớ
                await self.queue.put(task)
                
                logger.debug(f"Nhiệm vụ {task.task_id} đã được thêm vào hàng đợi")
                return True
                
            except Exception as e:
                logger.error(f"Thêm nhiệm vụ thất bại: {e}")
                return False
    
    async def get_task(self, timeout: float = 1.0) -> Optional[DownloadTask]:
        """
        Lấy nhiệm vụ từ hàng đợi
        
        Args:
            timeout: Thời gian chờ
        
        Returns:
            Nhiệm vụ tải xuống
        """
        try:
            task = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            
            # Cập nhật trạng thái database
            await self.update_task_status(task.task_id, TaskStatus.PROCESSING)
            
            return task
            
        except asyncio.TimeoutError:
            return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
        result: Optional[Dict] = None
    ):
        """
        Cập nhật trạng thái nhiệm vụ
        
        Args:
            task_id: ID nhiệm vụ
            status: Trạng thái mới
            error_message: Thông báo lỗi
            result: Kết quả thực thi
        """
        async with self._lock:
            cursor = self.conn.cursor()
            
            update_fields = {
                'status': status.value,
                'updated_at': time.time()
            }
            
            if error_message:
                update_fields['error_message'] = error_message
            
            if result:
                update_fields['result'] = json.dumps(result)
            
            if status == TaskStatus.COMPLETED:
                update_fields['completed_at'] = time.time()
            
            # Xây dựng câu lệnh UPDATE
            set_clause = ', '.join([f'{k} = ?' for k in update_fields.keys()])
            values = list(update_fields.values()) + [task_id]
            
            cursor.execute(
                f'UPDATE tasks SET {set_clause} WHERE task_id = ?',
                values
            )
            self.conn.commit()
    
    async def requeue_task(self, task: DownloadTask):
        """
        Đưa nhiệm vụ trở lại hàng đợi
        
        Args:
            task: Nhiệm vụ tải xuống
        """
        task.retry_count += 1
        task.status = TaskStatus.RETRYING
        task.updated_at = time.time()
        
        await self.add_task(task)
        logger.info(f"Nhiệm vụ {task.task_id} đã được đưa trở lại hàng đợi (thử lại {task.retry_count}/{task.max_retries})")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Lấy thông tin thống kê hàng đợi"""
        cursor = self.conn.cursor()
        
        # Thống kê số nhiệm vụ theo trạng thái
        cursor.execute('''
            SELECT status, COUNT(*) 
            FROM tasks 
            GROUP BY status
        ''')
        
        status_counts = {}
        for status, count in cursor.fetchall():
            status_counts[status] = count
        
        # Tính toán tỷ lệ thành công
        total = sum(status_counts.values())
        completed = status_counts.get(TaskStatus.COMPLETED.value, 0)
        success_rate = (completed / total * 100) if total > 0 else 0
        
        # Tính toán thời gian trung bình
        cursor.execute('''
            SELECT AVG(completed_at - created_at)
            FROM tasks
            WHERE status = ? AND completed_at IS NOT NULL
        ''', (TaskStatus.COMPLETED.value,))
        
        avg_duration = cursor.fetchone()[0] or 0
        
        stats = {
            'total_tasks': total,
            'pending_tasks': status_counts.get(TaskStatus.PENDING.value, 0),
            'processing_tasks': status_counts.get(TaskStatus.PROCESSING.value, 0),
            'completed_tasks': completed,
            'failed_tasks': status_counts.get(TaskStatus.FAILED.value, 0),
            'retrying_tasks': status_counts.get(TaskStatus.RETRYING.value, 0),
            'success_rate': success_rate,
            'average_duration': avg_duration,
            'queue_size': self.queue.qsize()
        }
        
        return stats
    
    async def save_progress(self):
        """Lưu tiến độ vào database"""
        stats = self.get_statistics()
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO progress (
                timestamp, total_tasks, pending_tasks, active_tasks,
                completed_tasks, failed_tasks, success_rate, average_duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            time.time(),
            stats['total_tasks'],
            stats['pending_tasks'],
            stats['processing_tasks'],
            stats['completed_tasks'],
            stats['failed_tasks'],
            stats['success_rate'],
            stats['average_duration']
        ))
        self.conn.commit()
        
        logger.debug("Đã lưu tiến độ")
    
    async def start_checkpoint(self):
        """Khởi động nhiệm vụ lưu checkpoint"""
        if not self._checkpoint_task:
            self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())
            logger.info("Nhiệm vụ lưu checkpoint đã khởi động")
    
    async def stop_checkpoint(self):
        """Dừng nhiệm vụ lưu checkpoint"""
        if self._checkpoint_task:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except asyncio.CancelledError:
                pass
            self._checkpoint_task = None
            logger.info("Nhiệm vụ lưu checkpoint đã dừng")
    
    async def _checkpoint_loop(self):
        """Vòng lặp lưu checkpoint"""
        while True:
            try:
                await asyncio.sleep(self.checkpoint_interval)
                await self.save_progress()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lưu checkpoint thất bại: {e}")
    
    def get_recent_progress(self, hours: int = 24) -> List[Dict]:
        """
        Lấy các bản ghi tiến độ gần đây
        
        Args:
            hours: Lấy bản ghi trong bao nhiêu giờ gần đây
        
        Returns:
            Danh sách bản ghi tiến độ
        """
        cursor = self.conn.cursor()
        since = time.time() - hours * 3600
        
        cursor.execute('''
            SELECT timestamp, total_tasks, completed_tasks, failed_tasks, success_rate
            FROM progress
            WHERE timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 100
        ''', (since,))
        
        records = []
        for row in cursor.fetchall():
            records.append({
                'timestamp': row[0],
                'total_tasks': row[1],
                'completed_tasks': row[2],
                'failed_tasks': row[3],
                'success_rate': row[4]
            })
        
        return records
    
    def cleanup_old_tasks(self, days: int = 7):
        """
        Dọn dẹp các bản ghi nhiệm vụ cũ
        
        Args:
            days: Giữ lại bản ghi trong bao nhiêu ngày gần đây
        """
        cursor = self.conn.cursor()
        cutoff = time.time() - days * 86400
        
        cursor.execute('''
            DELETE FROM tasks
            WHERE status IN (?, ?) AND updated_at < ?
        ''', (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, cutoff))
        
        deleted = cursor.rowcount
        self.conn.commit()
        
        if deleted > 0:
            logger.info(f"Đã dọn dẹp {deleted} bản ghi nhiệm vụ cũ")
    
    def export_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict]:
        """
        Xuất danh sách nhiệm vụ
        
        Args:
            status: Lọc theo trạng thái
        
        Returns:
            Danh sách nhiệm vụ
        """
        cursor = self.conn.cursor()
        
        if status:
            cursor.execute('''
                SELECT * FROM tasks WHERE status = ?
                ORDER BY created_at DESC
            ''', (status.value,))
        else:
            cursor.execute('''
                SELECT * FROM tasks
                ORDER BY created_at DESC
            ''')
        
        tasks = []
        columns = [desc[0] for desc in cursor.description]
        
        for row in cursor.fetchall():
            task_dict = dict(zip(columns, row))
            # Phân tích trường JSON
            if task_dict.get('metadata'):
                try:
                    task_dict['metadata'] = json.loads(task_dict['metadata'])
                except:
                    pass
            if task_dict.get('result'):
                try:
                    task_dict['result'] = json.loads(task_dict['result'])
                except:
                    pass
            tasks.append(task_dict)
        
        return tasks
    
    def close(self):
        """Đóng kết nối database"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Đã đóng kết nối database")
    
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.start_checkpoint()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        await self.stop_checkpoint()
        await self.save_progress()
        self.close()