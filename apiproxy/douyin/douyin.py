#!/usr/bin/env python
# -*- coding: utf-8 -*-


import re
import requests
import json
import time
import copy
# from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Tuple, Optional
from requests.exceptions import RequestException
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console

from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls
from apiproxy.douyin.result import Result
from apiproxy.douyin.database import DataBase
from apiproxy.common import utils
import sys
import os
# Thêm thư mục gốc dự án vào đường dẫn hệ thống, đảm bảo có thể import module utils đúng cách
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.logger import logger

# Tạo instance console toàn cục
console = Console()

class Douyin(object):

    def __init__(self, database=False):
        self.urls = Urls()
        self.result = Result()
        self.database = database
        if database:
            self.db = DataBase()
        # Dùng để thiết lập thời gian tối đa cho việc lặp lại request một interface
        self.timeout = 10
        self.console = Console()  # Cũng có thể tạo console trong instance

    # Trích xuất URL từ liên kết chia sẻ
    def getShareLink(self, string):
        # findall() tìm chuỗi khớp với biểu thức chính quy
        return re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)[0]

    # Lấy ID tác phẩm hoặc ID người dùng
    # URL truyền vào hỗ trợ https://www.iesdouyin.com và https://v.douyin.com
    def getKey(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Lấy định danh tài nguyên
        Args:
            url: Liên kết chia sẻ Douyin hoặc URL trang web
        Returns:
            (Loại tài nguyên, ID tài nguyên)
        """
        key = None
        key_type = None

        try:
            r = requests.get(url=url, headers=douyin_headers)
        except Exception as e:
            print('[  Lỗi  ]:Liên kết nhập vào không hợp lệ!\r')
            return key_type, key

        # Douyin đã cập nhật bộ ảnh thành note
        # Tác phẩm: liên kết được phân tích ở bước đầu là share/video/{aweme_id}
        # https://www.iesdouyin.com/share/video/7037827546599263488/?region=CN&mid=6939809470193126152&u_code=j8a5173b&did=MS4wLjABAAAA1DICF9-A9M_CiGqAJZdsnig5TInVeIyPdc2QQdGrq58xUgD2w6BqCHovtqdIDs2i&iid=MS4wLjABAAAAomGWi4n2T0H9Ab9x96cUZoJXaILk4qXOJlJMZFiK6b_aJbuHkjN_f0mBzfy91DX1&with_sec_did=1&titleType=title&schema_type=37&from_ssr=1&utm_source=copy&utm_campaign=client_share&utm_medium=android&app=aweme
        # Người dùng: liên kết được phân tích ở bước đầu là share/user/{sec_uid}
        # https://www.iesdouyin.com/share/user/MS4wLjABAAAA06y3Ctu8QmuefqvUSU7vr0c_ZQnCqB0eaglgkelLTek?did=MS4wLjABAAAA1DICF9-A9M_CiGqAJZdsnig5TInVeIyPdc2QQdGrq58xUgD2w6BqCHovtqdIDs2i&iid=MS4wLjABAAAAomGWi4n2T0H9Ab9x96cUZoJXaILk4qXOJlJMZFiK6b_aJbuHkjN_f0mBzfy91DX1&with_sec_did=1&sec_uid=MS4wLjABAAAA06y3Ctu8QmuefqvUSU7vr0c_ZQnCqB0eaglgkelLTek&from_ssr=1&u_code=j8a5173b&timestamp=1674540164&ecom_share_track_params=%7B%22is_ec_shopping%22%3A%221%22%2C%22secuid%22%3A%22MS4wLjABAAAA-jD2lukp--I21BF8VQsmYUqJDbj3FmU-kGQTHl2y1Cw%22%2C%22enter_from%22%3A%22others_homepage%22%2C%22share_previous_page%22%3A%22others_homepage%22%7D&utm_source=copy&utm_campaign=client_share&utm_medium=android&app=aweme
        # Bộ sưu tập
        # https://www.douyin.com/collection/7093490319085307918
        urlstr = str(r.request.path_url)

        if "/user/" in urlstr:
            # Lấy sec_uid người dùng
            if '?' in r.request.path_url:
                for one in re.finditer(r'user\/([\d\D]*)([?])', str(r.request.path_url)):
                    key = one.group(1)
            else:
                for one in re.finditer(r'user\/([\d\D]*)', str(r.request.path_url)):
                    key = one.group(1)
            key_type = "user"
        elif "/video/" in urlstr:
            # Lấy aweme_id tác phẩm
            key = re.findall('video/(\d+)?', urlstr)[0]
            key_type = "aweme"
        elif "/note/" in urlstr:
            # Lấy aweme_id note
            key = re.findall('note/(\d+)?', urlstr)[0]
            key_type = "aweme"
        elif "/mix/detail/" in urlstr:
            # Lấy ID bộ sưu tập
            key = re.findall('/mix/detail/(\d+)?', urlstr)[0]
            key_type = "mix"
        elif "/collection/" in urlstr:
            # Lấy ID bộ sưu tập
            key = re.findall('/collection/(\d+)?', urlstr)[0]
            key_type = "mix"
        elif "/music/" in urlstr:
            # Lấy ID nhạc gốc
            key = re.findall('music/(\d+)?', urlstr)[0]
            key_type = "music"
        elif "/webcast/reflow/" in urlstr:
            key1 = re.findall('reflow/(\d+)?', urlstr)[0]
            url = self.urls.LIVE2 + utils.getXbogus(
                f'live_id=1&room_id={key1}&app_id=1128')
            res = requests.get(url, headers=douyin_headers)
            resjson = json.loads(res.text)
            key = resjson['data']['room']['owner']['web_rid']
            key_type = "live"
        elif "live.douyin.com" in r.url:
            key = r.url.replace('https://live.douyin.com/', '')
            key_type = "live"

        if key is None or key_type is None:
            print('[  Lỗi  ]:Liên kết nhập vào không hợp lệ! Không thể lấy id\r')
            return key_type, key

        return key_type, key

    # Tạm thời comment decorator
    # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def getAwemeInfo(self, aweme_id: str) -> dict:
        """Lấy thông tin tác phẩm (có cơ chế thử lại)

        Do interface video đơn của Douyin thường trả về phản hồi rỗng, ở đây triển khai một phương án dự phòng:
        1. Đầu tiên thử interface video đơn gốc
        2. Nếu thất bại, thử lấy thông tin video qua interface tìm kiếm
        3. Nếu vẫn thất bại, trả về dictionary rỗng
        """
        retries = 3
        for attempt in range(retries):
            try:
                logger.info(f'[  Gợi ý  ]:Đang yêu cầu tác phẩm có id = {aweme_id}')
                if aweme_id is None:
                    return {}

                # Phương pháp 1: Thử interface video đơn gốc
                result = self._try_detail_api(aweme_id)
                if result:
                    return result

                # Phương pháp 2: Nếu interface video đơn thất bại, thử phương án dự phòng
                logger.warning("Interface video đơn thất bại, đang thử phương án dự phòng...")
                result = self._try_alternative_method(aweme_id)
                if result:
                    return result

                logger.warning(f"Tất cả phương pháp đều thất bại, đang thử {attempt+1}/{retries}")
                time.sleep(2 ** attempt)

            except Exception as e:
                logger.warning(f"Yêu cầu thất bại (thử {attempt+1}/{retries}): {str(e)}")
                time.sleep(2 ** attempt)

        logger.error(f"Không thể lấy thông tin video {aweme_id}")
        return {}

    def _try_detail_api(self, aweme_id: str) -> dict:
        """Thử sử dụng interface video đơn gốc"""
        try:
            start = time.time()
            while True:
                try:
                    # Interface tác phẩm đơn trả về 'aweme_detail'
                    # Interface tác phẩm trang chủ trả về 'aweme_list'->['aweme_detail']
                    # Cập nhật tham số API để phù hợp với yêu cầu interface mới nhất
                    detail_params = f'aweme_id={aweme_id}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50&update_version_code=170400'
                    jx_url = self.urls.POST_DETAIL + utils.getXbogus(detail_params)

                    response = requests.get(url=jx_url, headers=douyin_headers, timeout=10)

                    # Kiểm tra phản hồi có rỗng không
                    if len(response.text) == 0:
                        logger.warning("Interface video đơn trả về phản hồi rỗng")
                        return {}

                    datadict = json.loads(response.text)

                    # Thêm thông tin debug
                    logger.info(f"Trạng thái phản hồi API video đơn: {datadict.get('status_code') if datadict else 'None'}")
                    if datadict and datadict.get("status_code") != 0:
                        logger.warning(f"Lỗi API video đơn: {datadict.get('status_msg', 'Lỗi không xác định')}")
                        return {}

                    if datadict is not None and datadict.get("status_code") == 0:
                        # Kiểm tra xem có trường aweme_detail không
                        if "aweme_detail" not in datadict:
                            logger.error(f"Phản hồi thiếu trường aweme_detail, các trường có sẵn: {list(datadict.keys())}")
                            return {}
                        break
                except Exception as e:
                    end = time.time()
                    if end - start > self.timeout:
                        logger.warning(f"Lặp lại yêu cầu interface này {self.timeout}s, vẫn chưa lấy được dữ liệu")
                        return {}

            # Xóa self.awemeDict
            self.result.clearDict(self.result.awemeDict)

            # Mặc định là video
            awemeType = 0
            try:
                # datadict['aweme_detail']["images"] không phải None nghĩa là bộ sưu tập ảnh
                if datadict['aweme_detail']["images"] is not None:
                    awemeType = 1
            except Exception as e:
                logger.warning("Không tìm thấy images trong interface")

            # Chuyển đổi sang định dạng của chúng ta
            self.result.dataConvert(awemeType, self.result.awemeDict, datadict['aweme_detail'])

            return self.result.awemeDict

        except Exception as e:
            logger.warning(f"Interface video đơn có ngoại lệ: {str(e)}")
            return {}

    def _try_alternative_method(self, aweme_id: str) -> dict:
        """Phương án dự phòng: Lấy thông tin video qua cách khác

        Ở đây có thể triển khai:
        1. Tìm video qua interface tìm kiếm
        2. Tìm video qua interface trang chủ người dùng
        3. Các phương pháp khác có thể
        """
        logger.info("Đang thử phương án dự phòng để lấy thông tin video...")

        # Hiện tại trả về dictionary rỗng, nghĩa là phương án dự phòng chưa được triển khai
        # Có thể thêm các phương pháp lấy thông tin video khác ở đây
        logger.warning("Phương án dự phòng chưa được triển khai")
        return {}

    # URL truyền vào hỗ trợ https://www.iesdouyin.com và https://v.douyin.com
    # mode : post | like Lựa chọn chế độ like là thích của người dùng, post là đăng của người dùng
    def getUserInfo(self, sec_uid, mode="post", count=35, number=0, increase=False, start_time="", end_time=""):
        """Lấy thông tin người dùng
        Args:
            sec_uid: ID người dùng
            mode: Chế độ (post: đăng/like: thích)
            count: Số lượng mỗi trang
            number: Giới hạn số lượng tải xuống (0 nghĩa là không giới hạn)
            increase: Có cập nhật tăng dần không
            start_time: Thời gian bắt đầu, định dạng: YYYY-MM-DD
            end_time: Thời gian kết thúc, định dạng: YYYY-MM-DD
        """
        if sec_uid is None:
            return None

        # Xử lý phạm vi thời gian
        if end_time == "now":
            end_time = time.strftime("%Y-%m-%d")
        
        if not start_time:
            start_time = "1970-01-01"
        if not end_time:
            end_time = "2099-12-31"

        self.console.print(f"[cyan]🕒 Phạm vi thời gian: {start_time} đến {end_time}[/]")
        
        max_cursor = 0
        awemeList = []
        total_fetched = 0
        filtered_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True
        ) as progress:
            fetch_task = progress.add_task(
                f"[cyan]📥 Đang lấy danh sách tác phẩm {mode}...", 
                total=None  # Tổng số chưa biết, sử dụng thanh tiến độ vô hạn
            )
            
            while True:
                try:
                    # Xây dựng URL yêu cầu - thêm các tham số bắt buộc
                    base_params = f'sec_user_id={sec_uid}&count={count}&max_cursor={max_cursor}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'

                    if mode == "post":
                        url = self.urls.USER_POST + utils.getXbogus(base_params)
                    elif mode == "like":
                        # Thử interface like dự phòng
                        try:
                            url = self.urls.USER_FAVORITE_A + utils.getXbogus(base_params)
                        except:
                            # Nếu interface chính thất bại, thử interface dự phòng
                            url = self.urls.USER_FAVORITE_B + utils.getXbogus(base_params)
                    else:
                        self.console.print("[red]❌ Lựa chọn chế độ sai, chỉ hỗ trợ post, like[/]")
                        return None

                    # Gửi yêu cầu
                    res = requests.get(url=url, headers=douyin_headers, timeout=10)

                    # Kiểm tra mã trạng thái HTTP
                    if res.status_code != 200:
                        self.console.print(f"[red]❌ Yêu cầu HTTP thất bại: {res.status_code}[/]")
                        break

                    try:
                        datadict = json.loads(res.text)
                    except json.JSONDecodeError as e:
                        self.console.print(f"[red]❌ Phân tích JSON thất bại: {str(e)}[/]")
                        self.console.print(f"[yellow]🔍 Nội dung phản hồi: {res.text[:500]}...[/]")
                        self.console.print(f"[yellow]🔍 URL yêu cầu: {url}[/]")
                        self.console.print(f"[yellow]🔍 Chế độ: {mode}[/]")

                        # Kiểm tra xem có phải phản hồi rỗng hoặc vấn đề quyền không
                        if not res.text.strip():
                            self.console.print(f"[yellow]💡 Gợi ý: Chế độ {mode} có thể cần quyền đặc biệt hoặc danh sách {mode} của người dùng này không công khai[/]")
                        elif "登录" in res.text or "login" in res.text.lower():
                            self.console.print(f"[yellow]💡 Gợi ý: Chế độ {mode} cần trạng thái đăng nhập[/]")
                        elif "权限" in res.text or "permission" in res.text.lower():
                            self.console.print(f"[yellow]💡 Gợi ý: Chế độ {mode} quyền không đủ[/]")
                        break
                    
                    # Xử lý dữ liệu trả về
                    if not datadict or datadict.get("status_code") != 0:
                        self.console.print(f"[red]❌ Yêu cầu API thất bại: {datadict.get('status_msg', 'Lỗi không xác định')}[/]")
                        # In thông tin phản hồi chi tiết để debug
                        self.console.print(f"[yellow]🔍 Mã trạng thái phản hồi: {datadict.get('status_code') if datadict else 'None'}[/]")
                        self.console.print(f"[yellow]🔍 Nội dung phản hồi: {str(datadict)[:200]}...[/]")
                        break

                    # Kiểm tra xem trường aweme_list có tồn tại không
                    if "aweme_list" not in datadict:
                        self.console.print(f"[red]❌ Phản hồi thiếu trường aweme_list[/]")
                        self.console.print(f"[yellow]🔍 Các trường có sẵn: {list(datadict.keys())}[/]")
                        break

                    current_count = len(datadict["aweme_list"])
                    total_fetched += current_count
                    
                    # Cập nhật hiển thị tiến độ
                    progress.update(
                        fetch_task, 
                        description=f"[cyan]📥 Đã lấy: {total_fetched} tác phẩm"
                    )

                    # Thêm lọc thời gian khi xử lý tác phẩm
                    for aweme in datadict["aweme_list"]:
                        create_time = time.strftime(
                            "%Y-%m-%d", 
                            time.localtime(int(aweme.get("create_time", 0)))
                        )
                        
                        # Lọc thời gian
                        if not (start_time <= create_time <= end_time):
                            filtered_count += 1
                            continue

                        # Kiểm tra giới hạn số lượng
                        if number > 0 and len(awemeList) >= number:
                            self.console.print(f"[green]✅ Đã đạt giới hạn số lượng: {number}[/]")
                            return awemeList
                            
                        # Kiểm tra cập nhật tăng dần
                        if self.database:
                            if mode == "post":
                                if self.db.get_user_post(sec_uid=sec_uid, aweme_id=aweme['aweme_id']):
                                    if increase and aweme['is_top'] == 0:
                                        self.console.print("[green]✅ Cập nhật tăng dần hoàn tất[/]")
                                        return awemeList
                                else:
                                    self.db.insert_user_post(sec_uid=sec_uid, aweme_id=aweme['aweme_id'], data=aweme)
                            elif mode == "like":
                                if self.db.get_user_like(sec_uid=sec_uid, aweme_id=aweme['aweme_id']):
                                    if increase and aweme['is_top'] == 0:
                                        self.console.print("[green]✅ Cập nhật tăng dần hoàn tất[/]")
                                        return awemeList
                            else:
                                self.console.print("[red]❌ Lựa chọn chế độ sai, chỉ hỗ trợ post, like[/]")
                                return None

                        # Chuyển đổi định dạng dữ liệu
                        aweme_data = self._convert_aweme_data(aweme)
                        if aweme_data:
                            awemeList.append(aweme_data)

                    # Kiểm tra xem còn dữ liệu không
                    if not datadict["has_more"]:
                        self.console.print(f"[green]✅ Đã lấy tất cả tác phẩm: {total_fetched} tác phẩm[/]")
                        break
                    
                    # Cập nhật con trỏ
                    max_cursor = datadict["max_cursor"]
                    
                except Exception as e:
                    self.console.print(f"[red]❌ Lỗi khi lấy danh sách tác phẩm: {str(e)}[/]")
                    break

        return awemeList

    def _convert_aweme_data(self, aweme):
        """Chuyển đổi định dạng dữ liệu tác phẩm"""
        try:
            self.result.clearDict(self.result.awemeDict)
            aweme_type = 1 if aweme.get("images") else 0
            self.result.dataConvert(aweme_type, self.result.awemeDict, aweme)
            return copy.deepcopy(self.result.awemeDict)
        except Exception as e:
            logger.error(f"Lỗi chuyển đổi dữ liệu: {str(e)}")
            return None

    def getLiveInfo(self, web_rid: str):
        print('[  Gợi ý  ]:Đang yêu cầu livestream có id = %s\r\n' % web_rid)

        start = time.time()  # Thời gian bắt đầu
        while True:
            # Interface không ổn định, đôi khi server không trả về dữ liệu, cần lấy lại
            try:
                live_params = f'aid=6383&device_platform=web&web_rid={web_rid}&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                live_api = self.urls.LIVE + utils.getXbogus(live_params)

                response = requests.get(live_api, headers=douyin_headers)
                live_json = json.loads(response.text)
                if live_json != {} and live_json['status_code'] == 0:
                    break
            except Exception as e:
                end = time.time()  # Thời gian kết thúc
                if end - start > self.timeout:
                    print("[  Gợi ý  ]:Lặp lại yêu cầu interface này " + str(self.timeout) + "s, vẫn chưa lấy được dữ liệu")
                    return {}

        # Xóa dictionary
        self.result.clearDict(self.result.liveDict)

        # Loại
        self.result.liveDict["awemeType"] = 2
        # Có đang phát sóng không
        self.result.liveDict["status"] = live_json['data']['data'][0]['status']

        if self.result.liveDict["status"] == 4:
            print('[   📺   ]:Livestream hiện tại đã kết thúc, đang thoát')
            return self.result.liveDict

        # Tiêu đề livestream
        self.result.liveDict["title"] = live_json['data']['data'][0]['title']

        # Ảnh bìa livestream
        self.result.liveDict["cover"] = live_json['data']['data'][0]['cover']['url_list'][0]

        # Avatar
        self.result.liveDict["avatar"] = live_json['data']['data'][0]['owner']['avatar_thumb']['url_list'][0].replace(
            "100x100", "1080x1080")

        # Số người xem
        self.result.liveDict["user_count"] = live_json['data']['data'][0]['user_count_str']

        # Biệt danh
        self.result.liveDict["nickname"] = live_json['data']['data'][0]['owner']['nickname']

        # sec_uid
        self.result.liveDict["sec_uid"] = live_json['data']['data'][0]['owner']['sec_uid']

        # Trạng thái xem livestream
        self.result.liveDict["display_long"] = live_json['data']['data'][0]['room_view_stats']['display_long']

        # Stream
        self.result.liveDict["flv_pull_url"] = live_json['data']['data'][0]['stream_url']['flv_pull_url']

        try:
            # Khu vực
            self.result.liveDict["partition"] = live_json['data']['partition_road_map']['partition']['title']
            self.result.liveDict["sub_partition"] = \
                live_json['data']['partition_road_map']['sub_partition']['partition']['title']
        except Exception as e:
            self.result.liveDict["partition"] = 'Không có'
            self.result.liveDict["sub_partition"] = 'Không có'

        info = '[   💻   ]:Livestream：%s  Hiện tại%s  Streamer：%s Khu vực：%s-%s\r' % (
            self.result.liveDict["title"], self.result.liveDict["display_long"], self.result.liveDict["nickname"],
            self.result.liveDict["partition"], self.result.liveDict["sub_partition"])
        print(info)

        flv = []
        print('[   🎦   ]:Độ phân giải livestream')
        for i, f in enumerate(self.result.liveDict["flv_pull_url"].keys()):
            print('[   %s   ]: %s' % (i, f))
            flv.append(f)

        rate = int(input('[   🎬   ]Nhập số để chọn độ phân giải stream：'))

        self.result.liveDict["flv_pull_url0"] = self.result.liveDict["flv_pull_url"][flv[rate]]

        # Hiển thị danh sách độ phân giải
        print('[   %s   ]:%s' % (flv[rate], self.result.liveDict["flv_pull_url"][flv[rate]]))
        print('[   📺   ]:Sao chép liên kết để tải xuống bằng công cụ tải xuống')
        return self.result.liveDict

    def getMixInfo(self, mix_id, count=35, number=0, increase=False, sec_uid="", start_time="", end_time=""):
        """Lấy thông tin bộ sưu tập"""
        if mix_id is None:
            return None

        # Xử lý phạm vi thời gian
        if end_time == "now":
            end_time = time.strftime("%Y-%m-%d")
        
        if not start_time:
            start_time = "1970-01-01"
        if not end_time:
            end_time = "2099-12-31"

        self.console.print(f"[cyan]🕒 Phạm vi thời gian: {start_time} đến {end_time}[/]")

        cursor = 0
        awemeList = []
        total_fetched = 0
        filtered_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=True
        ) as progress:
            fetch_task = progress.add_task(
                "[cyan]📥 Đang lấy tác phẩm bộ sưu tập...",
                total=None
            )

            while True:  # Vòng lặp ngoài
                try:
                    mix_params = f'mix_id={mix_id}&cursor={cursor}&count={count}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                    url = self.urls.USER_MIX + utils.getXbogus(mix_params)

                    res = requests.get(url=url, headers=douyin_headers, timeout=10)

                    # Kiểm tra mã trạng thái HTTP
                    if res.status_code != 200:
                        self.console.print(f"[red]❌ Yêu cầu HTTP bộ sưu tập thất bại: {res.status_code}[/]")
                        break

                    try:
                        datadict = json.loads(res.text)
                    except json.JSONDecodeError as e:
                        self.console.print(f"[red]❌ Phân tích JSON bộ sưu tập thất bại: {str(e)}[/]")
                        self.console.print(f"[yellow]🔍 Nội dung phản hồi: {res.text[:500]}...[/]")
                        break

                    if not datadict:
                        self.console.print("[red]❌ Lấy dữ liệu bộ sưu tập thất bại[/]")
                        break

                    if datadict.get("status_code") != 0:
                        self.console.print(f"[red]❌ Yêu cầu API bộ sưu tập thất bại: {datadict.get('status_msg', 'Lỗi không xác định')}[/]")
                        break

                    if "aweme_list" not in datadict:
                        self.console.print(f"[red]❌ Phản hồi bộ sưu tập thiếu trường aweme_list[/]")
                        self.console.print(f"[yellow]🔍 Các trường có sẵn: {list(datadict.keys())}[/]")
                        break

                    for aweme in datadict["aweme_list"]:
                        create_time = time.strftime(
                            "%Y-%m-%d",
                            time.localtime(int(aweme.get("create_time", 0)))
                        )

                        # Lọc thời gian
                        if not (start_time <= create_time <= end_time):
                            filtered_count += 1
                            continue

                        # Kiểm tra giới hạn số lượng
                        if number > 0 and len(awemeList) >= number:
                            return awemeList  # Sử dụng return thay cho break

                        # Kiểm tra cập nhật tăng dần
                        if self.database:
                            if self.db.get_mix(sec_uid=sec_uid, mix_id=mix_id, aweme_id=aweme['aweme_id']):
                                if increase and aweme['is_top'] == 0:
                                    return awemeList  # Sử dụng return thay cho break
                            else:
                                self.db.insert_mix(sec_uid=sec_uid, mix_id=mix_id, aweme_id=aweme['aweme_id'], data=aweme)

                        # Chuyển đổi dữ liệu
                        aweme_data = self._convert_aweme_data(aweme)
                        if aweme_data:
                            awemeList.append(aweme_data)

                    # Kiểm tra xem còn dữ liệu không
                    if not datadict.get("has_more"):
                        self.console.print(f"[green]✅ Đã lấy tất cả tác phẩm[/]")
                        break

                    # Cập nhật con trỏ
                    cursor = datadict.get("cursor", 0)
                    total_fetched += len(datadict["aweme_list"])
                    progress.update(fetch_task, description=f"[cyan]📥 Đã lấy: {total_fetched} tác phẩm")

                except Exception as e:
                    self.console.print(f"[red]❌ Lỗi khi lấy danh sách tác phẩm: {str(e)}[/]")
                    # Thêm thông tin lỗi chi tiết hơn
                    if 'datadict' in locals():
                        self.console.print(f"[yellow]🔍 Phản hồi cuối cùng: {str(datadict)[:300]}...[/]")
                    break

        if filtered_count > 0:
            self.console.print(f"[yellow]⚠️  Đã lọc {filtered_count} tác phẩm không nằm trong phạm vi thời gian[/]")

        return awemeList

    def getUserAllMixInfo(self, sec_uid, count=35, number=0):
        print('[  Gợi ý  ]:Đang yêu cầu người dùng có id = %s\r\n' % sec_uid)
        if sec_uid is None:
            return None
        if number <= 0:
            numflag = False
        else:
            numflag = True

        cursor = 0
        mixIdNameDict = {}

        print("[  Gợi ý  ]:Đang lấy tất cả dữ liệu bộ sưu tập trên trang chủ, vui lòng đợi...\r")
        print("[  Gợi ý  ]:Sẽ thực hiện nhiều yêu cầu, thời gian chờ sẽ lâu hơn...\r\n")
        times = 0
        while True:
            times = times + 1
            print("[  Gợi ý  ]:Đang thực hiện yêu cầu thứ " + str(times) + " cho [Danh sách bộ sưu tập]...\r")

            start = time.time()  # Thời gian bắt đầu
            while True:
                # Interface không ổn định, đôi khi server không trả về dữ liệu, cần lấy lại
                try:
                    mix_list_params = f'sec_user_id={sec_uid}&count={count}&cursor={cursor}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                    url = self.urls.USER_MIX_LIST + utils.getXbogus(mix_list_params)

                    res = requests.get(url=url, headers=douyin_headers, timeout=10)

                    # Kiểm tra mã trạng thái HTTP
                    if res.status_code != 200:
                        self.console.print(f"[red]❌ Yêu cầu HTTP danh sách bộ sưu tập thất bại: {res.status_code}[/]")
                        break

                    try:
                        # Thử phân tích trực tiếp, nếu thất bại thì kiểm tra xem có phải định dạng nén không
                        try:
                            datadict = json.loads(res.text)
                        except json.JSONDecodeError:
                            # Có thể là phản hồi nén, thử giải nén thủ công
                            content_encoding = res.headers.get('content-encoding', '').lower()
                            if content_encoding == 'gzip':
                                import gzip
                                content = gzip.decompress(res.content).decode('utf-8')
                                datadict = json.loads(content)
                            elif content_encoding == 'br':
                                try:
                                    import brotli
                                    content = brotli.decompress(res.content).decode('utf-8')
                                    datadict = json.loads(content)
                                except ImportError:
                                    self.console.print("[red]❌ Cần cài đặt thư viện brotli để xử lý nén br: pip install brotli[/]")
                                    raise
                            else:
                                raise  # Ném lại exception gốc
                    except json.JSONDecodeError as e:
                        self.console.print(f"[red]❌ Phân tích JSON danh sách bộ sưu tập thất bại: {str(e)}[/]")
                        self.console.print(f"[yellow]🔍 Nội dung phản hồi: {res.text[:500]}...[/]")
                        self.console.print(f"[yellow]🔍 Tiêu đề phản hồi: {dict(res.headers)}[/]")
                        break

                    # Kiểm tra cấu trúc phản hồi
                    if not datadict:
                        self.console.print("[red]❌ Lấy dữ liệu danh sách bộ sưu tập thất bại[/]")
                        break

                    if datadict.get("status_code") != 0:
                        self.console.print(f"[red]❌ Yêu cầu API danh sách bộ sưu tập thất bại: {datadict.get('status_msg', 'Lỗi không xác định')}[/]")
                        break

                    if "mix_infos" not in datadict:
                        self.console.print(f"[red]❌ Phản hồi thiếu trường mix_infos[/]")
                        self.console.print(f"[yellow]🔍 Các trường có sẵn: {list(datadict.keys())}[/]")
                        break

                    print('[  Gợi ý  ]:Yêu cầu này trả về ' + str(len(datadict["mix_infos"])) + ' bản ghi dữ liệu\r')

                    if datadict is not None and datadict["status_code"] == 0:
                        break
                except Exception as e:
                    end = time.time()  # Thời gian kết thúc
                    if end - start > self.timeout:
                        print("[  Gợi ý  ]:Lặp lại yêu cầu interface này " + str(self.timeout) + "s, vẫn chưa lấy được dữ liệu")
                        return mixIdNameDict

            # Kiểm tra xem datadict có được lấy thành công không
            if 'datadict' not in locals() or not datadict:
                print("[  Gợi ý  ]:Không thể lấy dữ liệu danh sách bộ sưu tập hợp lệ")
                return mixIdNameDict


            for mix in datadict["mix_infos"]:
                mixIdNameDict[mix["mix_id"]] = mix["mix_name"]
                if numflag:
                    number -= 1
                    if number == 0:
                        break
            if numflag and number == 0:
                print("\r\n[  Gợi ý  ]:Đã lấy xong dữ liệu bộ sưu tập với số lượng chỉ định trong [Danh sách bộ sưu tập]...\r\n")
                break

            # Cập nhật max_cursor
            cursor = datadict["cursor"]

            # Điều kiện thoát
            if datadict["has_more"] == 0 or datadict["has_more"] == False:
                print("[  Gợi ý  ]:Đã lấy xong tất cả dữ liệu id bộ sưu tập trong [Danh sách bộ sưu tập]...\r\n")
                break
            else:
                print("\r\n[  Gợi ý  ]:Yêu cầu thứ " + str(times) + " trong [Danh sách bộ sưu tập] thành công...\r\n")

        return mixIdNameDict

    def getMusicInfo(self, music_id: str, count=35, number=0, increase=False):
        print('[  Gợi ý  ]:Đang yêu cầu bộ nhạc có id = %s\r\n' % music_id)
        if music_id is None:
            return None
        if number <= 0:
            numflag = False
        else:
            numflag = True

        cursor = 0
        awemeList = []
        increaseflag = False
        numberis0 = False

        print("[  Gợi ý  ]:Đang lấy tất cả dữ liệu tác phẩm trong bộ nhạc, vui lòng đợi...\r")
        print("[  Gợi ý  ]:Sẽ thực hiện nhiều yêu cầu, thời gian chờ sẽ lâu hơn...\r\n")
        times = 0
        while True:
            times = times + 1
            print("[  Gợi ý  ]:Đang thực hiện yêu cầu thứ " + str(times) + " cho [Bộ nhạc]...\r")

            start = time.time()  # Thời gian bắt đầu
            while True:
                # Interface không ổn định, đôi khi server không trả về dữ liệu, cần lấy lại
                try:
                    music_params = f'music_id={music_id}&cursor={cursor}&count={count}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                    url = self.urls.MUSIC + utils.getXbogus(music_params)

                    res = requests.get(url=url, headers=douyin_headers, timeout=10)

                    # Kiểm tra mã trạng thái HTTP
                    if res.status_code != 200:
                        self.console.print(f"[red]❌ Yêu cầu HTTP nhạc thất bại: {res.status_code}[/]")
                        break

                    try:
                        datadict = json.loads(res.text)
                    except json.JSONDecodeError as e:
                        self.console.print(f"[red]❌ Phân tích JSON nhạc thất bại: {str(e)}[/]")
                        self.console.print(f"[yellow]🔍 Nội dung phản hồi: {res.text[:500]}...[/]")
                        break

                    if not datadict:
                        self.console.print("[red]❌ Lấy dữ liệu nhạc thất bại[/]")
                        break

                    if datadict.get("status_code") != 0:
                        self.console.print(f"[red]❌ Yêu cầu API nhạc thất bại: {datadict.get('status_msg', 'Lỗi không xác định')}[/]")
                        break

                    if "aweme_list" not in datadict:
                        self.console.print(f"[red]❌ Phản hồi nhạc thiếu trường aweme_list[/]")
                        self.console.print(f"[yellow]🔍 Các trường có sẵn: {list(datadict.keys())}[/]")
                        break

                    print('[  Gợi ý  ]:Yêu cầu này trả về ' + str(len(datadict["aweme_list"])) + ' bản ghi dữ liệu\r')

                    if datadict is not None and datadict["status_code"] == 0:
                        break
                except Exception as e:
                    end = time.time()  # Thời gian kết thúc
                    if end - start > self.timeout:
                        print("[  Gợi ý  ]:Lặp lại yêu cầu interface này " + str(self.timeout) + "s, vẫn chưa lấy được dữ liệu")
                        return awemeList


            for aweme in datadict["aweme_list"]:
                if self.database:
                    # Điều kiện thoát
                    if increase is False and numflag and numberis0:
                        break
                    if increase and numflag and numberis0 and increaseflag:
                        break
                    # Cập nhật tăng dần, tìm thời gian phát hành tác phẩm mới nhất không được ghim
                    if self.db.get_music(music_id=music_id, aweme_id=aweme['aweme_id']) is not None:
                        if increase and aweme['is_top'] == 0:
                            increaseflag = True
                    else:
                        self.db.insert_music(music_id=music_id, aweme_id=aweme['aweme_id'], data=aweme)

                    # Điều kiện thoát
                    if increase and numflag is False and increaseflag:
                        break
                    if increase and numflag and numberis0 and increaseflag:
                        break
                else:
                    if numflag and numberis0:
                        break

                if numflag:
                    number -= 1
                    if number == 0:
                        numberis0 = True

                # Xóa self.awemeDict
                self.result.clearDict(self.result.awemeDict)

                # Mặc định là video
                awemeType = 0
                try:
                    if aweme["images"] is not None:
                        awemeType = 1
                except Exception as e:
                    print("[  Cảnh báo  ]:Không tìm thấy images trong interface\r")

                # Chuyển đổi sang định dạng của chúng ta
                self.result.dataConvert(awemeType, self.result.awemeDict, aweme)

                if self.result.awemeDict is not None and self.result.awemeDict != {}:
                    awemeList.append(copy.deepcopy(self.result.awemeDict))

            if self.database:
                if increase and numflag is False and increaseflag:
                    print("\r\n[  Gợi ý  ]: Đã lấy xong dữ liệu cập nhật tăng dần tác phẩm trong [Bộ nhạc]...\r\n")
                    break
                elif increase is False and numflag and numberis0:
                    print("\r\n[  Gợi ý  ]: Đã lấy xong dữ liệu tác phẩm với số lượng chỉ định trong [Bộ nhạc]...\r\n")
                    break
                elif increase and numflag and numberis0 and increaseflag:
                    print("\r\n[  Gợi ý  ]: Đã lấy xong dữ liệu tác phẩm với số lượng chỉ định trong [Bộ nhạc], đã lấy xong dữ liệu cập nhật tăng dần...\r\n")
                    break
            else:
                if numflag and numberis0:
                    print("\r\n[  Gợi ý  ]: Đã lấy xong dữ liệu tác phẩm với số lượng chỉ định trong [Bộ nhạc]...\r\n")
                    break

            # Cập nhật cursor
            cursor = datadict["cursor"]

            # Điều kiện thoát
            if datadict["has_more"] == 0 or datadict["has_more"] == False:
                print("\r\n[  Gợi ý  ]:Đã lấy xong tất cả dữ liệu tác phẩm trong [Bộ nhạc]...\r\n")
                break
            else:
                print("\r\n[  Gợi ý  ]:Yêu cầu thứ " + str(times) + " trong [Bộ nhạc] thành công...\r\n")

        return awemeList

    def getUserDetailInfo(self, sec_uid):
        if sec_uid is None:
            return None

        datadict = {}
        start = time.time()  # Thời gian bắt đầu
        while True:
            # Interface không ổn định, đôi khi server không trả về dữ liệu, cần lấy lại
            try:
                user_detail_params = f'sec_user_id={sec_uid}&device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=MacIntel&browser_name=Chrome&browser_version=122.0.0.0&browser_online=true&engine_name=Blink&engine_version=122.0.0.0&os_name=Mac&os_version=10.15.7&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=50'
                url = self.urls.USER_DETAIL + utils.getXbogus(user_detail_params)

                res = requests.get(url=url, headers=douyin_headers)
                datadict = json.loads(res.text)

                if datadict is not None and datadict["status_code"] == 0:
                    return datadict
            except Exception as e:
                end = time.time()  # Thời gian kết thúc
                if end - start > self.timeout:
                    print("[  Gợi ý  ]:Lặp lại yêu cầu interface này " + str(self.timeout) + "s, vẫn chưa lấy được dữ liệu")
                    return datadict


if __name__ == "__main__":
    pass
