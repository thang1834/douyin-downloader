#!/usr/bin/env python
# -*- coding: utf-8 -*-


import argparse
import os
import sys
import json
import yaml
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import logging

# Cấu hình logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
# Đổi tên thành douyin_logger để tránh xung đột
douyin_logger = logging.getLogger("DouYin")

# Có thể dùng douyin_logger an toàn
try:
    import asyncio
    import aiohttp
    ASYNC_SUPPORT = True
except ImportError:
    ASYNC_SUPPORT = False
    douyin_logger.warning("Chưa cài aiohttp, không thể dùng tải bất đồng bộ")

from apiproxy.douyin.douyin import Douyin
from apiproxy.douyin.download import Download
from apiproxy.douyin import douyin_headers
from apiproxy.common import utils

@dataclass
class DownloadConfig:
    """Lớp cấu hình tải xuống"""
    link: List[str]
    path: Path
    music: bool = True
    cover: bool = True
    avatar: bool = True
    json: bool = True
    start_time: str = ""
    end_time: str = ""
    folderstyle: bool = True
    mode: List[str] = field(default_factory=lambda: ["post"])
    thread: int = 5
    cookie: Optional[str] = None
    database: bool = True
    number: Dict[str, int] = field(default_factory=lambda: {
        "post": 0, "like": 0, "allmix": 0, "mix": 0, "music": 0
    })
    increase: Dict[str, bool] = field(default_factory=lambda: {
        "post": False, "like": False, "allmix": False, "mix": False, "music": False
    })
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "DownloadConfig":
        """Tải cấu hình từ file YAML"""
        # TODO: Thêm logic đọc YAML
        
    @classmethod 
    def from_args(cls, args) -> "DownloadConfig":
        """Tải cấu hình từ tham số dòng lệnh"""
        # TODO: Thêm logic đọc tham số
        
    def validate(self) -> bool:
        """Xác minh cấu hình hợp lệ"""
        # TODO: Thêm logic xác minh

configModel = {
    "link": [],
    "path": os.getcwd(),
    "music": True,
    "cover": True,
    "avatar": True,
    "json": True,
    "start_time": "",
    "end_time": "",
    "folderstyle": True,
    "mode": ["post"],
    "number": {
        "post": 0,
        "like": 0,
        "allmix": 0,
        "mix": 0,
        "music": 0,
    },
    'database': True,
    "increase": {
        "post": False,
        "like": False,
        "allmix": False,
        "mix": False,
        "music": False,
    },
    "thread": 5,
    "cookie": os.environ.get("DOUYIN_COOKIE", "")
}

def argument():
    parser = argparse.ArgumentParser(description='Hỗ trợ sử dụng công cụ tải hàng loạt Douyin')
    parser.add_argument("--cmd", "-C", help="Dùng dòng lệnh (True) hay file cấu hình (False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--link", "-l",
                        help="Liên kết chia sẻ tác phẩm (video hoặc ảnh), livestream, bộ sưu tập, nhạc hoặc trang cá nhân; có thể đặt nhiều link (xoá văn bản, chỉ giữ URL, bắt đầu bằng https://v.douyin.com/ hoặc https://www.douyin.com/)",
                        type=str, required=False, default=[], action="append")
    parser.add_argument("--path", "-p", help="Đường dẫn lưu, mặc định thư mục hiện tại",
                        type=str, required=False, default=os.getcwd())
    parser.add_argument("--music", "-m", help="Có tải nhạc trong video không (True/False), mặc định True",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--cover", "-c", help="Có tải ảnh bìa của video không (True/False), mặc định True, chỉ hiệu lực khi tải video",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--avatar", "-a", help="Có tải avatar của tác giả không (True/False), mặc định True",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--json", "-j", help="Có lưu dữ liệu lấy được không (True/False), mặc định True",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--folderstyle", "-fs", help="Kiểu lưu thư mục, mặc định True",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--mode", "-M", help="Khi link là trang cá nhân, chọn tải tác phẩm đã đăng (post), đã thích (like) hoặc toàn bộ bộ sưu tập (mix); mặc định post, có thể chọn nhiều chế độ",
                        type=str, required=False, default=[], action="append")
    parser.add_argument("--postnumber", help="Số tác phẩm từ trang cá nhân, mặc định 0 là tất cả",
                        type=int, required=False, default=0)
    parser.add_argument("--likenumber", help="Số tác phẩm đã thích, mặc định 0 là tất cả",
                        type=int, required=False, default=0)
    parser.add_argument("--allmixnumber", help="Số bộ sưu tập của trang cá nhân, mặc định 0 là tất cả",
                        type=int, required=False, default=0)
    parser.add_argument("--mixnumber", help="Số tác phẩm trong một bộ sưu tập, mặc định 0 là tất cả",
                        type=int, required=False, default=0)
    parser.add_argument("--musicnumber", help="Số tác phẩm theo nhạc (âm thanh gốc), mặc định 0 là tất cả",
                        type=int, required=False, default=0)
    parser.add_argument("--database", "-d", help="Có dùng cơ sở dữ liệu không, mặc định True; nếu không dùng DB thì tải bổ sung không hoạt động",
                        type=utils.str2bool, required=False, default=True)
    parser.add_argument("--postincrease", help="Bật tải bổ sung cho tác phẩm trang cá nhân (True/False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--likeincrease", help="Bật tải bổ sung cho tác phẩm đã thích (True/False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--allmixincrease", help="Bật tải bổ sung cho bộ sưu tập trang cá nhân (True/False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--mixincrease", help="Bật tải bổ sung cho tác phẩm trong một bộ sưu tập (True/False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--musicincrease", help="Bật tải bổ sung cho tác phẩm theo nhạc (True/False), mặc định False",
                        type=utils.str2bool, required=False, default=False)
    parser.add_argument("--thread", "-t",
                        help="Thiết lập số luồng, mặc định 5",
                        type=int, required=False, default=5)
    parser.add_argument("--cookie", help="Thiết lập cookie, định dạng: \"name1=value1; name2=value2;\" nhớ thêm dấu chấm phẩy",
                        type=str, required=False, default='')
    parser.add_argument("--config", "-F", 
                       type=argparse.FileType('r', encoding='utf-8'),
                       help="Đường dẫn file cấu hình")
    args = parser.parse_args()
    if args.thread <= 0:
        args.thread = 5

    return args


def yamlConfig():
    curPath = os.path.dirname(os.path.realpath(sys.argv[0]))
    yamlPath = os.path.join(curPath, "config.yml")
    
    try:
        with open(yamlPath, 'r', encoding='utf-8') as f:
            configDict = yaml.safe_load(f)
            
        # Dùng dict comprehension để cập nhật cấu hình gọn hơn
        for key in configModel:
            if key in configDict:
                if isinstance(configModel[key], dict):
                    configModel[key].update(configDict[key] or {})
                else:
                    configModel[key] = configDict[key]
                    
        # Xử lý riêng cookie
        if configDict.get("cookies"):
            cookieStr = "; ".join(f"{k}={v}" for k,v in configDict["cookies"].items())
            configModel["cookie"] = cookieStr
            
        # Xử lý riêng end_time
        if configDict.get("end_time") == "now":
                configModel["end_time"] = time.strftime("%Y-%m-%d", time.localtime())
            
    except FileNotFoundError:
        douyin_logger.warning("Không tìm thấy file cấu hình config.yml")
    except Exception as e:
        douyin_logger.warning(f"Lỗi phân tích file cấu hình: {str(e)}")


def validate_config(config: dict) -> bool:
    """Xác minh cấu hình hợp lệ"""
    required_keys = {
        'link': list,
        'path': str,
        'thread': int
    }
    
    for key, typ in required_keys.items():
        if key not in config or not isinstance(config[key], typ):
            douyin_logger.error(f"Cấu hình không hợp lệ: {key}")
            return False
            
    if not all(isinstance(url, str) for url in config['link']):
        douyin_logger.error("Định dạng liên kết không hợp lệ")
        return False
        
    return True


def main():
    start = time.time()

    # Khởi tạo cấu hình
    args = argument()
    if args.cmd:
        update_config_from_args(args)
    else:
        yamlConfig()

    if not validate_config(configModel):
        return

    if not configModel["link"]:
        douyin_logger.error("Chưa thiết lập liên kết tải")
        return

    # Xử lý Cookie
    if configModel["cookie"]:
        douyin_headers["Cookie"] = configModel["cookie"]

    # Xử lý đường dẫn
    configModel["path"] = os.path.abspath(configModel["path"])
    os.makedirs(configModel["path"], exist_ok=True)
    douyin_logger.info(f"Đường dẫn lưu dữ liệu {configModel['path']}")

    # Khởi tạo bộ tải
    dy = Douyin(database=configModel["database"])
    dl = Download(
        thread=configModel["thread"],
        music=configModel["music"],
        cover=configModel["cover"],
        avatar=configModel["avatar"],
        resjson=configModel["json"],
        folderstyle=configModel["folderstyle"]
    )

    # Xử lý từng liên kết
    for link in configModel["link"]:
        process_link(dy, dl, link)

    # Tính thời gian
    duration = time.time() - start
    douyin_logger.info(f'\n[Tải xong]: Tổng thời gian: {int(duration/60)} phút {int(duration%60)} giây\n')


def process_link(dy, dl, link):
    """Xử lý tải cho từng liên kết"""
    douyin_logger.info("-" * 80)
    douyin_logger.info(f"[  Gợi ý  ]: Đang yêu cầu liên kết: {link}")
    
    try:
        url = dy.getShareLink(link)
        key_type, key = dy.getKey(url)
        
        handlers = {
            "user": handle_user_download,
            "mix": handle_mix_download,
            "music": handle_music_download,
            "aweme": handle_aweme_download,
            "live": handle_live_download
        }
        
        handler = handlers.get(key_type)
        if handler:
            handler(dy, dl, key)
        else:
            douyin_logger.warning(f"[  Cảnh báo  ]: Loại liên kết không xác định: {key_type}")
    except Exception as e:
        douyin_logger.error(f"Lỗi khi xử lý liên kết: {str(e)}")


def handle_user_download(dy, dl, key):
    """Xử lý tải trang cá nhân"""
    douyin_logger.info("[  Gợi ý  ]: Đang yêu cầu tác phẩm trong trang cá nhân")
    data = dy.getUserDetailInfo(sec_uid=key)
    nickname = ""
    if data and data.get('user'):
        nickname = utils.replaceStr(data['user']['nickname'])

    userPath = os.path.join(configModel["path"], f"user_{nickname}_{key}")
    os.makedirs(userPath, exist_ok=True)

    for mode in configModel["mode"]:
        douyin_logger.info("-" * 80)
        douyin_logger.info(f"[  Gợi ý  ]: Đang yêu cầu chế độ trang cá nhân: {mode}")
        
        if mode in ('post', 'like'):
            _handle_post_like_mode(dy, dl, key, mode, userPath)
        elif mode == 'mix':
            _handle_mix_mode(dy, dl, key, userPath)

def _handle_post_like_mode(dy, dl, key, mode, userPath):
    """Xử lý chế độ tải tác phẩm đã đăng/đã thích"""
    datalist = dy.getUserInfo(
        key, 
        mode, 
        35, 
        configModel["number"][mode], 
        configModel["increase"][mode],
        start_time=configModel.get("start_time", ""),
        end_time=configModel.get("end_time", "")
    )
    
    if not datalist:
        return
        
    modePath = os.path.join(userPath, mode)
    os.makedirs(modePath, exist_ok=True)
    
    dl.userDownload(awemeList=datalist, savePath=modePath)

def _handle_mix_mode(dy, dl, key, userPath):
    """Xử lý chế độ tải bộ sưu tập"""
    mixIdNameDict = dy.getUserAllMixInfo(key, 35, configModel["number"]["allmix"])
    if not mixIdNameDict:
        return

    modePath = os.path.join(userPath, "mix")
    os.makedirs(modePath, exist_ok=True)

    for mix_id, mix_name in mixIdNameDict.items():
        douyin_logger.info(f'[  Gợi ý  ]: Đang tải tác phẩm trong bộ sưu tập [{mix_name}]')
        mix_file_name = utils.replaceStr(mix_name)
        datalist = dy.getMixInfo(
            mix_id, 
            35, 
            0, 
            configModel["increase"]["allmix"], 
            key,
            start_time=configModel.get("start_time", ""),
            end_time=configModel.get("end_time", "")
        )
        
        if datalist:
            dl.userDownload(awemeList=datalist, savePath=os.path.join(modePath, mix_file_name))
            douyin_logger.info(f'[  Gợi ý  ]: Đã tải xong tác phẩm trong bộ sưu tập [{mix_name}]')

def handle_mix_download(dy, dl, key):
    """Xử lý tải một bộ sưu tập"""
    douyin_logger.info("[  Gợi ý  ]: Đang yêu cầu tác phẩm trong một bộ sưu tập")
    try:
        datalist = dy.getMixInfo(
            key, 
            35, 
            configModel["number"]["mix"], 
            configModel["increase"]["mix"], 
            "",
            start_time=configModel.get("start_time", ""),
            end_time=configModel.get("end_time", "")
        )
        
        if not datalist:
            douyin_logger.error("Không lấy được thông tin bộ sưu tập")
            return
            
        mixname = utils.replaceStr(datalist[0]["mix_info"]["mix_name"])
        mixPath = os.path.join(configModel["path"], f"mix_{mixname}_{key}")
        os.makedirs(mixPath, exist_ok=True)
        dl.userDownload(awemeList=datalist, savePath=mixPath)
    except Exception as e:
        douyin_logger.error(f"Lỗi khi xử lý bộ sưu tập: {str(e)}")

def handle_music_download(dy, dl, key):
    """Xử lý tải theo nhạc"""
    douyin_logger.info("[  Gợi ý  ]: Đang yêu cầu tác phẩm theo nhạc (âm thanh gốc)")
    datalist = dy.getMusicInfo(key, 35, configModel["number"]["music"], configModel["increase"]["music"])

    if datalist:
        musicname = utils.replaceStr(datalist[0]["music"]["title"])
        musicPath = os.path.join(configModel["path"], f"music_{musicname}_{key}")
        os.makedirs(musicPath, exist_ok=True)
        dl.userDownload(awemeList=datalist, savePath=musicPath)

def handle_aweme_download(dy, dl, key):
    """Xử lý tải một tác phẩm"""
    douyin_logger.info("[  Gợi ý  ]: Đang yêu cầu một tác phẩm")
    
    # Số lần thử tối đa
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            douyin_logger.info(f"[  Gợi ý  ]: Lần thử {retry_count+1} để lấy thông tin tác phẩm")
            result = dy.getAwemeInfo(key)
            
            if not result:
                douyin_logger.error("[  Lỗi  ]: Không lấy được thông tin tác phẩm")
                retry_count += 1
                if retry_count < max_retries:
                    douyin_logger.info("[  Gợi ý  ]: Chờ 5 giây rồi thử lại...")
                    time.sleep(5)
                continue
            
            # Dùng trực tiếp dict trả về, không cần giải nén
            datanew = result
            
            if datanew:
                awemePath = os.path.join(configModel["path"], "aweme")
                os.makedirs(awemePath, exist_ok=True)
                
                # Kiểm tra URL video trước khi tải
                video_url = datanew.get("video", {}).get("play_addr", {}).get("url_list", [])
                if not video_url or len(video_url) == 0:
                    douyin_logger.error("[  Lỗi  ]: Không thể lấy URL video")
                    retry_count += 1
                    if retry_count < max_retries:
                        douyin_logger.info("[  Gợi ý  ]: Chờ 5 giây rồi thử lại...")
                        time.sleep(5)
                    continue
                    
                douyin_logger.info(f"[  Gợi ý  ]: Đã lấy URL video, chuẩn bị tải")
                dl.userDownload(awemeList=[datanew], savePath=awemePath)
                douyin_logger.info(f"[  Thành công  ]: Đã tải xong video")
                return True
            else:
                douyin_logger.error("[  Lỗi  ]: Dữ liệu tác phẩm rỗng")
                
            retry_count += 1
            if retry_count < max_retries:
                douyin_logger.info("[  Gợi ý  ]: Chờ 5 giây rồi thử lại...")
                time.sleep(5)
                
        except Exception as e:
            douyin_logger.error(f"[  Lỗi  ]: Gặp lỗi khi xử lý tác phẩm: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                douyin_logger.info("[  Gợi ý  ]: Chờ 5 giây rồi thử lại...")
                time.sleep(5)
    
    douyin_logger.error("[  Thất bại  ]: Đã đạt số lần thử tối đa, không thể tải video")

def handle_live_download(dy, dl, key):
    """Xử lý tải livestream"""
    douyin_logger.info("[  Gợi ý  ]: Đang phân tích luồng trực tiếp")
    live_json = dy.getLiveInfo(key)
    
    if configModel["json"] and live_json:
        livePath = os.path.join(configModel["path"], "live")
        os.makedirs(livePath, exist_ok=True)
        
        live_file_name = utils.replaceStr(f"{key}{live_json['nickname']}")
        json_path = os.path.join(livePath, f"{live_file_name}.json")
        
        douyin_logger.info("[  Gợi ý  ]: Đang lưu thông tin nhận được vào result.json")
        with open(json_path, "w", encoding='utf-8') as f:
            json.dump(live_json, f, ensure_ascii=False, indent=2)

# Chỉ định nghĩa hàm bất đồng bộ khi đủ điều kiện
if ASYNC_SUPPORT:
    async def download_file(url, path):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(path, 'wb') as f:
                        f.write(await response.read())
                    return True
        return False

def update_config_from_args(args):
    """Cập nhật cấu hình từ tham số dòng lệnh"""
    configModel["link"] = args.link
    configModel["path"] = args.path
    configModel["music"] = args.music
    configModel["cover"] = args.cover
    configModel["avatar"] = args.avatar
    configModel["json"] = args.json
    configModel["folderstyle"] = args.folderstyle
    configModel["mode"] = args.mode if args.mode else ["post"]
    configModel["thread"] = args.thread
    configModel["cookie"] = args.cookie
    configModel["database"] = args.database
    
    # Cập nhật dict number
    configModel["number"]["post"] = args.postnumber
    configModel["number"]["like"] = args.likenumber
    configModel["number"]["allmix"] = args.allmixnumber
    configModel["number"]["mix"] = args.mixnumber
    configModel["number"]["music"] = args.musicnumber
    
    # Cập nhật dict increase
    configModel["increase"]["post"] = args.postincrease
    configModel["increase"]["like"] = args.likeincrease
    configModel["increase"]["allmix"] = args.allmixincrease
    configModel["increase"]["mix"] = args.mixincrease
    configModel["increase"]["music"] = args.musicincrease

if __name__ == "__main__":
    main()
