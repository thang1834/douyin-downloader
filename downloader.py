#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Trình tải xuống Douyin - Phiên bản nâng cao thống nhất
Hỗ trợ tải xuống hàng loạt video, hình ảnh, trang người dùng, bộ sưu tập và nhiều nội dung khác
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import argparse
import yaml

# Thư viện bên thứ ba
try:
    import aiohttp
    import requests
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich import print as rprint
except ImportError as e:
    print(f"Vui lòng cài đặt các phụ thuộc cần thiết: pip install aiohttp requests rich pyyaml")
    sys.exit(1)

# Thêm đường dẫn dự án
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Nhập các module dự án
from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls
from apiproxy.douyin.result import Result
from apiproxy.common.utils import Utils
from apiproxy.douyin.auth.cookie_manager import AutoCookieManager
from apiproxy.douyin.database import DataBase

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('downloader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Rich console
console = Console()


class ContentType:
    """Enum loại nội dung"""
    VIDEO = "video"
    IMAGE = "image" 
    USER = "user"
    MIX = "mix"
    MUSIC = "music"
    LIVE = "live"


class DownloadStats:
    """Thống kê tải xuống"""
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
    
    @property
    def success_rate(self):
        return (self.success / self.total * 100) if self.total > 0 else 0
    
    @property
    def elapsed_time(self):
        return time.time() - self.start_time
    
    def to_dict(self):
        return {
            'total': self.total,
            'success': self.success,
            'failed': self.failed,
            'skipped': self.skipped,
            'success_rate': f"{self.success_rate:.1f}%",
            'elapsed_time': f"{self.elapsed_time:.1f}s"
        }


class RateLimiter:
    """Bộ giới hạn tốc độ"""
    def __init__(self, max_per_second: float = 2):
        self.max_per_second = max_per_second
        self.min_interval = 1.0 / max_per_second
        self.last_request = 0
    
    async def acquire(self):
        """Lấy quyền truy cập"""
        current = time.time()
        time_since_last = current - self.last_request
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)
        self.last_request = time.time()


class RetryManager:
    """Quản lý thử lại"""
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_delays = [1, 2, 5]  # Độ trễ thử lại
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """Thực thi hàm và tự động thử lại"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(f"Lần thử {attempt + 1} thất bại: {e}, sẽ thử lại sau {delay} giây...")
                    await asyncio.sleep(delay)
        raise last_error


class UnifiedDownloader:
    """Trình tải xuống thống nhất"""
    
    def __init__(self, config_path: str = "config.yml"):
        self.config = self._load_config(config_path)
        self.urls_helper = Urls()
        self.result_helper = Result()
        self.utils = Utils()
        
        # Khởi tạo các thành phần
        self.stats = DownloadStats()
        self.rate_limiter = RateLimiter(max_per_second=2)
        self.retry_manager = RetryManager(max_retries=self.config.get('retry_times', 3))
        
        # Cookie và request headers (khởi tạo trễ, hỗ trợ tự động lấy)
        self.cookies = self.config.get('cookies') if 'cookies' in self.config else self.config.get('cookie')
        self.auto_cookie = bool(self.config.get('auto_cookie')) or (isinstance(self.config.get('cookie'), str) and self.config.get('cookie') == 'auto') or (isinstance(self.config.get('cookies'), str) and self.config.get('cookies') == 'auto')
        self.headers = {**douyin_headers}
        # Tránh server sử dụng brotli khiến aiohttp không thể giải nén (sẽ có phản hồi rỗng nếu chưa cài thư viện brotli)
        self.headers['accept-encoding'] = 'gzip, deflate'
        # Tải xuống tăng dần và cơ sở dữ liệu
        self.increase_cfg: Dict[str, Any] = self.config.get('increase', {}) or {}
        self.enable_database: bool = bool(self.config.get('database', True))
        self.db: Optional[DataBase] = DataBase() if self.enable_database else None
        
        # Đường dẫn lưu
        self.save_path = Path(self.config.get('path', './Downloaded'))
        self.save_path.mkdir(parents=True, exist_ok=True)
        
    def _load_config(self, config_path: str) -> Dict:
        """Tải cấu hình từ file"""
        if not os.path.exists(config_path):
            # Tương thích với tên file cấu hình: ưu tiên config.yml, sau đó config_simple.yml
            alt_path = 'config_simple.yml'
            if os.path.exists(alt_path):
                config_path = alt_path
            else:
                # Trả về cấu hình rỗng, sẽ được quyết định bởi tham số dòng lệnh
                return {}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Tương thích cấu hình đơn giản: links/link, output_dir/path, cookie/cookies
        if 'links' in config and 'link' not in config:
            config['link'] = config['links']
        if 'output_dir' in config and 'path' not in config:
            config['path'] = config['output_dir']
        if 'cookie' in config and 'cookies' not in config:
            config['cookies'] = config['cookie']
        if isinstance(config.get('cookies'), str) and config.get('cookies') == 'auto':
            config['auto_cookie'] = True
        
        # Cho phép không có link (truyền qua dòng lệnh)
        # Nếu cả hai đều không có, sẽ được nhắc trong quá trình chạy
        
        return config
    
    def _build_cookie_string(self) -> str:
        """Xây dựng chuỗi Cookie"""
        if isinstance(self.cookies, str):
            return self.cookies
        elif isinstance(self.cookies, dict):
            return '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
        elif isinstance(self.cookies, list):
            # Hỗ trợ danh sách cookies từ AutoCookieManager
            try:
                kv = {c.get('name'): c.get('value') for c in self.cookies if c.get('name') and c.get('value')}
                return '; '.join([f'{k}={v}' for k, v in kv.items()])
            except Exception:
                return ''
        return ''

    async def _initialize_cookies_and_headers(self):
        """Khởi tạo Cookie và request headers (hỗ trợ tự động lấy)"""
        # Nếu cấu hình là chuỗi 'auto', coi như chưa cung cấp, kích hoạt tự động lấy
        if isinstance(self.cookies, str) and self.cookies.strip().lower() == 'auto':
            self.cookies = None
        
        # Nếu đã cung cấp cookies rõ ràng, sử dụng trực tiếp
        cookie_str = self._build_cookie_string()
        if cookie_str:
            self.headers['Cookie'] = cookie_str
            # Đồng thời thiết lập vào douyin_headers toàn cục, đảm bảo tất cả API request đều có thể sử dụng
            from apiproxy.douyin import douyin_headers
            douyin_headers['Cookie'] = cookie_str
            return
        
        # Tự động lấy Cookie
        if self.auto_cookie:
            try:
                console.print("[cyan]🔐 Đang tự động lấy Cookie...[/cyan]")
                async with AutoCookieManager(cookie_file='cookies.pkl', headless=False) as cm:
                    cookies_list = await cm.get_cookies()
                    if cookies_list:
                        self.cookies = cookies_list
                        cookie_str = self._build_cookie_string()
                        if cookie_str:
                            self.headers['Cookie'] = cookie_str
                            # Đồng thời thiết lập vào douyin_headers toàn cục, đảm bảo tất cả API request đều có thể sử dụng
                            from apiproxy.douyin import douyin_headers
                            douyin_headers['Cookie'] = cookie_str
                            console.print("[green]✅ Lấy Cookie thành công[/green]")
                            return
                console.print("[yellow]⚠️ Tự động lấy Cookie thất bại hoặc rỗng, tiếp tục thử chế độ không Cookie[/yellow]")
            except Exception as e:
                logger.warning(f"Tự động lấy Cookie thất bại: {e}")
                console.print("[yellow]⚠️ Tự động lấy Cookie thất bại, tiếp tục thử chế độ không Cookie[/yellow]")
        
        # Không lấy được Cookie thì không thiết lập, sử dụng headers mặc định
    
    def detect_content_type(self, url: str) -> ContentType:
        """Phát hiện loại nội dung URL"""
        if '/user/' in url:
            return ContentType.USER
        elif '/video/' in url or 'v.douyin.com' in url:
            return ContentType.VIDEO
        elif '/note/' in url:
            return ContentType.IMAGE
        elif '/collection/' in url or '/mix/' in url:
            return ContentType.MIX
        elif '/music/' in url:
            return ContentType.MUSIC
        elif 'live.douyin.com' in url:
            return ContentType.LIVE
        else:
            return ContentType.VIDEO  # Mặc định coi là video
    
    async def resolve_short_url(self, url: str) -> str:
        """Phân giải liên kết ngắn"""
        if 'v.douyin.com' in url:
            try:
                # Sử dụng request đồng bộ để lấy redirect
                response = requests.get(url, headers=self.headers, allow_redirects=True, timeout=10)
                final_url = response.url
                logger.info(f"Phân giải liên kết ngắn: {url} -> {final_url}")
                return final_url
            except Exception as e:
                logger.warning(f"Phân giải liên kết ngắn thất bại: {e}")
        return url
    
    def extract_id_from_url(self, url: str, content_type: ContentType = None) -> Optional[str]:
        """Trích xuất ID từ URL
        
        Args:
            url: URL cần phân tích
            content_type: Loại nội dung (tùy chọn, dùng để hướng dẫn trích xuất)
        """
        # Nếu đã biết là trang người dùng, trích xuất trực tiếp user ID
        if content_type == ContentType.USER or '/user/' in url:
            user_patterns = [
                r'/user/([\w-]+)',
                r'sec_uid=([\w-]+)'
            ]
            
            for pattern in user_patterns:
                match = re.search(pattern, url)
                if match:
                    user_id = match.group(1)
                    logger.info(f"Trích xuất được user ID: {user_id}")
                    return user_id
        
        # Mẫu video ID (ưu tiên)
        video_patterns = [
            r'/video/(\d+)',
            r'/note/(\d+)',
            r'modal_id=(\d+)',
            r'aweme_id=(\d+)',
            r'item_id=(\d+)'
        ]
        
        for pattern in video_patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.info(f"Trích xuất được video ID: {video_id}")
                return video_id
        
        # Các mẫu khác
        other_patterns = [
            r'/collection/(\d+)',
            r'/music/(\d+)'
        ]
        
        for pattern in other_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # Thử trích xuất ID số từ URL
        number_match = re.search(r'(\d{15,20})', url)
        if number_match:
            video_id = number_match.group(1)
            logger.info(f"Trích xuất được ID số từ URL: {video_id}")
            return video_id
        
        logger.error(f"Không thể trích xuất ID từ URL: {url}")
        return None

    def _get_aweme_id_from_info(self, info: Dict) -> Optional[str]:
        """Trích xuất aweme_id từ thông tin aweme"""
        try:
            if 'aweme_id' in info:
                return str(info.get('aweme_id'))
            # Cấu trúc aweme_detail
            return str(info.get('aweme', {}).get('aweme_id') or info.get('aweme_id'))
        except Exception:
            return None

    def _get_sec_uid_from_info(self, info: Dict) -> Optional[str]:
        """Trích xuất sec_uid tác giả từ thông tin aweme"""
        try:
            return info.get('author', {}).get('sec_uid')
        except Exception:
            return None

    def _should_skip_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None) -> bool:
        """Dựa vào cấu hình tăng dần và bản ghi database để quyết định có bỏ qua tải xuống không"""
        if not self.db:
            return False
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id:
            return False

        try:
            if context == 'post' and self.increase_cfg.get('post', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_post(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'like' and self.increase_cfg.get('like', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                return bool(self.db.get_user_like(sec, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'mix' and self.increase_cfg.get('mix', False):
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                return bool(self.db.get_mix(sec, mid, int(aweme_id)) if aweme_id.isdigit() else None)
            if context == 'music' and self.increase_cfg.get('music', False):
                mid = music_id or ''
                return bool(self.db.get_music(mid, int(aweme_id)) if aweme_id.isdigit() else None)
        except Exception:
            return False
        return False

    def _record_increment(self, context: str, info: Dict, mix_id: Optional[str] = None, music_id: Optional[str] = None, sec_uid: Optional[str] = None):
        """Ghi bản ghi database sau khi tải xuống thành công"""
        if not self.db:
            return
        aweme_id = self._get_aweme_id_from_info(info)
        if not aweme_id or not aweme_id.isdigit():
            return
        try:
            if context == 'post':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_post(sec, int(aweme_id), info)
            elif context == 'like':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                self.db.insert_user_like(sec, int(aweme_id), info)
            elif context == 'mix':
                sec = sec_uid or self._get_sec_uid_from_info(info) or ''
                mid = mix_id or ''
                self.db.insert_mix(sec, mid, int(aweme_id), info)
            elif context == 'music':
                mid = music_id or ''
                self.db.insert_music(mid, int(aweme_id), info)
        except Exception:
            pass
    
    async def download_single_video(self, url: str, progress=None) -> bool:
        """Tải xuống một video/ảnh văn bản"""
        try:
            # Phân tích liên kết rút gọn
            url = await self.resolve_short_url(url)
            
            # Trích xuất ID
            video_id = self.extract_id_from_url(url, ContentType.VIDEO)
            if not video_id:
                logger.error(f"Không thể trích xuất ID từ URL: {url}")
                return False
            
            # Nếu không trích xuất được video ID, thử dùng trực tiếp như video ID
            if not video_id and '/user/' not in url:
                # Có thể liên kết rút gọn trực tiếp chứa video ID
                video_id = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                logger.info(f"Thử trích xuất ID từ đường dẫn liên kết rút gọn: {video_id}")
            
            if not video_id:
                logger.error(f"Không thể trích xuất video ID từ URL: {url}")
                return False
            
            # Giới hạn tốc độ
            await self.rate_limiter.acquire()
            
            # Lấy thông tin video
            if progress:
                progress.update(task_id=progress.task_ids[-1], description="Đang lấy thông tin video...")
            
            video_info = await self.retry_manager.execute_with_retry(
                self._fetch_video_info, video_id
            )
            
            if not video_info:
                logger.error(f"Không thể lấy thông tin video: {video_id}")
                self.stats.failed += 1
                return False
            
            # Tải xuống file video
            if progress:
                progress.update(task_id=progress.task_ids[-1], description="Đang tải xuống file video...")
            
            success = await self._download_media_files(video_info, progress)
            
            if success:
                self.stats.success += 1
                logger.info(f"✅ Tải xuống thành công: {url}")
            else:
                self.stats.failed += 1
                logger.error(f"❌ Tải xuống thất bại: {url}")
            
            return success
            
        except Exception as e:
            logger.error(f"Lỗi khi tải xuống video {url}: {e}")
            self.stats.failed += 1
            return False
        finally:
            self.stats.total += 1
    
    async def _fetch_video_info(self, video_id: str) -> Optional[Dict]:
        """Lấy thông tin video"""
        try:
            # Sử dụng trực tiếp class Douyin thành công từ DouYinCommand.py
            from apiproxy.douyin.douyin import Douyin
            
            # Tạo instance Douyin
            dy = Douyin(database=False)
            
            # Thiết lập cookies của chúng ta vào douyin_headers
            if hasattr(self, 'cookies') and self.cookies:
                cookie_str = self._build_cookie_string()
                if cookie_str:
                    from apiproxy.douyin import douyin_headers
                    douyin_headers['Cookie'] = cookie_str
                    logger.info(f"Đã thiết lập Cookie vào class Douyin: {cookie_str[:100]}...")
            
            try:
                # Sử dụng implementation thành công hiện có
                result = dy.getAwemeInfo(video_id)
                if result:
                    logger.info(f"Class Douyin đã lấy thông tin video thành công: {result.get('desc', '')[:30]}")
                    return result
                else:
                    logger.error("Class Douyin trả về kết quả rỗng")
                    
            except Exception as e:
                logger.error(f"Class Douyin lấy thông tin video thất bại: {e}")
                
        except Exception as e:
            logger.error(f"Import hoặc sử dụng class Douyin thất bại: {e}")
            import traceback
            traceback.print_exc()
        
        # Nếu class Douyin thất bại, thử interface dự phòng (iesdouyin, không cần X-Bogus)
        try:
            fallback_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
            logger.info(f"Thử interface dự phòng để lấy thông tin video: {fallback_url}")
            
            # Thiết lập header yêu cầu phổ biến hơn
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(fallback_url, headers=headers, timeout=15) as response:
                    logger.info(f"Trạng thái phản hồi interface dự phòng: {response.status}")
                    if response.status != 200:
                        logger.error(f"Yêu cầu interface dự phòng thất bại, mã trạng thái: {response.status}")
                        return None
                    
                    text = await response.text()
                    logger.info(f"Độ dài nội dung phản hồi interface dự phòng: {len(text)}")
                    
                    if not text:
                        logger.error("Phản hồi interface dự phòng rỗng")
                        return None
                    
                    try:
                        data = json.loads(text)
                        logger.info(f"Dữ liệu trả về từ interface dự phòng: {data}")
                        
                        item_list = (data or {}).get('item_list') or []
                        if item_list:
                            aweme_detail = item_list[0]
                            logger.info("Interface dự phòng đã lấy thông tin video thành công")
                            return aweme_detail
                        else:
                            logger.error("Dữ liệu trả về từ interface dự phòng không có item_list")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Phân tích JSON interface dự phòng thất bại: {e}")
                        logger.error(f"Nội dung phản hồi gốc: {text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Lấy thông tin video từ interface dự phòng thất bại: {e}")
        
        return None
    
    def _build_detail_params(self, aweme_id: str) -> str:
        """Xây dựng tham số API chi tiết"""
        # Sử dụng cùng định dạng tham số với douyinapi.py hiện có
        params = [
            f'aweme_id={aweme_id}',
            'device_platform=webapp',
            'aid=6383'
        ]
        return '&'.join(params)
    
    async def _download_media_files(self, video_info: Dict, progress=None) -> bool:
        """Tải xuống file media"""
        try:
            # Đánh giá loại
            is_image = bool(video_info.get('images'))
            
            # Xây dựng đường dẫn lưu
            author_name = video_info.get('author', {}).get('nickname', 'unknown')
            desc = video_info.get('desc', '')[:50].replace('/', '_')
            # Tương thích create_time là timestamp hoặc chuỗi đã định dạng
            raw_create_time = video_info.get('create_time')
            dt_obj = None
            if isinstance(raw_create_time, (int, float)):
                dt_obj = datetime.fromtimestamp(raw_create_time)
            elif isinstance(raw_create_time, str) and raw_create_time:
                for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                    try:
                        dt_obj = datetime.strptime(raw_create_time, fmt)
                        break
                    except Exception:
                        pass
            if dt_obj is None:
                dt_obj = datetime.fromtimestamp(time.time())
            create_time = dt_obj.strftime('%Y-%m-%d_%H-%M-%S')
            
            folder_name = f"{create_time}_{desc}" if desc else create_time
            save_dir = self.save_path / author_name / folder_name
            save_dir.mkdir(parents=True, exist_ok=True)
            
            success = True
            
            if is_image:
                # Tải xuống ảnh văn bản (không có watermark)
                images = video_info.get('images', [])
                for i, img in enumerate(images):
                    img_url = self._get_best_quality_url(img.get('url_list', []))
                    if img_url:
                        file_path = save_dir / f"image_{i+1}.jpg"
                        if await self._download_file(img_url, file_path):
                            logger.info(f"Tải xuống ảnh {i+1}/{len(images)}: {file_path.name}")
                        else:
                            success = False
            else:
                # Tải xuống video (không có watermark)
                video_url = self._get_no_watermark_url(video_info)
                if video_url:
                    file_path = save_dir / f"{folder_name}.mp4"
                    if await self._download_file(video_url, file_path):
                        logger.info(f"Tải xuống video: {file_path.name}")
                    else:
                        success = False
                
                # Tải xuống âm thanh
                if self.config.get('music', True):
                    music_url = self._get_music_url(video_info)
                    if music_url:
                        file_path = save_dir / f"{folder_name}_music.mp3"
                        await self._download_file(music_url, file_path)
            
            # Tải xuống ảnh bìa
            if self.config.get('cover', True):
                cover_url = self._get_cover_url(video_info)
                if cover_url:
                    file_path = save_dir / f"{folder_name}_cover.jpg"
                    await self._download_file(cover_url, file_path)
            
            # Lưu dữ liệu JSON
            if self.config.get('json', True):
                json_path = save_dir / f"{folder_name}_data.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)
            
            return success
            
        except Exception as e:
            logger.error(f"Tải xuống file media thất bại: {e}")
            return False
    
    def _get_no_watermark_url(self, video_info: Dict) -> Optional[str]:
        """Lấy URL video không có watermark"""
        try:
            # Ưu tiên sử dụng play_addr_h264
            play_addr = video_info.get('video', {}).get('play_addr_h264') or \
                       video_info.get('video', {}).get('play_addr')
            
            if play_addr:
                url_list = play_addr.get('url_list', [])
                if url_list:
                    # Thay thế URL để lấy phiên bản không có watermark
                    url = url_list[0]
                    url = url.replace('playwm', 'play')
                    url = url.replace('720p', '1080p')
                    return url
            
            # Dự phòng: download_addr
            download_addr = video_info.get('video', {}).get('download_addr')
            if download_addr:
                url_list = download_addr.get('url_list', [])
                if url_list:
                    return url_list[0]
                    
        except Exception as e:
            logger.error(f"Lấy URL không có watermark thất bại: {e}")
        
        return None
    
    def _get_best_quality_url(self, url_list: List[str]) -> Optional[str]:
        """Lấy URL chất lượng cao nhất"""
        if not url_list:
            return None
        
        # Ưu tiên chọn URL chứa từ khóa cụ thể
        for keyword in ['1080', 'origin', 'high']:
            for url in url_list:
                if keyword in url:
                    return url
        
        # Trả về URL đầu tiên
        return url_list[0]
    
    def _get_music_url(self, video_info: Dict) -> Optional[str]:
        """Lấy URL nhạc"""
        try:
            music = video_info.get('music', {})
            play_url = music.get('play_url', {})
            url_list = play_url.get('url_list', [])
            return url_list[0] if url_list else None
        except:
            return None
    
    def _get_cover_url(self, video_info: Dict) -> Optional[str]:
        """Lấy URL ảnh bìa"""
        try:
            cover = video_info.get('video', {}).get('cover', {})
            url_list = cover.get('url_list', [])
            return self._get_best_quality_url(url_list)
        except:
            return None
    
    async def _download_file(self, url: str, save_path: Path) -> bool:
        """Tải xuống file"""
        try:
            if save_path.exists():
                logger.info(f"File đã tồn tại, bỏ qua: {save_path.name}")
                return True
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, 'wb') as f:
                            f.write(content)
                        return True
                    else:
                        logger.error(f"Tải xuống thất bại, mã trạng thái: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Tải xuống file thất bại {url}: {e}")
            return False
    
    async def download_user_page(self, url: str) -> bool:
        """Tải xuống nội dung trang chủ người dùng"""
        try:
            # Trích xuất ID người dùng
            user_id = self.extract_id_from_url(url, ContentType.USER)
            if not user_id:
                logger.error(f"Không thể trích xuất ID người dùng từ URL: {url}")
                return False
            
            console.print(f"\n[cyan]Đang lấy danh sách tác phẩm của người dùng {user_id}...[/cyan]")
            
            # Dựa vào cấu hình để tải xuống các loại nội dung khác nhau
            mode = self.config.get('mode', ['post'])
            if isinstance(mode, str):
                mode = [mode]
            
            # Tăng thống kê tổng số nhiệm vụ
            total_posts = 0
            if 'post' in mode:
                total_posts += self.config.get('number', {}).get('post', 0) or 1
            if 'like' in mode:
                total_posts += self.config.get('number', {}).get('like', 0) or 1
            if 'mix' in mode:
                total_posts += self.config.get('number', {}).get('allmix', 0) or 1
            
            self.stats.total += total_posts
            
            for m in mode:
                if m == 'post':
                    await self._download_user_posts(user_id)
                elif m == 'like':
                    await self._download_user_likes(user_id)
                elif m == 'mix':
                    await self._download_user_mixes(user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Tải xuống trang chủ người dùng thất bại: {e}")
            return False
    
    async def _download_user_posts(self, user_id: str):
        """Tải xuống tác phẩm người dùng đã đăng"""
        max_count = self.config.get('number', {}).get('post', 0)
        cursor = 0
        downloaded = 0
        
        console.print(f"\n[green]Bắt đầu tải xuống tác phẩm người dùng đã đăng...[/green]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            while True:
                # Giới hạn tốc độ
                await self.rate_limiter.acquire()
                
                # Lấy danh sách tác phẩm
                posts_data = await self._fetch_user_posts(user_id, cursor)
                if not posts_data:
                    break
                
                aweme_list = posts_data.get('aweme_list', [])
                if not aweme_list:
                    break
                
                # Tải xuống tác phẩm
                for aweme in aweme_list:
                    if max_count > 0 and downloaded >= max_count:
                        console.print(f"[yellow]Đã đạt giới hạn số lượng tải xuống: {max_count}[/yellow]")
                        return
                    
                    # Lọc thời gian
                    if not self._check_time_filter(aweme):
                        continue
                    
                    # Tạo nhiệm vụ tải xuống
                    task_id = progress.add_task(
                        f"Tải xuống tác phẩm {downloaded + 1}", 
                        total=100
                    )
                    
                    # Đánh giá tăng dần
                    if self._should_skip_increment('post', aweme, sec_uid=user_id):
                        continue
                    
                    # Tải xuống
                    success = await self._download_media_files(aweme, progress)
                    
                    if success:
                        downloaded += 1
                        self.stats.success += 1  # Tăng số đếm thành công
                        progress.update(task_id, completed=100)
                        self._record_increment('post', aweme, sec_uid=user_id)
                    else:
                        self.stats.failed += 1  # Tăng số đếm thất bại
                        progress.update(task_id, description="[red]Tải xuống thất bại[/red]")
                
                # Kiểm tra xem còn thêm không
                if not posts_data.get('has_more'):
                    break
                
                cursor = posts_data.get('max_cursor', 0)
        
        console.print(f"[green]✅ Hoàn thành tải xuống tác phẩm người dùng, đã tải {downloaded} tác phẩm[/green]")
    
    async def _fetch_user_posts(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """Lấy danh sách tác phẩm người dùng"""
        try:
            # Sử dụng trực tiếp phương thức getUserInfo của class Douyin, giống như DouYinCommand.py
            from apiproxy.douyin.douyin import Douyin
            
            # Tạo instance Douyin
            dy = Douyin(database=False)
            
            # Lấy danh sách tác phẩm người dùng
            result = dy.getUserInfo(
                user_id, 
                "post", 
                35, 
                0,  # Không giới hạn số lượng
                False,  # Không bật tăng dần
                "",  # start_time
                ""   # end_time
            )
            
            if result:
                logger.info(f"Class Douyin đã lấy danh sách tác phẩm người dùng thành công, tổng {len(result)} tác phẩm")
                # Chuyển đổi sang định dạng mong muốn
                return {
                    'status_code': 0,
                    'aweme_list': result,
                    'max_cursor': cursor,
                    'has_more': False
                }
            else:
                logger.error("Class Douyin trả về kết quả rỗng")
                return None
                
        except Exception as e:
            logger.error(f"Lấy danh sách tác phẩm người dùng thất bại: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    async def _download_user_likes(self, user_id: str):
        """Tải xuống tác phẩm người dùng đã thích"""
        max_count = 0
        try:
            max_count = int(self.config.get('number', {}).get('like', 0))
        except Exception:
            max_count = 0
        cursor = 0
        downloaded = 0

        console.print(f"\n[green]Bắt đầu tải xuống tác phẩm người dùng đã thích...[/green]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:

            while True:
                # Giới hạn tốc độ
                await self.rate_limiter.acquire()

                # Lấy danh sách thích
                likes_data = await self._fetch_user_likes(user_id, cursor)
                if not likes_data:
                    break

                aweme_list = likes_data.get('aweme_list', [])
                if not aweme_list:
                    break

                # Tải xuống tác phẩm
                for aweme in aweme_list:
                    if max_count > 0 and downloaded >= max_count:
                        console.print(f"[yellow]Đã đạt giới hạn số lượng tải xuống: {max_count}[/yellow]")
                        return

                    if not self._check_time_filter(aweme):
                        continue

                    task_id = progress.add_task(
                        f"Tải xuống thích {downloaded + 1}",
                        total=100
                    )

                    # Đánh giá tăng dần
                    if self._should_skip_increment('like', aweme, sec_uid=user_id):
                        continue

                    success = await self._download_media_files(aweme, progress)

                    if success:
                        downloaded += 1
                        progress.update(task_id, completed=100)
                        self._record_increment('like', aweme, sec_uid=user_id)
                    else:
                        progress.update(task_id, description="[red]Tải xuống thất bại[/red]")

                # Lật trang
                if not likes_data.get('has_more'):
                    break
                cursor = likes_data.get('max_cursor', 0)

        console.print(f"[green]✅ Hoàn thành tải xuống tác phẩm thích, đã tải {downloaded} tác phẩm[/green]")

    async def _fetch_user_likes(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """Lấy danh sách tác phẩm người dùng đã thích"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'max_cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_FAVORITE_A

            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"Lấy X-Bogus thất bại: {e}, thử không có X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"Yêu cầu danh sách thích người dùng: {full_url[:100]}...")

            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Yêu cầu thất bại, mã trạng thái: {response.status}")
                        return None

                    text = await response.text()
                    if not text:
                        logger.error("Nội dung phản hồi rỗng")
                        return None

                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API trả về lỗi: {data.get('status_msg', 'Lỗi không xác định')}")
                        return None
        except Exception as e:
            logger.error(f"Lấy danh sách thích người dùng thất bại: {e}")
        return None

    async def _download_user_mixes(self, user_id: str):
        """Tải xuống tất cả bộ sưu tập người dùng (có thể giới hạn số lượng theo cấu hình)"""
        max_allmix = 0
        try:
            # Tương thích tên khóa cũ allmix hoặc mix
            number_cfg = self.config.get('number', {}) or {}
            max_allmix = int(number_cfg.get('allmix', number_cfg.get('mix', 0)) or 0)
        except Exception:
            max_allmix = 0

        cursor = 0
        fetched = 0

        console.print(f"\n[green]Bắt đầu lấy danh sách bộ sưu tập người dùng...[/green]")
        while True:
            await self.rate_limiter.acquire()
            mix_list_data = await self._fetch_user_mix_list(user_id, cursor)
            if not mix_list_data:
                break

            mix_infos = mix_list_data.get('mix_infos') or []
            if not mix_infos:
                break

            for mix in mix_infos:
                if max_allmix > 0 and fetched >= max_allmix:
                    console.print(f"[yellow]Đã đạt giới hạn số lượng bộ sưu tập: {max_allmix}[/yellow]")
                    return
                mix_id = mix.get('mix_id')
                mix_name = mix.get('mix_name', '')
                console.print(f"[cyan]Tải xuống bộ sưu tập[/cyan]: {mix_name} ({mix_id})")
                await self._download_mix_by_id(mix_id)
                fetched += 1

            if not mix_list_data.get('has_more'):
                break
            cursor = mix_list_data.get('cursor', 0)

        console.print(f"[green]✅ Hoàn thành tải xuống bộ sưu tập người dùng, đã xử lý {fetched} bộ sưu tập[/green]")

    async def _fetch_user_mix_list(self, user_id: str, cursor: int = 0) -> Optional[Dict]:
        """Lấy danh sách bộ sưu tập người dùng"""
        try:
            params_list = [
                f'sec_user_id={user_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX_LIST
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"Lấy X-Bogus thất bại: {e}, thử không có X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"Yêu cầu danh sách bộ sưu tập người dùng: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Yêu cầu thất bại, mã trạng thái: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("Nội dung phản hồi rỗng")
                        return None
                    data = json.loads(text)
                    if data.get('status_code') == 0:
                        return data
                    else:
                        logger.error(f"API trả về lỗi: {data.get('status_msg', 'Lỗi không xác định')}")
                        return None
        except Exception as e:
            logger.error(f"Lấy danh sách bộ sưu tập người dùng thất bại: {e}")
        return None

    async def download_mix(self, url: str) -> bool:
        """Dựa vào liên kết bộ sưu tập để tải xuống tất cả tác phẩm trong bộ sưu tập"""
        try:
            mix_id = None
            for pattern in [r'/collection/(\d+)', r'/mix/detail/(\d+)']:
                m = re.search(pattern, url)
                if m:
                    mix_id = m.group(1)
                    break
            if not mix_id:
                logger.error(f"Không thể trích xuất ID từ liên kết bộ sưu tập: {url}")
                return False
            await self._download_mix_by_id(mix_id)
            return True
        except Exception as e:
            logger.error(f"Tải xuống bộ sưu tập thất bại: {e}")
            return False

    async def _download_mix_by_id(self, mix_id: str):
        """Tải xuống tất cả tác phẩm theo ID bộ sưu tập"""
        cursor = 0
        downloaded = 0

        console.print(f"\n[green]Bắt đầu tải xuống bộ sưu tập {mix_id} ...[/green]")

        while True:
            await self.rate_limiter.acquire()
            data = await self._fetch_mix_awemes(mix_id, cursor)
            if not data:
                break

            aweme_list = data.get('aweme_list') or []
            if not aweme_list:
                break

            for aweme in aweme_list:
                success = await self._download_media_files(aweme)
                if success:
                    downloaded += 1

            if not data.get('has_more'):
                break
            cursor = data.get('cursor', 0)

        console.print(f"[green]✅ Hoàn thành tải xuống bộ sưu tập, đã tải {downloaded} tác phẩm[/green]")

    async def _fetch_mix_awemes(self, mix_id: str, cursor: int = 0) -> Optional[Dict]:
        """Lấy danh sách tác phẩm trong bộ sưu tập"""
        try:
            params_list = [
                f'mix_id={mix_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.USER_MIX
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"Lấy X-Bogus thất bại: {e}, thử không có X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"Yêu cầu danh sách tác phẩm bộ sưu tập: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Yêu cầu thất bại, mã trạng thái: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("Nội dung phản hồi rỗng")
                        return None
                    data = json.loads(text)
                    # USER_MIX trả về không có status_code thống nhất, ở đây trả về trực tiếp
                    return data
        except Exception as e:
            logger.error(f"Lấy tác phẩm bộ sưu tập thất bại: {e}")
        return None

    async def download_music(self, url: str) -> bool:
        """Dựa vào liên kết trang nhạc để tải xuống tất cả tác phẩm trong nhạc (hỗ trợ tăng dần)"""
        try:
            # Trích xuất music_id
            music_id = None
            m = re.search(r'/music/(\d+)', url)
            if m:
                music_id = m.group(1)
            if not music_id:
                logger.error(f"Không thể trích xuất ID từ liên kết nhạc: {url}")
                return False

            cursor = 0
            downloaded = 0
            limit_num = 0
            try:
                limit_num = int((self.config.get('number', {}) or {}).get('music', 0))
            except Exception:
                limit_num = 0

            console.print(f"\n[green]Bắt đầu tải xuống tác phẩm trong nhạc {music_id}...[/green]")

            while True:
                await self.rate_limiter.acquire()
                data = await self._fetch_music_awemes(music_id, cursor)
                if not data:
                    break
                aweme_list = data.get('aweme_list') or []
                if not aweme_list:
                    break

                for aweme in aweme_list:
                    if limit_num > 0 and downloaded >= limit_num:
                        console.print(f"[yellow]Đã đạt giới hạn số lượng tải xuống nhạc: {limit_num}[/yellow]")
                        return True
                    if self._should_skip_increment('music', aweme, music_id=music_id):
                        continue
                    success = await self._download_media_files(aweme)
                    if success:
                        downloaded += 1
                        self._record_increment('music', aweme, music_id=music_id)

                if not data.get('has_more'):
                    break
                cursor = data.get('cursor', 0)

            console.print(f"[green]✅ Hoàn thành tải xuống tác phẩm nhạc, đã tải {downloaded} tác phẩm[/green]")
            return True
        except Exception as e:
            logger.error(f"Tải xuống trang nhạc thất bại: {e}")
            return False

    async def _fetch_music_awemes(self, music_id: str, cursor: int = 0) -> Optional[Dict]:
        """Lấy danh sách tác phẩm trong nhạc"""
        try:
            params_list = [
                f'music_id={music_id}',
                f'cursor={cursor}',
                'count=35',
                'aid=6383',
                'device_platform=webapp',
                'channel=channel_pc_web',
                'pc_client_type=1',
                'version_code=170400',
                'version_name=17.4.0',
                'cookie_enabled=true',
                'screen_width=1920',
                'screen_height=1080',
                'browser_language=zh-CN',
                'browser_platform=MacIntel',
                'browser_name=Chrome',
                'browser_version=122.0.0.0',
                'browser_online=true'
            ]
            params = '&'.join(params_list)

            api_url = self.urls_helper.MUSIC
            try:
                xbogus = self.utils.getXbogus(params)
                full_url = f"{api_url}{params}&X-Bogus={xbogus}"
            except Exception as e:
                logger.warning(f"Lấy X-Bogus thất bại: {e}, thử không có X-Bogus")
                full_url = f"{api_url}{params}"

            logger.info(f"Yêu cầu danh sách tác phẩm nhạc: {full_url[:100]}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"Yêu cầu thất bại, mã trạng thái: {response.status}")
                        return None
                    text = await response.text()
                    if not text:
                        logger.error("Nội dung phản hồi rỗng")
                        return None
                    data = json.loads(text)
                    return data
        except Exception as e:
            logger.error(f"Lấy tác phẩm nhạc thất bại: {e}")
        return None
    
    def _check_time_filter(self, aweme: Dict) -> bool:
        """Kiểm tra lọc thời gian"""
        start_time = self.config.get('start_time')
        end_time = self.config.get('end_time')
        
        if not start_time and not end_time:
            return True
        
        raw_create_time = aweme.get('create_time')
        if not raw_create_time:
            return True
        
        create_date = None
        if isinstance(raw_create_time, (int, float)):
            try:
                create_date = datetime.fromtimestamp(raw_create_time)
            except Exception:
                create_date = None
        elif isinstance(raw_create_time, str):
            for fmt in ('%Y-%m-%d %H.%M.%S', '%Y-%m-%d_%H-%M-%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    create_date = datetime.strptime(raw_create_time, fmt)
                    break
                except Exception:
                    pass
        
        if create_date is None:
            return True
        
        if start_time:
            start_date = datetime.strptime(start_time, '%Y-%m-%d')
            if create_date < start_date:
                return False
        
        if end_time:
            end_date = datetime.strptime(end_time, '%Y-%m-%d')
            if create_date > end_date:
                return False
        
        return True
    
    async def run(self):
        """Chạy trình tải xuống"""
        # Hiển thị thông tin khởi động
        console.print(Panel.fit(
            "[bold cyan]Trình tải xuống Douyin v3.0 - Phiên bản nâng cao thống nhất[/bold cyan]\n"
            "[dim]Hỗ trợ tải xuống hàng loạt video, hình ảnh, trang người dùng, bộ sưu tập[/dim]",
            border_style="cyan"
        ))
        
        # Khởi tạo Cookie và request headers
        await self._initialize_cookies_and_headers()
        
        # Lấy danh sách URL
        urls = self.config.get('link', [])
        # Tương thích: chuỗi đơn
        if isinstance(urls, str):
            urls = [urls]
        if not urls:
            console.print("[red]Không tìm thấy liên kết để tải xuống![/red]")
            return
        
        # Phân tích loại URL
        console.print(f"\n[cyan]📊 Phân tích liên kết[/cyan]")
        url_types = {}
        for url in urls:
            content_type = self.detect_content_type(url)
            url_types[url] = content_type
            console.print(f"  • {content_type.upper()}: {url[:50]}...")
        
        # Bắt đầu tải xuống
        console.print(f"\n[green]⏳ Bắt đầu tải xuống {len(urls)} liên kết...[/green]\n")
        
        for i, url in enumerate(urls, 1):
            content_type = url_types[url]
            console.print(f"[{i}/{len(urls)}] Xử lý: {url}")
            
            if content_type == ContentType.VIDEO or content_type == ContentType.IMAGE:
                await self.download_single_video(url)
            elif content_type == ContentType.USER:
                await self.download_user_page(url)
                # Nếu cấu hình chứa like hoặc mix, xử lý kèm theo
                modes = self.config.get('mode', ['post'])
                if 'like' in modes:
                    user_id = self.extract_id_from_url(url, ContentType.USER)
                    if user_id:
                        await self._download_user_likes(user_id)
                if 'mix' in modes:
                    user_id = self.extract_id_from_url(url, ContentType.USER)
                    if user_id:
                        await self._download_user_mixes(user_id)
            elif content_type == ContentType.MIX:
                await self.download_mix(url)
            elif content_type == ContentType.MUSIC:
                await self.download_music(url)
            else:
                console.print(f"[yellow]Loại nội dung không được hỗ trợ: {content_type}[/yellow]")
            
            # Hiển thị tiến độ
            console.print(f"Tiến độ: {i}/{len(urls)} | Thành công: {self.stats.success} | Thất bại: {self.stats.failed}")
            console.print("-" * 60)
        
        # Hiển thị thống kê
        self._show_stats()
    
    def _show_stats(self):
        """Hiển thị thống kê tải xuống"""
        console.print("\n" + "=" * 60)
        
        # Tạo bảng thống kê
        table = Table(title="📊 Thống kê tải xuống", show_header=True, header_style="bold magenta")
        table.add_column("Mục", style="cyan", width=12)
        table.add_column("Giá trị", style="green")
        
        stats = self.stats.to_dict()
        table.add_row("Tổng số nhiệm vụ", str(stats['total']))
        table.add_row("Thành công", str(stats['success']))
        table.add_row("Thất bại", str(stats['failed']))
        table.add_row("Đã bỏ qua", str(stats['skipped']))
        table.add_row("Tỷ lệ thành công", stats['success_rate'])
        table.add_row("Thời gian", stats['elapsed_time'])
        
        console.print(table)
        console.print("\n[bold green]✅ Hoàn thành tải xuống![/bold green]")


def main():
    """Hàm chính"""
    parser = argparse.ArgumentParser(
        description='Trình tải xuống Douyin - Phiên bản nâng cao thống nhất',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-c', '--config',
        default='config.yml',
        help='Đường dẫn file cấu hình (mặc định: config.yml, tự động tương thích config_simple.yml)'
    )
    
    parser.add_argument(
        '-u', '--url',
        nargs='+',
        help='Chỉ định trực tiếp URL cần tải xuống'
    )
    parser.add_argument(
        '-p', '--path',
        default=None,
        help='Đường dẫn lưu (ghi đè cấu hình file)'
    )
    parser.add_argument(
        '--auto-cookie',
        action='store_true',
        help='Tự động lấy Cookie (cần cài đặt Playwright)'
    )
    parser.add_argument(
        '--cookie',
        help='Chỉ định thủ công chuỗi Cookie, ví dụ "msToken=xxx; ttwid=yyy"'
    )
    
    args = parser.parse_args()
    
    # Kết hợp nguồn cấu hình: ưu tiên dòng lệnh
    temp_config = {}
    if args.url:
        temp_config['link'] = args.url
    
    # Ghi đè đường dẫn lưu
    if args.path:
        temp_config['path'] = args.path
    
    # Cấu hình Cookie
    if args.auto_cookie:
        temp_config['auto_cookie'] = True
        temp_config['cookies'] = 'auto'
    if args.cookie:
        temp_config['cookies'] = args.cookie
        temp_config['auto_cookie'] = False
    
    # Nếu có cấu hình tạm thời, tạo file tạm thời để constructor hiện có sử dụng
    if temp_config:
        # Hợp nhất cấu hình file (nếu có)
        file_config = {}
        if os.path.exists(args.config):
            try:
                with open(args.config, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
            except Exception:
                file_config = {}
        
        # Tương thích tên khóa đơn giản hóa
        if 'links' in file_config and 'link' not in file_config:
            file_config['link'] = file_config['links']
        if 'output_dir' in file_config and 'path' not in file_config:
            file_config['path'] = file_config['output_dir']
        if 'cookie' in file_config and 'cookies' not in file_config:
            file_config['cookies'] = file_config['cookie']
        
        merged = {**(file_config or {}), **temp_config}
        with open('temp_config.yml', 'w', encoding='utf-8') as f:
            yaml.dump(merged, f, allow_unicode=True)
        config_path = 'temp_config.yml'
    else:
        config_path = args.config
    
    # Chạy trình tải xuống
    try:
        downloader = UnifiedDownloader(config_path)
        asyncio.run(downloader.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Người dùng đã ngắt tải xuống[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ Lỗi chương trình: {e}[/red]")
        logger.exception("Lỗi chương trình")
    finally:
        # Dọn dẹp cấu hình tạm
        if args.url and os.path.exists('temp_config.yml'):
            os.remove('temp_config.yml')


if __name__ == '__main__':
    main()