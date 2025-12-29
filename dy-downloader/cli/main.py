import asyncio
import argparse
import json
import sys
from pathlib import Path

from config import ConfigLoader
from auth import CookieManager
from storage import Database, FileManager
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, URLParser, DownloaderFactory
from cli.progress_display import ProgressDisplay
from utils.logger import setup_logger

logger = setup_logger('CLI')
display = ProgressDisplay()


async def download_url(url: str, config: ConfigLoader, cookie_manager: CookieManager, database: Database = None):
    file_manager = FileManager(config.get('path'))
    rate_limiter = RateLimiter(max_per_second=2)
    retry_handler = RetryHandler(max_retries=config.get('retry_times', 3))
    queue_manager = QueueManager(max_workers=int(config.get('thread', 5) or 5))

    original_url = url

    async with DouyinAPIClient(cookie_manager.get_cookies()) as api_client:
        if url.startswith('https://v.douyin.com'):
            resolved_url = await api_client.resolve_short_url(url)
            if resolved_url:
                url = resolved_url
            else:
                display.print_error(f"Không thể phân giải URL rút gọn: {url}")
                return None

        parsed = URLParser.parse(url)
        if not parsed:
            display.print_error(f"Không thể phân tích URL: {url}")
            return None

        display.print_info(f"Loại URL: {parsed['type']}")

        downloader = DownloaderFactory.create(
            parsed['type'],
            config,
            api_client,
            file_manager,
            cookie_manager,
            database,
            rate_limiter,
            retry_handler,
            queue_manager
        )

        if not downloader:
            display.print_error(f"Không tìm thấy trình tải xuống cho loại: {parsed['type']}")
            return None

        result = await downloader.download(parsed)

        if result and database:
            await database.add_history({
                'url': original_url,
                'url_type': parsed['type'],
                'total_count': result.total,
                'success_count': result.success,
                'config': json.dumps(config.config, ensure_ascii=False),
            })

        return result


async def main_async(args):
    display.show_banner()

    if args.config:
        config_path = args.config
    else:
        config_path = 'config.yml'

    if not Path(config_path).exists():
        display.print_error(f"Không tìm thấy file cấu hình: {config_path}")
        return

    config = ConfigLoader(config_path)

    if args.url:
        urls = args.url if isinstance(args.url, list) else [args.url]
        for url in urls:
            if url not in config.get('link', []):
                config.update(link=config.get('link', []) + [url])

    if args.path:
        config.update(path=args.path)

    if args.thread:
        config.update(thread=args.thread)

    if not config.validate():
        display.print_error("Cấu hình không hợp lệ: thiếu các trường bắt buộc")
        return

    cookies = config.get_cookies()
    cookie_manager = CookieManager()
    cookie_manager.set_cookies(cookies)

    if not cookie_manager.validate_cookies():
        display.print_warning("Cookies có thể không hợp lệ hoặc không đầy đủ")

    database = None
    if config.get('database'):
        database = Database()
        await database.initialize()
        display.print_success("Cơ sở dữ liệu đã khởi tạo")

    urls = config.get_links()
    display.print_info(f"Tìm thấy {len(urls)} URL để xử lý")

    all_results = []

    for i, url in enumerate(urls, 1):
        display.print_info(f"Đang xử lý [{i}/{len(urls)}]: {url}")

        result = await download_url(url, config, cookie_manager, database)
        if result:
            all_results.append(result)
            display.show_result(result)

    if all_results:
        from core.downloader_base import DownloadResult
        total_result = DownloadResult()
        for r in all_results:
            total_result.total += r.total
            total_result.success += r.success
            total_result.failed += r.failed
            total_result.skipped += r.skipped

        display.print_success("\n=== Tóm tắt tổng thể ===")
        display.show_result(total_result)


def main():
    parser = argparse.ArgumentParser(description='Douyin Downloader - Công cụ tải xuống hàng loạt Douyin')
    parser.add_argument('-u', '--url', action='append', help='URL tải xuống')
    parser.add_argument('-c', '--config', help='Đường dẫn file cấu hình (mặc định: config.yml)')
    parser.add_argument('-p', '--path', help='Đường dẫn lưu')
    parser.add_argument('-t', '--thread', type=int, help='Số luồng')
    parser.add_argument('--version', action='version', version='1.0.0')

    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        display.print_warning("\nNgười dùng đã hủy tải xuống")
        sys.exit(0)
    except Exception as e:
        display.print_error(f"Lỗi nghiêm trọng: {e}")
        logger.exception("Đã xảy ra lỗi nghiêm trọng")
        sys.exit(1)


if __name__ == '__main__':
    main()
