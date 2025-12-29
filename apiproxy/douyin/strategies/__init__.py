#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module chiến lược tải xuống Douyin
Bao gồm implementation của nhiều chiến lược tải xuống
"""

from .base import IDownloadStrategy, DownloadTask, DownloadResult, TaskType, TaskStatus
from .api_strategy import EnhancedAPIStrategy
from .browser_strategy import BrowserDownloadStrategy as BrowserStrategy
from .retry_strategy import RetryStrategy

__all__ = [
    'IDownloadStrategy',
    'DownloadTask',
    'DownloadResult',
    'TaskType',
    'TaskStatus',
    'EnhancedAPIStrategy',
    'BrowserStrategy',
    'RetryStrategy'
]