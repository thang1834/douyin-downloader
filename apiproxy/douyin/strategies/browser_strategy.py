#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chiến lược tải xuống tự động bằng trình duyệt
Sử dụng Playwright để thực hiện tải xuống tự động bằng trình duyệt
"""

import asyncio
import json
import logging
import time
import os
from typing import Dict, Optional, List, Any
from pathlib import Path

from .base import IDownloadStrategy, DownloadTask, DownloadResult, TaskType

logger = logging.getLogger(__name__)

# Import động Playwright, tránh lỗi khi chưa cài đặt
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright chưa được cài đặt, chiến lược trình duyệt không khả dụng. Vui lòng chạy: pip install playwright && playwright install chromium")


class BrowserDownloadStrategy(IDownloadStrategy):
    """Chiến lược tải xuống tự động bằng trình duyệt"""
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Khởi tạo chiến lược trình duyệt
        
        Args:
            headless: Có phải chế độ không đầu không
            timeout: Thời gian chờ tải trang (milli giây)
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright chưa được cài đặt, vui lòng chạy: pip install playwright && playwright install chromium")
        
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self.initialized = False
        
        # Cấu hình trình duyệt
        self.browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-accelerated-2d-canvas',
            '--disable-gpu'
        ]
        
        # User-Agent
        self.user_agent = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
    
    @property
    def name(self) -> str:
        return "Browser Automation Strategy"
    
    def get_priority(self) -> int:
        """Ưu tiên chiến lược trình duyệt ở mức trung bình"""
        return 50
    
    async def can_handle(self, task: DownloadTask) -> bool:
        """Đánh giá xem có thể xử lý nhiệm vụ không"""
        # Chiến lược trình duyệt có thể xử lý video và bộ ảnh
        return task.task_type in [TaskType.VIDEO, TaskType.IMAGE]
    
    async def initialize(self):
        """Khởi tạo trình duyệt"""
        if self.initialized:
            return
        
        try:
            logger.info("Đang khởi tạo trình duyệt...")
            self.playwright = await async_playwright().start()
            
            # Khởi động trình duyệt
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=self.browser_args
            )
            
            # Tạo context
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.user_agent,
                locale='zh-CN',
                timezone_id='Asia/Shanghai'
            )
            
            # Thêm script chống phát hiện
            await self.context.add_init_script("""
                // Ẩn đặc điểm webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Sửa đổi navigator.plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Sửa đổi navigator.languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                
                // Sửa đổi truy vấn quyền
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            self.initialized = True
            logger.info("Khởi tạo trình duyệt hoàn tất")
            
        except Exception as e:
            logger.error(f"Khởi tạo trình duyệt thất bại: {e}")
            await self.cleanup()
            raise
    
    async def download(self, task: DownloadTask) -> DownloadResult:
        """Thực thi nhiệm vụ tải xuống"""
        start_time = time.time()
        
        try:
            # Khởi tạo trình duyệt
            await self.initialize()
            
            # Tạo trang mới
            page = await self.context.new_page()
            
            try:
                # Thiết lập cookies (nếu có)
                if task.metadata.get('cookies'):
                    await self._set_cookies(page, task.metadata['cookies'])
                
                # Truy cập trang
                logger.info(f"Trình duyệt truy cập: {task.url}")
                await page.goto(task.url, wait_until='networkidle', timeout=self.timeout)
                
                # Chờ trang tải
                await asyncio.sleep(2)
                
                # Xử lý theo loại nhiệm vụ
                if task.task_type == TaskType.VIDEO:
                    result = await self._download_video(page, task)
                else:
                    result = await self._download_images(page, task)
                
                result.duration = time.time() - start_time
                return result
                
            finally:
                await page.close()
                
        except Exception as e:
            logger.error(f"Tải xuống bằng trình duyệt thất bại: {e}")
            return DownloadResult(
                success=False,
                task_id=task.task_id,
                error_message=str(e),
                duration=time.time() - start_time
            )
    
    async def _download_video(self, page: 'Page', task: DownloadTask) -> DownloadResult:
        """Tải xuống video"""
        try:
            # Chờ phần tử video tải
            video_selector = 'video'
            await page.wait_for_selector(video_selector, timeout=10000)
            
            # Lấy thông tin video
            video_info = await page.evaluate("""
                () => {
                    const video = document.querySelector('video');
                    if (!video) return null;
                    
                    // Thử nhiều cách để lấy URL video
                    let videoUrl = video.src || video.currentSrc;
                    
                    // Nếu không có src trực tiếp, thử lấy từ thẻ source
                    if (!videoUrl) {
                        const source = video.querySelector('source');
                        if (source) {
                            videoUrl = source.src;
                        }
                    }
                    
                    // Lấy tiêu đề video
                    let title = document.title;
                    const titleElement = document.querySelector('h1, .video-title, [class*="title"]');
                    if (titleElement) {
                        title = titleElement.innerText || title;
                    }
                    
                    // Lấy thông tin tác giả
                    let author = '';
                    const authorElement = document.querySelector('[class*="author"], [class*="nickname"]');
                    if (authorElement) {
                        author = authorElement.innerText;
                    }
                    
                    return {
                        url: videoUrl,
                        title: title,
                        author: author,
                        duration: video.duration,
                        width: video.videoWidth,
                        height: video.videoHeight
                    };
                }
            """)
            
            if not video_info or not video_info.get('url'):
                # Thử chặn request mạng để lấy URL video
                video_url = await self._intercept_video_url(page)
                if not video_url:
                    return DownloadResult(
                        success=False,
                        task_id=task.task_id,
                        error_message="Không thể lấy URL video"
                    )
                video_info = {'url': video_url}
            
            # Lấy các tài nguyên media khác
            media_urls = await self._extract_media_urls(page)
            
            logger.info(f"Đã lấy thông tin video: {video_info}")
            
            # Trả về kết quả (tải xuống thực tế do component khác xử lý)
            return DownloadResult(
                success=True,
                task_id=task.task_id,
                file_paths=[],  # Ở đây chỉ trả về URL, tải xuống thực tế do class Download xử lý
                metadata={
                    'video_url': video_info['url'],
                    'title': video_info.get('title', ''),
                    'author': video_info.get('author', ''),
                    'media_urls': media_urls,
                    'video_info': video_info
                }
            )
            
        except Exception as e:
            logger.error(f"Tải xuống video thất bại: {e}")
            return DownloadResult(
                success=False,
                task_id=task.task_id,
                error_message=str(e)
            )
    
    async def _download_images(self, page: 'Page', task: DownloadTask) -> DownloadResult:
        """Tải xuống bộ ảnh"""
        try:
            # Chờ ảnh tải
            await page.wait_for_selector('img', timeout=10000)
            
            # Lấy tất cả URL ảnh
            image_urls = await page.evaluate("""
                () => {
                    const images = [];
                    
                    // Tìm container ảnh chính
                    const selectors = [
                        '.swiper-slide img',
                        '[class*="image-list"] img',
                        '[class*="gallery"] img',
                        'img[class*="image"]'
                    ];
                    
                    for (const selector of selectors) {
                        const imgs = document.querySelectorAll(selector);
                        if (imgs.length > 0) {
                            imgs.forEach(img => {
                                const url = img.src || img.dataset.src;
                                if (url && !url.includes('avatar') && !url.includes('icon')) {
                                    images.push(url);
                                }
                            });
                            break;
                        }
                    }
                    
                    // Nếu không tìm thấy, lấy tất cả ảnh lớn
                    if (images.length === 0) {
                        document.querySelectorAll('img').forEach(img => {
                            if (img.naturalWidth > 200 && img.naturalHeight > 200) {
                                const url = img.src || img.dataset.src;
                                if (url) images.push(url);
                            }
                        });
                    }
                    
                    return [...new Set(images)];  // Loại bỏ trùng lặp
                }
            """)
            
            if not image_urls:
                return DownloadResult(
                    success=False,
                    task_id=task.task_id,
                    error_message="Không tìm thấy ảnh"
                )
            
            logger.info(f"Tìm thấy {len(image_urls)} ảnh")
            
            return DownloadResult(
                success=True,
                task_id=task.task_id,
                file_paths=[],
                metadata={
                    'image_urls': image_urls,
                    'count': len(image_urls)
                }
            )
            
        except Exception as e:
            logger.error(f"Tải xuống bộ ảnh thất bại: {e}")
            return DownloadResult(
                success=False,
                task_id=task.task_id,
                error_message=str(e)
            )
    
    async def _intercept_video_url(self, page: 'Page') -> Optional[str]:
        """Chặn request mạng để lấy URL video"""
        video_url = None
        
        def handle_response(response):
            nonlocal video_url
            url = response.url
            # Kiểm tra xem có phải request video không
            if any(ext in url for ext in ['.mp4', '.m3u8', '.flv', 'video', 'stream']):
                if response.status == 200:
                    video_url = url
                    logger.info(f"Đã chặn được URL video: {url}")
        
        # Lắng nghe response
        page.on('response', handle_response)
        
        # Chờ một khoảng thời gian để thu thập request
        await asyncio.sleep(3)
        
        # Thử kích hoạt tải video
        await page.evaluate("""
            () => {
                const video = document.querySelector('video');
                if (video) {
                    video.play();
                }
            }
        """)
        
        await asyncio.sleep(2)
        
        return video_url
    
    async def _extract_media_urls(self, page: 'Page') -> Dict[str, str]:
        """Trích xuất URL tài nguyên media trong trang"""
        media_urls = await page.evaluate("""
            () => {
                const urls = {};
                
                // Lấy URL audio
                const audio = document.querySelector('audio');
                if (audio) {
                    urls.audio = audio.src;
                }
                
                // Lấy ảnh bìa
                const meta_image = document.querySelector('meta[property="og:image"]');
                if (meta_image) {
                    urls.cover = meta_image.content;
                }
                
                // Lấy avatar
                const avatar = document.querySelector('[class*="avatar"] img');
                if (avatar) {
                    urls.avatar = avatar.src;
                }
                
                return urls;
            }
        """)
        
        return media_urls
    
    async def _set_cookies(self, page: 'Page', cookies: Any):
        """Thiết lập cookies"""
        try:
            if isinstance(cookies, str):
                # Phân tích chuỗi cookie
                cookie_list = []
                for item in cookies.split(';'):
                    if '=' in item:
                        key, value = item.strip().split('=', 1)
                        cookie_list.append({
                            'name': key,
                            'value': value,
                            'domain': '.douyin.com',
                            'path': '/'
                        })
                await page.context.add_cookies(cookie_list)
            elif isinstance(cookies, list):
                await page.context.add_cookies(cookies)
            elif isinstance(cookies, dict):
                cookie_list = [
                    {'name': k, 'value': v, 'domain': '.douyin.com', 'path': '/'}
                    for k, v in cookies.items()
                ]
                await page.context.add_cookies(cookie_list)
                
            logger.info("Thiết lập Cookies thành công")
            
        except Exception as e:
            logger.warning(f"Thiết lập Cookies thất bại: {e}")
    
    async def cleanup(self):
        """Dọn dẹp tài nguyên"""
        try:
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            self.initialized = False
            logger.info("Đã dọn dẹp tài nguyên trình duyệt")
            
        except Exception as e:
            logger.error(f"Dọn dẹp tài nguyên trình duyệt thất bại: {e}")
    
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        await self.cleanup()