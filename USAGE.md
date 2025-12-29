# Hướng dẫn sử dụng trình tải Douyin

## 🚀 Bắt đầu nhanh

### 1. Cài đặt phụ thuộc
```bash
pip install -r requirements.txt
```

### 2. Cấu hình Cookie (cần cho lần đầu)
```bash
# Tự động lấy (khuyến nghị)
python cookie_extractor.py

# Hoặc lấy thủ công
python get_cookies_manual.py
```

### 3. Bắt đầu tải

#### V1.0 ổn định (gợi ý cho video đơn)
```bash
# Chỉnh file cấu hình config.yml
# Sau đó chạy
python DouYinCommand.py
```

#### V2.0 tăng cường (gợi ý cho trang cá nhân)
```bash
# Tải trang cá nhân
python downloader.py -u "https://www.douyin.com/user/xxxxx"

# Tự lấy Cookie rồi tải
python downloader.py --auto-cookie -u "https://www.douyin.com/user/xxxxx"
```

## 📋 So sánh phiên bản

| Tính năng | V1.0 (DouYinCommand.py) | V2.0 (downloader.py) |
|------|------------------------|---------------------|
| Tải video đơn | ✅ Hoàn toàn ổn định | ⚠️ Lỗi API |
| Tải trang cá nhân | ✅ Bình thường | ✅ Hoàn toàn ổn định |
| Quản lý Cookie | Cấu hình thủ công | Tự động lấy |
| Độ phức tạp sử dụng | Đơn giản | Trung bình |
| Độ ổn định | Cao | Trung bình |

## 🎯 Kịch bản khuyến nghị

- **Tải video đơn**: dùng V1.0
- **Tải trang cá nhân**: dùng V2.0
- **Tải hàng loạt**: dùng V2.0
- **Học tập nghiên cứu**: cả hai phiên bản đều được

## 📞 Nhận hỗ trợ

- Xem tài liệu chi tiết: `README.md`
- Báo lỗi: [GitHub Issues](https://github.com/jiji262/douyin-downloader/issues)
