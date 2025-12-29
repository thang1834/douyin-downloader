#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Trình trích xuất Cookie Douyin tự động
Sử dụng Playwright để đăng nhập tự động và trích xuất Cookie
"""

import asyncio
import json
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Optional
import time

try:
    from playwright.async_api import async_playwright, Browser, Page
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich import print as rprint
except ImportError:
    print("Vui lòng cài đặt các thư viện cần thiết: pip install playwright rich pyyaml")
    print("Và chạy: playwright install chromium")
    sys.exit(1)

console = Console()


class CookieExtractor:
    """Trình trích xuất Cookie"""
    
    def __init__(self, config_path: str = "config_simple.yml"):
        self.config_path = config_path
        self.cookies = {}
        
    async def extract_cookies(self, headless: bool = False) -> Dict:
        """Trích xuất Cookie
        
        Args:
            headless: Có chạy ở chế độ không đầu không
        """
        console.print(Panel.fit(
            "[bold cyan]Trình trích xuất Cookie Douyin tự động[/bold cyan]\n"
            "[dim]Sẽ tự động mở trình duyệt, vui lòng hoàn thành đăng nhập trong trình duyệt[/dim]",
            border_style="cyan"
        ))
        
        async with async_playwright() as p:
            # Khởi động trình duyệt
            browser = await p.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            # Tạo context (mô phỏng trình duyệt thật)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Thêm script khởi tạo (ẩn đặc điểm tự động hóa)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Tạo trang
            page = await context.new_page()
            
            try:
                # Truy cập trang đăng nhập Douyin
                console.print("\n[cyan]Đang mở trang đăng nhập Douyin...[/cyan]")
                await page.goto('https://www.douyin.com', wait_until='networkidle')
                
                # Chờ người dùng đăng nhập
                console.print("\n[yellow]Vui lòng hoàn thành thao tác đăng nhập trong trình duyệt[/yellow]")
                console.print("[dim]Phương thức đăng nhập：[/dim]")
                console.print("  1. Đăng nhập bằng mã QR (khuyên dùng)")
                console.print("  2. Đăng nhập bằng số điện thoại")
                console.print("  3. Đăng nhập bằng tài khoản bên thứ ba")
                
                # Chờ dấu hiệu đăng nhập thành công
                logged_in = await self._wait_for_login(page)
                
                if logged_in:
                    console.print("\n[green]✅ Đăng nhập thành công! Đang trích xuất Cookie...[/green]")
                    
                    # Trích xuất Cookie
                    cookies = await context.cookies()
                    
                    # Chuyển đổi sang định dạng dictionary
                    cookie_dict = {}
                    cookie_string = ""
                    
                    for cookie in cookies:
                        cookie_dict[cookie['name']] = cookie['value']
                        cookie_string += f"{cookie['name']}={cookie['value']}; "
                    
                    self.cookies = cookie_dict
                    
                    # Hiển thị Cookie quan trọng
                    console.print("\n[cyan]Các Cookie quan trọng đã trích xuất:[/cyan]")
                    important_cookies = ['sessionid', 'sessionid_ss', 'ttwid', 'passport_csrf_token', 'msToken']
                    for name in important_cookies:
                        if name in cookie_dict:
                            value = cookie_dict[name]
                            console.print(f"  • {name}: {value[:20]}..." if len(value) > 20 else f"  • {name}: {value}")
                    
                    # Lưu Cookie
                    if Confirm.ask("\nCó muốn lưu Cookie vào file cấu hình không？"):
                        self._save_cookies(cookie_dict)
                        console.print("[green]✅ Cookie đã lưu vào file cấu hình[/green]")
                    
                    # Lưu chuỗi Cookie đầy đủ vào file
                    with open('cookies.txt', 'w', encoding='utf-8') as f:
                        f.write(cookie_string.strip())
                    console.print("[green]✅ Cookie đầy đủ đã lưu vào cookies.txt[/green]")
                    
                    return cookie_dict
                else:
                    console.print("\n[red]❌ Đăng nhập quá thời gian hoặc thất bại[/red]")
                    return {}
                    
            except Exception as e:
                console.print(f"\n[red]❌ Trích xuất Cookie thất bại: {e}[/red]")
                return {}
            finally:
                await browser.close()
    
    async def _wait_for_login(self, page: Page, timeout: int = 300) -> bool:
        """Chờ người dùng đăng nhập
        
        Args:
            page: Đối tượng trang
            timeout: Thời gian chờ (giây)
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Kiểm tra xem đã đăng nhập chưa (nhiều cách kiểm tra)
            try:
                # Cách 1: Kiểm tra xem có avatar người dùng không
                avatar = await page.query_selector('div[class*="avatar"]')
                if avatar:
                    await asyncio.sleep(2)  # Chờ Cookie tải hoàn toàn
                    return True
                
                # Cách 2: Kiểm tra URL có chứa ID người dùng không
                current_url = page.url
                if '/user/' in current_url:
                    await asyncio.sleep(2)
                    return True
                
                # Cách 3: Kiểm tra xem có phần tử sau đăng nhập cụ thể không
                user_menu = await page.query_selector('[class*="user-info"]')
                if user_menu:
                    await asyncio.sleep(2)
                    return True
                
            except:
                pass
            
            await asyncio.sleep(2)
            
            # Hiển thị tiến độ chờ
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            console.print(f"\r[dim]Đang chờ đăng nhập... ({remaining} giây còn lại)[/dim]", end="")
        
        return False
    
    def _save_cookies(self, cookies: Dict):
        """Lưu Cookie vào file cấu hình"""
        # Đọc cấu hình hiện có
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Cập nhật cấu hình Cookie
        config['cookies'] = cookies
        
        # Lưu cấu hình
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    async def quick_extract(self) -> Dict:
        """Trích xuất nhanh (sử dụng phiên trình duyệt đã đăng nhập)"""
        console.print("\n[cyan]Thử trích xuất Cookie từ trình duyệt đã mở...[/cyan]")
        console.print("[dim]Vui lòng đảm bảo bạn đã đăng nhập Douyin trong trình duyệt[/dim]")
        
        # Ở đây có thể sử dụng CDP để kết nối với trình duyệt đã mở
        # Cần trình duyệt khởi động ở chế độ debug
        console.print("\n[yellow]Vui lòng thực hiện các bước sau：[/yellow]")
        console.print("1. Đóng tất cả Chrome")
        console.print("2. Khởi động Chrome ở chế độ gỡ lỗi:")
        console.print("   Windows: chrome.exe --remote-debugging-port=9222")
        console.print("   Mac: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
        console.print("3. Đăng nhập Douyin trong trình duyệt đã mở")
        console.print("4. Nhấn Enter để tiếp tục...")
        
        input()
        
        try:
            async with async_playwright() as p:
                # Kết nối với trình duyệt đã mở
                browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                contexts = browser.contexts
                
                if contexts:
                    context = contexts[0]
                    pages = context.pages
                    
                    # Tìm trang Douyin
                    douyin_page = None
                    for page in pages:
                        if 'douyin.com' in page.url:
                            douyin_page = page
                            break
                    
                    if douyin_page:
                        # Trích xuất Cookie
                        cookies = await context.cookies()
                        cookie_dict = {}
                        
                        for cookie in cookies:
                            if 'douyin.com' in cookie.get('domain', ''):
                                cookie_dict[cookie['name']] = cookie['value']
                        
                        if cookie_dict:
                            console.print("[green]✅ Trích xuất Cookie thành công！[/green]")
                            self._save_cookies(cookie_dict)
                            return cookie_dict
                        else:
                            console.print("[red]Không tìm thấy Cookie Douyin[/red]")
                    else:
                        console.print("[red]Không tìm thấy trang Douyin, vui lòng truy cập douyin.com trước[/red]")
                else:
                    console.print("[red]Không tìm thấy ngữ cảnh trình duyệt[/red]")
                    
        except Exception as e:
            console.print(f"[red]Kết nối trình duyệt thất bại: {e}[/red]")
            console.print("[yellow]Vui lòng đảm bảo trình duyệt đã khởi động ở chế độ gỡ lỗi[/yellow]")
        
        return {}


async def main():
    """Hàm chính"""
    extractor = CookieExtractor()
    
    console.print("\n[cyan]Vui lòng chọn phương thức trích xuất：[/cyan]")
    console.print("1. Tự động đăng nhập và trích xuất (khuyên dùng)")
    console.print("2. Trích xuất từ trình duyệt đã đăng nhập")
    console.print("3. Nhập Cookie thủ công")
    
    choice = Prompt.ask("Vui lòng chọn", choices=["1", "2", "3"], default="1")
    
    if choice == "1":
        # Tự động đăng nhập và trích xuất
        headless = not Confirm.ask("Có hiển thị giao diện trình duyệt không？", default=True)
        cookies = await extractor.extract_cookies(headless=headless)
        
    elif choice == "2":
        # Trích xuất từ trình duyệt đã đăng nhập
        cookies = await extractor.quick_extract()
        
    else:
        # Nhập thủ công
        console.print("\n[cyan]Vui lòng nhập chuỗi Cookie：[/cyan]")
        console.print("[dim]Định dạng: name1=value1; name2=value2; ...[/dim]")
        cookie_string = Prompt.ask("Cookie")
        
        cookies = {}
        for item in cookie_string.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                cookies[key] = value
        
        if cookies:
            extractor._save_cookies(cookies)
            console.print("[green]✅ Cookie đã lưu[/green]")
    
    if cookies:
        console.print("\n[green]✅ Trích xuất Cookie hoàn tất！[/green]")
        console.print("[dim]Bạn có thể chạy trình tải xuống ngay bây giờ：[/dim]")
        console.print("python3 downloader.py -c config_simple.yml")
    else:
        console.print("\n[red]❌ Không thể trích xuất Cookie[/red]")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Người dùng đã hủy thao tác[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Lỗi chương trình: {e}[/red]")