#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import json
import time
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
from typing import List, Optional
from pathlib import Path
# import asyncio  # Tạm thời comment
# import aiohttp  # Tạm thời comment
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from apiproxy.douyin import douyin_headers
from apiproxy.common import utils

logger = logging.getLogger("douyin_downloader")
console = Console()

class Download(object):
    def __init__(self, thread=5, music=True, cover=True, avatar=True, resjson=True, folderstyle=True):
        self.thread = thread
        self.music = music
        self.cover = cover
        self.avatar = avatar
        self.resjson = resjson
        self.folderstyle = folderstyle
        self.console = Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            transient=True  # Thêm tham số này, thanh tiến độ sẽ tự động biến mất sau khi hoàn thành
        )
        self.retry_times = 3
        self.chunk_size = 8192
        self.timeout = 30

    def _download_media(self, url: str, path: Path, desc: str) -> bool:
        """Phương thức tải xuống chung, xử lý tất cả các loại tải xuống media"""
        if path.exists():
            self.console.print(f"[cyan]⏭️  Bỏ qua đã tồn tại: {desc}[/]")
            return True
            
        # Sử dụng phương thức tải xuống tiếp tục điểm dừng mới thay thế logic tải xuống cũ
        return self.download_with_resume(url, path, desc)

    def _get_first_url(self, url_list: list) -> str:
        """Lấy URL đầu tiên từ danh sách URL một cách an toàn"""
        if isinstance(url_list, list) and len(url_list) > 0:
            return url_list[0]
        return None

    def _download_media_files(self, aweme: dict, path: Path, name: str, desc: str) -> None:
        """Tải xuống tất cả file media"""
        try:
            # Tải xuống video hoặc bộ ảnh
            if aweme["awemeType"] == 0:  # Video
                video_path = path / f"{name}_video.mp4"
                url_list = aweme.get("video", {}).get("play_addr", {}).get("url_list", [])
                if url := self._get_first_url(url_list):
                    if not self._download_media(url, video_path, f"[Video]{desc}"):
                        raise Exception("Tải xuống video thất bại")
                else:
                    logger.warning(f"URL video rỗng: {desc}")

            elif aweme["awemeType"] == 1:  # Bộ ảnh
                for i, image in enumerate(aweme.get("images", [])):
                    url_list = image.get("url_list", [])
                    if url := self._get_first_url(url_list):
                        image_path = path / f"{name}_image_{i}.jpeg"
                        if not self._download_media(url, image_path, f"[Bộ ảnh{i+1}]{desc}"):
                            raise Exception(f"Tải xuống ảnh {i+1} thất bại")
                    else:
                        logger.warning(f"URL ảnh {i+1} rỗng: {desc}")

            # Tải xuống nhạc
            if self.music:
                url_list = aweme.get("music", {}).get("play_url", {}).get("url_list", [])
                if url := self._get_first_url(url_list):
                    music_name = utils.replaceStr(aweme["music"]["title"])
                    music_path = path / f"{name}_music_{music_name}.mp3"
                    if not self._download_media(url, music_path, f"[Nhạc]{desc}"):
                        self.console.print(f"[yellow]⚠️  Tải xuống nhạc thất bại: {desc}[/]")

            # Tải xuống ảnh bìa
            if self.cover and aweme["awemeType"] == 0:
                url_list = aweme.get("video", {}).get("cover", {}).get("url_list", [])
                if url := self._get_first_url(url_list):
                    cover_path = path / f"{name}_cover.jpeg"
                    if not self._download_media(url, cover_path, f"[Ảnh bìa]{desc}"):
                        self.console.print(f"[yellow]⚠️  Tải xuống ảnh bìa thất bại: {desc}[/]")

            # Tải xuống avatar
            if self.avatar:
                url_list = aweme.get("author", {}).get("avatar", {}).get("url_list", [])
                if url := self._get_first_url(url_list):
                    avatar_path = path / f"{name}_avatar.jpeg"
                    if not self._download_media(url, avatar_path, f"[Avatar]{desc}"):
                        self.console.print(f"[yellow]⚠️  Tải xuống avatar thất bại: {desc}[/]")

        except Exception as e:
            raise Exception(f"Tải xuống thất bại: {str(e)}")

    def awemeDownload(self, awemeDict: dict, savePath: Path) -> None:
        """Tải xuống tất cả nội dung của một tác phẩm"""
        if not awemeDict:
            logger.warning("Dữ liệu tác phẩm không hợp lệ")
            return
            
        try:
            # Tạo thư mục lưu
            save_path = Path(savePath)
            save_path.mkdir(parents=True, exist_ok=True)
            
            # Xây dựng tên file
            file_name = f"{awemeDict['create_time']}_{utils.replaceStr(awemeDict['desc'])}"
            aweme_path = save_path / file_name if self.folderstyle else save_path
            aweme_path.mkdir(exist_ok=True)
            
            # Lưu dữ liệu JSON
            if self.resjson:
                self._save_json(aweme_path / f"{file_name}_result.json", awemeDict)
                
            # Tải xuống file media
            desc = file_name[:30]
            self._download_media_files(awemeDict, aweme_path, file_name, desc)
                
        except Exception as e:
            logger.error(f"Lỗi khi xử lý tác phẩm: {str(e)}")

    def _save_json(self, path: Path, data: dict) -> None:
        """Lưu dữ liệu JSON"""
        try:
            with open(path, "w", encoding='utf-8') as f:
                json.dump(data, ensure_ascii=False, indent=2, fp=f)
        except Exception as e:
            logger.error(f"Lưu JSON thất bại: {path}, lỗi: {str(e)}")

    def userDownload(self, awemeList: List[dict], savePath: Path):
        if not awemeList:
            self.console.print("[yellow]⚠️  Không tìm thấy nội dung để tải xuống[/]")
            return

        save_path = Path(savePath)
        save_path.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        total_count = len(awemeList)
        success_count = 0
        
        # Hiển thị panel thông tin tải xuống
        self.console.print(Panel(
            Text.assemble(
                ("Cấu hình tải xuống\n", "bold cyan"),
                (f"Tổng số: {total_count} tác phẩm\n", "cyan"),
                (f"Luồng: {self.thread}\n", "cyan"),
                (f"Đường dẫn lưu: {save_path}\n", "cyan"),
            ),
            title="Trình tải xuống Douyin",
            border_style="cyan"
        ))

        with self.progress:
            download_task = self.progress.add_task(
                "[cyan]📥 Tiến độ tải xuống hàng loạt", 
                total=total_count
            )
            
            for aweme in awemeList:
                try:
                    self.awemeDownload(awemeDict=aweme, savePath=save_path)
                    success_count += 1
                    self.progress.update(download_task, advance=1)
                except Exception as e:
                    self.console.print(f"[red]❌ Tải xuống thất bại: {str(e)}[/]")

        # Hiển thị thống kê hoàn thành tải xuống
        end_time = time.time()
        duration = end_time - start_time
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        
        self.console.print(Panel(
            Text.assemble(
                ("Tải xuống hoàn thành\n", "bold green"),
                (f"Thành công: {success_count}/{total_count}\n", "green"),
                (f"Thời gian: {minutes} phút {seconds} giây\n", "green"),
                (f"Vị trí lưu: {save_path}\n", "green"),
            ),
            title="Thống kê tải xuống",
            border_style="green"
        ))

    def download_with_resume(self, url: str, filepath: Path, desc: str) -> bool:
        """Phương thức tải xuống hỗ trợ tiếp tục điểm dừng"""
        file_size = filepath.stat().st_size if filepath.exists() else 0
        headers = {'Range': f'bytes={file_size}-'} if file_size > 0 else {}

        for attempt in range(self.retry_times):
            try:
                response = requests.get(url, headers={**douyin_headers, **headers},
                                     stream=True, timeout=self.timeout)

                if response.status_code not in (200, 206):
                    raise Exception(f"HTTP {response.status_code}")

                total_size = int(response.headers.get('content-length', 0)) + file_size
                mode = 'ab' if file_size > 0 else 'wb'

                with self.progress:
                    task = self.progress.add_task(f"[cyan]⬇️  {desc}", total=total_size)
                    self.progress.update(task, completed=file_size)  # Cập nhật tiến độ tiếp tục điểm dừng

                    with open(filepath, mode) as f:
                        try:
                            for chunk in response.iter_content(chunk_size=self.chunk_size):
                                if chunk:
                                    size = f.write(chunk)
                                    self.progress.update(task, advance=size)
                        except (requests.exceptions.ConnectionError,
                               requests.exceptions.ChunkedEncodingError,
                               Exception) as chunk_error:
                            # Mạng bị ngắt, ghi lại kích thước file hiện tại, lần sau tiếp tục từ đây
                            current_size = filepath.stat().st_size if filepath.exists() else 0
                            logger.warning(f"Tải xuống bị ngắt, đã tải {current_size} byte: {str(chunk_error)}")
                            raise chunk_error

                return True

            except Exception as e:
                # Tính toán thời gian chờ thử lại (exponential backoff)
                wait_time = min(2 ** attempt, 10)  # Tối đa chờ 10 giây
                logger.warning(f"Tải xuống thất bại (thử {attempt + 1}/{self.retry_times}): {str(e)}")

                if attempt == self.retry_times - 1:
                    self.console.print(f"[red]❌ Tải xuống thất bại: {desc}\n   {str(e)}[/]")
                    return False
                else:
                    logger.info(f"Chờ {wait_time} giây rồi thử lại...")
                    time.sleep(wait_time)
                    # Tính lại kích thước file, chuẩn bị tiếp tục điểm dừng
                    file_size = filepath.stat().st_size if filepath.exists() else 0
                    headers = {'Range': f'bytes={file_size}-'} if file_size > 0 else {}

        return False


class DownloadManager:
    def __init__(self, max_workers=3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def download_with_resume(self, url, filepath, callback=None):
        # Kiểm tra xem có file đã tải xuống một phần không
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        
        headers = {'Range': f'bytes={file_size}-'}
        
        response = requests.get(url, headers=headers, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        mode = 'ab' if file_size > 0 else 'wb'
        
        with open(filepath, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    if callback:
                        callback(len(chunk))


if __name__ == "__main__":
    pass
