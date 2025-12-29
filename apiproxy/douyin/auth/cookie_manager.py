#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Quản lý Cookie tự động
Tự động lấy, làm mới và quản lý Cookies Douyin
"""

import asyncio
import json
import time
import logging
import pickle
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright chưa được cài đặt, quản lý Cookie tự động không khả dụng")


@dataclass
class CookieInfo:
    """Thông tin Cookie"""
    cookies: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    login_method: str = "manual"  # manual, qrcode, phone
    is_valid: bool = True
    
    def is_expired(self, max_age_hours: int = 24) -> bool:
        """Kiểm tra Cookie có hết hạn không"""
        age = time.time() - self.created_at
        return age > max_age_hours * 3600
    
    def to_dict(self) -> Dict:
        """Chuyển đổi sang định dạng dictionary"""
        return {
            'cookies': self.cookies,
            'created_at': self.created_at,
            'last_used': self.last_used,
            'login_method': self.login_method,
            'is_valid': self.is_valid
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CookieInfo':
        """Tạo từ dictionary"""
        return cls(**data)


class AutoCookieManager:
    """Quản lý Cookie tự động"""
    
    def __init__(
        self,
        cookie_file: str = "cookies.pkl",
        auto_refresh: bool = True,
        refresh_interval: int = 3600,
        headless: bool = False
    ):
        """
        Khởi tạo quản lý Cookie
        
        Args:
            cookie_file: File lưu Cookie
            auto_refresh: Có tự động làm mới không
            refresh_interval: Khoảng thời gian làm mới (giây)
            headless: Trình duyệt có chế độ không đầu không
        """
        self.cookie_file = Path(cookie_file)
        self.auto_refresh = auto_refresh
        self.refresh_interval = refresh_interval
        self.headless = headless
        
        self.current_cookies: Optional[CookieInfo] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        
        self._refresh_task = None
        self._lock = asyncio.Lock()
        
        # Tải Cookies đã lưu
        self._load_cookies()
    
    def _load_cookies(self):
        """Tải Cookies từ file"""
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'rb') as f:
                    data = pickle.load(f)
                    self.current_cookies = CookieInfo.from_dict(data)
                    logger.info(f"Đã tải Cookies đã lưu (thời gian tạo: {datetime.fromtimestamp(self.current_cookies.created_at)})")
            except Exception as e:
                logger.error(f"Tải Cookies thất bại: {e}")
                self.current_cookies = None
    
    def _save_cookies(self):
        """Lưu Cookies vào file"""
        if self.current_cookies:
            try:
                with open(self.cookie_file, 'wb') as f:
                    pickle.dump(self.current_cookies.to_dict(), f)
                logger.info("Đã lưu Cookies")
            except Exception as e:
                logger.error(f"Lưu Cookies thất bại: {e}")
    
    async def get_cookies(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lấy Cookies hợp lệ
        
        Returns:
            Danh sách Cookie
        """
        async with self._lock:
            # Kiểm tra xem có cần làm mới không
            if self._need_refresh():
                await self._refresh_cookies()
            
            if self.current_cookies and self.current_cookies.is_valid:
                self.current_cookies.last_used = time.time()
                return self.current_cookies.cookies
            
            return None
    
    def _need_refresh(self) -> bool:
        """Đánh giá xem có cần làm mới Cookies không"""
        if not self.current_cookies:
            return True
        
        # Kiểm tra xem có hết hạn không
        if self.current_cookies.is_expired(max_age_hours=24):
            logger.info("Cookies đã hết hạn, cần làm mới")
            return True
        
        # Kiểm tra xem có lâu không sử dụng không
        idle_time = time.time() - self.current_cookies.last_used
        if idle_time > self.refresh_interval:
            logger.info(f"Cookies đã không sử dụng {idle_time/3600:.1f} giờ, cần làm mới")
            return True
        
        return False
    
    async def _refresh_cookies(self):
        """Đăng nhập và lấy Cookies mới"""
        logger.info("Cần đăng nhập lại để lấy Cookies")
        
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            
            # Truy cập Douyin, nới lỏng điều kiện chờ
            try:
                await page.goto("https://www.douyin.com", wait_until='domcontentloaded', timeout=120000)
                # Chờ thêm để trang ổn định, dành thời gian cho trang xác minh tải
                await asyncio.sleep(10)
            except Exception as e:
                logger.warning(f"Trang tải quá thời gian, tiếp tục thử: {e}")
                # Ngay cả khi quá thời gian cũng tiếp tục thử
            
            # Kiểm tra xem có cần đăng nhập không
            is_logged_in = await self._check_login_status(page)
            
            if not is_logged_in:
                # Thực hiện quy trình đăng nhập
                login_method = await self._perform_login(page)
                
                if not login_method:
                    logger.error("Đăng nhập thất bại")
                    await page.close()
                    return
            else:
                login_method = "already_logged_in"
            
            # Lấy Cookies
            cookies = await page.context.cookies()
            
            # Lọc các Cookies cần thiết
            filtered_cookies = self._filter_cookies(cookies)
            
            self.current_cookies = CookieInfo(
                cookies=filtered_cookies,
                login_method=login_method
            )
            
            self._save_cookies()
            logger.info(f"Lấy Cookies thành công (phương thức đăng nhập: {login_method})")
            
            await page.close()
            
        except Exception as e:
            logger.error(f"Đăng nhập lấy Cookies thất bại: {e}")
    
    async def _try_refresh_existing(self) -> bool:
        """Thử làm mới Cookies hiện có"""
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            
            # Thiết lập Cookies hiện có
            await page.context.add_cookies(self.current_cookies.cookies)
            
            # Truy cập trang chủ Douyin
            await page.goto("https://www.douyin.com", wait_until='networkidle')
            
            # Kiểm tra xem vẫn còn đăng nhập không
            is_logged_in = await self._check_login_status(page)
            
            if is_logged_in:
                # Lấy Cookies đã cập nhật
                cookies = await page.context.cookies()
                self.current_cookies = CookieInfo(
                    cookies=cookies,
                    login_method="refresh"
                )
                self._save_cookies()
                logger.info("Làm mới Cookies thành công")
                await page.close()
                return True
            
            await page.close()
            return False
            
        except Exception as e:
            logger.error(f"Làm mới Cookies thất bại: {e}")
            return False
    
    async def _login_and_get_cookies(self):
        """Đăng nhập và lấy Cookies mới"""
        logger.info("Cần đăng nhập lại để lấy Cookies")
        
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            
            # Truy cập Douyin
            await page.goto("https://www.douyin.com", wait_until='networkidle')
            
            # Kiểm tra xem có cần đăng nhập không
            is_logged_in = await self._check_login_status(page)
            
            if not is_logged_in:
                # Thực hiện quy trình đăng nhập
                login_method = await self._perform_login(page)
                
                if not login_method:
                    logger.error("Đăng nhập thất bại")
                    await page.close()
                    return
            else:
                login_method = "already_logged_in"
            
            # Lấy Cookies
            cookies = await page.context.cookies()
            
            # Lọc các Cookies cần thiết
            filtered_cookies = self._filter_cookies(cookies)
            
            self.current_cookies = CookieInfo(
                cookies=filtered_cookies,
                login_method=login_method
            )
            
            self._save_cookies()
            logger.info(f"Đã lấy Cookies thành công (Phương thức đăng nhập: {login_method})")
            
            await page.close()
            
        except Exception as e:
            logger.error(f"Lấy Cookies đăng nhập thất bại: {e}")
    
    async def _check_login_status(self, page: 'Page') -> bool:
        """Kiểm tra trạng thái đăng nhập"""
        try:
            # Tìm avatar người dùng hoặc các dấu hiệu đăng nhập khác
            selectors = [
                '[data-e2e="user-avatar"]',
                '.user-avatar',
                '[class*="avatar"]',
                '.login-success',
                '[class*="user"]',
                '[class*="profile"]',
                'img[alt*="头像"]',
                'img[alt*="avatar"]',
                '[data-e2e="profile"]',
                '.profile-info'
            ]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        logger.info("Phát hiện đã đăng nhập")
                        return True
                except:
                    continue
            
            # Kiểm tra bổ sung: tìm nút đăng nhập, nếu không tìm thấy có thể đã đăng nhập
            try:
                login_indicators = [
                    '[data-e2e="login-button"]',
                    '.login-button',
                    'button:has-text("登录")',
                    'a:has-text("登录")'
                ]
                
                for indicator in login_indicators:
                    try:
                        element = await page.wait_for_selector(indicator, timeout=2000)
                        if element:
                            logger.info("Phát hiện nút đăng nhập, chưa đăng nhập")
                            return False
                    except:
                        continue
                
                # Nếu không tìm thấy nút đăng nhập, có thể đã đăng nhập
                logger.info("Không tìm thấy nút đăng nhập, có thể đã đăng nhập")
                return True
                
            except Exception:
                pass
            
            return False
            
        except Exception as e:
            logger.warning(f"Kiểm tra trạng thái đăng nhập thất bại: {e}")
            return False
    
    async def _perform_login(self, page: 'Page') -> Optional[str]:
        """Thực hiện quy trình đăng nhập"""
        logger.info("Bắt đầu quy trình đăng nhập...")
        
        # Trước tiên thử đăng nhập bằng mã QR
        login_method = await self._qrcode_login(page)
        
        if not login_method:
            # Nếu đăng nhập bằng mã QR thất bại, thử cách khác
            login_method = await self._manual_login(page)
        
        return login_method
    
    async def _qrcode_login(self, page: Page) -> Optional[str]:
        """Đăng nhập bằng mã QR"""
        try:
            logger.info("Thử đăng nhập bằng mã QR...")
            
            # Tìm và nhấp nút đăng nhập
            login_button_selectors = [
                '[data-e2e="login-button"]',
                '.login-button',
                'button:has-text("登录")',
                'a:has-text("登录")',
                '[class*="login"]',
                'button:has-text("登入")',
                'a:has-text("登入")'
            ]
            
            for selector in login_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=15000)
                    if button:
                        await button.click()
                        break
                except:
                    continue
            
            # Chờ cửa sổ đăng nhập
            await asyncio.sleep(8)
            
            # Chọn đăng nhập bằng mã QR
            qr_selectors = [
                '[data-e2e="qrcode-tab"]',
                '.qrcode-login',
                'text=扫码登录',
                'text=二维码登录',
                '[class*="qrcode"]',
                'text=二维码',
                'text=扫码'
            ]
            
            for selector in qr_selectors:
                try:
                    qr_tab = await page.wait_for_selector(selector, timeout=15000)
                    if qr_tab:
                        await qr_tab.click()
                        break
                except:
                    continue
            
            # Chờ mã QR xuất hiện
            qr_img_selectors = [
                '.qrcode-img', 
                '[class*="qrcode"] img', 
                'canvas',
                '[class*="qr"] img',
                'img[alt*="二维码"]',
                'img[alt*="QR"]'
            ]
            
            qr_found = False
            for selector in qr_img_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=20000)
                    qr_found = True
                    break
                except:
                    continue
            
            if not qr_found:
                logger.warning("Không tìm thấy mã QR, tiếp tục chờ...")
                # Ngay cả khi không tìm thấy mã QR cũng tiếp tục chờ, có thể trang vẫn đang tải
            
            if not self.headless:
                print("\n" + "="*60)
                print("Vui lòng sử dụng ứng dụng Douyin để quét mã QR đăng nhập")
                print("Nếu xuất hiện mã xác minh, vui lòng hoàn thành xác minh")
                print("Đang chờ đăng nhập...")
                print("="*60 + "\n")
            
            # Chờ người dùng quét mã (tối đa 300 giây, dành thời gian cho xác minh mã)
            start_time = time.time()
            while time.time() - start_time < 300:
                is_logged_in = await self._check_login_status(page)
                if is_logged_in:
                    logger.info("Đăng nhập bằng mã QR thành công")
                    return "qrcode"
                await asyncio.sleep(8)
            
            logger.warning("Đăng nhập bằng mã QR quá thời gian")
            return None
            
        except Exception as e:
            logger.error(f"Đăng nhập bằng mã QR thất bại: {e}")
            return None
    
    async def _manual_login(self, page: Page) -> Optional[str]:
        """Đăng nhập thủ công (chờ người dùng thao tác)"""
        if self.headless:
            logger.error("Không thể đăng nhập thủ công ở chế độ không đầu")
            return None
        
        print("\n" + "="*60)
        print("Vui lòng hoàn thành đăng nhập trong trình duyệt")
        print("Nếu xuất hiện mã xác minh, vui lòng hoàn thành xác minh")
        print("Sau khi đăng nhập thành công sẽ tự động tiếp tục...")
        print("="*60 + "\n")
        
        # Chờ người dùng đăng nhập thủ công (tối đa 600 giây, dành thời gian dư cho xác minh mã)
        start_time = time.time()
        while time.time() - start_time < 600:
            is_logged_in = await self._check_login_status(page)
            if is_logged_in:
                logger.info("Đăng nhập thủ công thành công")
                return "manual"
            await asyncio.sleep(8)
        
        logger.warning("Đăng nhập thủ công quá thời gian")
        return None
    
    def _filter_cookies(self, cookies: List[Dict]) -> List[Dict]:
        """Lọc các Cookies cần thiết"""
        # Tên Cookie cần thiết
        required_names = [
            'msToken',
            'ttwid', 
            'odin_tt',
            'passport_csrf_token',
            'sid_guard',
            'uid_tt',
            'sessionid',
            'sid_tt'
        ]
        
        filtered = []
        for cookie in cookies:
            # Giữ lại Cookie cần thiết hoặc tất cả Cookie trong domain Douyin
            if cookie['name'] in required_names or '.douyin.com' in cookie.get('domain', ''):
                filtered.append(cookie)
        
        logger.info(f"Sau khi lọc giữ lại {len(filtered)} Cookies")
        return filtered
    
    async def _get_browser(self) -> Browser:
        """Lấy instance trình duyệt"""
        if not self.browser:
            if not PLAYWRIGHT_AVAILABLE:
                raise ImportError("Playwright chưa được cài đặt")
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN'
            )
        
        return self.context
    
    async def start_auto_refresh(self):
        """Khởi động nhiệm vụ làm mới tự động"""
        if self.auto_refresh and not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._auto_refresh_loop())
            logger.info("Làm mới Cookie tự động đã khởi động")
    
    async def stop_auto_refresh(self):
        """Dừng nhiệm vụ làm mới tự động"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
            logger.info("Làm mới Cookie tự động đã dừng")
    
    async def _auto_refresh_loop(self):
        """Vòng lặp làm mới tự động"""
        while True:
            try:
                await asyncio.sleep(self.refresh_interval)
                
                if self._need_refresh():
                    logger.info("Kích hoạt làm mới Cookie tự động")
                    await self._refresh_cookies()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lỗi làm mới tự động: {e}")
                await asyncio.sleep(60)  # Sau khi lỗi chờ 1 phút rồi thử lại
    
    async def cleanup(self):
        """Dọn dẹp tài nguyên"""
        await self.stop_auto_refresh()
        
        if self.context:
            await self.context.close()
            self.context = None
        
        if self.browser:
            await self.browser.close()
            self.browser = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        logger.info("Đã dọn dẹp tài nguyên quản lý Cookie")
    
    def get_cookie_dict(self) -> Optional[Dict[str, str]]:
        """Lấy Cookie ở định dạng dictionary"""
        if not self.current_cookies:
            return None
        
        cookie_dict = {}
        for cookie in self.current_cookies.cookies:
            cookie_dict[cookie['name']] = cookie['value']
        
        return cookie_dict
    
    def get_cookie_string(self) -> Optional[str]:
        """Lấy Cookie ở định dạng chuỗi"""
        cookie_dict = self.get_cookie_dict()
        if not cookie_dict:
            return None
        
        return '; '.join([f'{k}={v}' for k, v in cookie_dict.items()])
    
    async def __aenter__(self):
        """Điểm vào quản lý context bất đồng bộ"""
        await self.start_auto_refresh()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Điểm ra quản lý context bất đồng bộ"""
        await self.cleanup()