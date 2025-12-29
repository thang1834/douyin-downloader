#!/usr/bin/env python
# -*- coding: utf-8 -*-


import time
import copy


class Result(object):
    def __init__(self):
        # Thông tin tác giả
        self.authorDict = {
            "avatar_thumb": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "avatar": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_url": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            # Số tác phẩm đã thích
            "favoriting_count": "",
            # Số người theo dõi
            "follower_count": "",
            # Số người đang theo dõi
            "following_count": "",
            # Biệt danh
            "nickname": "",
            # Có cho phép tải xuống không
            "prevent_download": "",
            # ID URL người dùng
            "sec_uid": "",
            # Có phải tài khoản riêng tư không
            "secret": "",
            # ID ngắn
            "short_id": "",
            # Chữ ký
            "signature": "",
            # Tổng số lượt thích
            "total_favorited": "",
            # ID người dùng
            "uid": "",
            # ID duy nhất do người dùng tự định nghĩa, số Douyin
            "unique_id": "",
            # Tuổi
            "user_age": "",

        }
        # Thông tin ảnh
        self.picDict = {
            "height": "",
            "mask_url_list": "",
            "uri": "",
            "url_list": [],
            "width": ""
        }
        # Thông tin nhạc
        self.musicDict = {
            "cover_hd": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_large": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_medium": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover_thumb": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            # Số Douyin của tác giả nhạc
            "owner_handle": "",
            # ID tác giả nhạc
            "owner_id": "",
            # Biệt danh tác giả nhạc
            "owner_nickname": "",
            "play_url": {
                "height": "",
                "uri": "",
                "url_key": "",
                "url_list": [],
                "width": ""
            },
            # Tên nhạc
            "title": "",
        }
        # Thông tin video
        self.videoDict = {
            "play_addr": {
                "uri": "",
                "url_list": [],
            },
            "cover_original_scale": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "dynamic_cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "origin_cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            },
            "cover": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": ""
            }
        }
        # Thông tin bộ sưu tập
        self.mixInfo = {
            "cover_url": {
                "height": "",
                "uri": "",
                "url_list": [],
                "width": 720
            },
            "ids": "",
            "is_serial_mix": "",
            "mix_id": "",
            "mix_name": "",
            "mix_pic_type": "",
            "mix_type": "",
            "statis": {
                "current_episode": "",
                "updated_to_episode": ""
            }
        }
        # Thông tin tác phẩm
        self.awemeDict = {
            # Thời gian tạo tác phẩm
            "create_time": "",
            # awemeType=0 Video, awemeType=1 Bộ sưu tập ảnh, awemeType=2 Livestream
            "awemeType": "",
            # ID tác phẩm
            "aweme_id": "",
            # Thông tin tác giả
            "author": self.authorDict,
            # Mô tả tác phẩm
            "desc": "",
            # Ảnh
            "images": [],
            # Nhạc
            "music": self.musicDict,
            # Bộ sưu tập
            "mix_info": self.mixInfo,
            # Video
            "video": self.videoDict,
            # Thống kê thông tin tác phẩm
            "statistics": {
                "admire_count": "",
                "collect_count": "",
                "comment_count": "",
                "digg_count": "",
                "play_count": "",
                "share_count": ""
            }
        }
        # Thông tin tác phẩm người dùng
        self.awemeList = []
        # Thông tin livestream
        self.liveDict = {
            # awemeType=0 Video, awemeType=1 Bộ sưu tập ảnh, awemeType=2 Livestream
            "awemeType": "",
            # Có đang phát sóng không
            "status": "",
            # Tiêu đề livestream
            "title": "",
            # Ảnh bìa livestream
            "cover": "",
            # Avatar
            "avatar": "",
            # Số người xem
            "user_count": "",
            # Biệt danh
            "nickname": "",
            # sec_uid
            "sec_uid": "",
            # Trạng thái xem livestream
            "display_long": "",
            # Stream
            "flv_pull_url": "",
            # Khu vực
            "partition": "",
            "sub_partition": "",
            # Địa chỉ rõ nét nhất
            "flv_pull_url0": "",
        }



    # Chuyển đổi dữ liệu json nhận được (dataRaw) thành dữ liệu tự định nghĩa (dataNew)
    # Chuyển đổi dữ liệu nhận được
    def dataConvert(self, awemeType, dataNew, dataRaw):
        for item in dataNew:
            try:
                # Thời gian tạo tác phẩm
                if item == "create_time":
                    dataNew['create_time'] = time.strftime(
                        "%Y-%m-%d %H.%M.%S", time.localtime(dataRaw['create_time']))
                    continue
                # Thiết lập awemeType
                if item == "awemeType":
                    dataNew["awemeType"] = awemeType
                    continue
                # Khi liên kết được phân tích là ảnh
                if item == "images":
                    if awemeType == 1:
                        for image in dataRaw[item]:
                            for i in image:
                                self.picDict[i] = image[i]
                            # Dictionary cần sao chép sâu
                            self.awemeDict["images"].append(copy.deepcopy(self.picDict))
                    continue
                # Khi liên kết được phân tích là video
                if item == "video":
                    if awemeType == 0:
                        self.dataConvert(awemeType, dataNew[item], dataRaw[item])
                    continue
                # Phóng to avatar nhỏ
                if item == "avatar":
                    for i in dataNew[item]:
                        if i == "url_list":
                            for j in self.awemeDict["author"]["avatar_thumb"]["url_list"]:
                                dataNew[item][i].append(j.replace("100x100", "1080x1080"))
                        elif i == "uri":
                            dataNew[item][i] = self.awemeDict["author"]["avatar_thumb"][i].replace("100x100",
                                                                                                   "1080x1080")
                        else:
                            dataNew[item][i] = self.awemeDict["author"]["avatar_thumb"][i]
                    continue

                # JSON gốc là [{}] còn của chúng ta là {}
                if item == "cover_url":
                    self.dataConvert(awemeType, dataNew[item], dataRaw[item][0])
                    continue

                # Lấy video 1080p theo uri
                if item == "play_addr":
                    dataNew[item]["uri"] = dataRaw["bit_rate"][0]["play_addr"]["uri"]
                    # Sử dụng API này có thể lấy được 1080p
                    # dataNew[item]["url_list"] = "https://aweme.snssdk.com/aweme/v1/play/?video_id=%s&ratio=1080p&line=0" \
                    #                             % dataNew[item]["uri"]
                    dataNew[item]["url_list"] = copy.deepcopy(dataRaw["bit_rate"][0]["play_addr"]["url_list"])
                    continue

                # Duyệt đệ quy dictionary thông thường
                if isinstance(dataNew[item], dict):
                    self.dataConvert(awemeType, dataNew[item], dataRaw[item])
                else:
                    # Gán giá trị
                    dataNew[item] = dataRaw[item]
            except Exception as e:
                # Xóa cảnh báo này, luôn khiến người ta hiểu nhầm là có lỗi
                # print("[  Cảnh báo  ]:Không tìm thấy %s trong interface khi chuyển đổi dữ liệu\r" % (item))
                pass

    def clearDict(self, data):
        for item in data:
            # Duyệt đệ quy dictionary thông thường
            if isinstance(data[item], dict):
                self.clearDict(data[item])
            elif isinstance(data[item], list):
                data[item] = []
            else:
                data[item] = ""


if __name__ == '__main__':
    pass
