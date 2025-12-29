#!/usr/bin/env python
# -*- coding: utf-8 -*-


class Urls(object):
    def __init__(self):
        ######################################### WEB #########################################
        # Trang chủ đề xuất
        self.TAB_FEED = 'https://www.douyin.com/aweme/v1/web/tab/feed/?'

        # Thông tin ngắn người dùng (trả về thông tin người dùng tương ứng với số lượng secid người dùng được cung cấp)
        self.USER_SHORT_INFO = 'https://www.douyin.com/aweme/v1/web/im/user/info/?'

        # Thông tin chi tiết người dùng
        self.USER_DETAIL = 'https://www.douyin.com/aweme/v1/web/user/profile/other/?'

        # Tác phẩm người dùng
        self.USER_POST = 'https://www.douyin.com/aweme/v1/web/aweme/post/?'

        # Thông tin tác phẩm
        self.POST_DETAIL = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?'

        # Người dùng thích A
        # Cần odin_tt
        self.USER_FAVORITE_A = 'https://www.douyin.com/aweme/v1/web/aweme/favorite/?'

        # Người dùng thích B
        self.USER_FAVORITE_B = 'https://www.iesdouyin.com/web/api/v2/aweme/like/?'

        # Lịch sử người dùng
        self.USER_HISTORY = 'https://www.douyin.com/aweme/v1/web/history/read/?'

        # Bộ sưu tập người dùng
        self.USER_COLLECTION = 'https://www.douyin.com/aweme/v1/web/aweme/listcollection/?'

        # Bình luận người dùng
        self.COMMENT = 'https://www.douyin.com/aweme/v1/web/comment/list/?'

        # Tác phẩm bạn bè trang chủ
        self.FRIEND_FEED = 'https://www.douyin.com/aweme/v1/web/familiar/feed/?'

        # Tác phẩm người dùng đang theo dõi
        self.FOLLOW_FEED = 'https://www.douyin.com/aweme/v1/web/follow/feed/?'

        # Tất cả tác phẩm trong bộ sưu tập
        # Chỉ cần X-Bogus
        self.USER_MIX = 'https://www.douyin.com/aweme/v1/web/mix/aweme/?'

        # Danh sách tất cả bộ sưu tập người dùng
        # Cần ttwid
        self.USER_MIX_LIST = 'https://www.douyin.com/aweme/v1/web/mix/list/?'

        # Livestream
        self.LIVE = 'https://live.douyin.com/webcast/room/web/enter/?'
        self.LIVE2 = 'https://webcast.amemv.com/webcast/room/reflow/info/?'

        # Nhạc
        self.MUSIC = 'https://www.douyin.com/aweme/v1/web/music/aweme/?'

        #######################################################################################


if __name__ == '__main__':
    pass
