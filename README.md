# Trình tải Douyin - Công cụ tải hàng loạt không logo

![douyin-downloader](https://socialify.git.ci/jiji262/douyin-downloader/image?custom_description=%E6%8A%96%E9%9F%B3%E6%89%B9%E9%87%8F%E4%B8%8B%E8%BD%BD%E5%B7%A5%E5%85%B7%EF%BC%8C%E5%8E%BB%E6%B0%B4%E5%8D%B0%EF%BC%8C%E6%94%AF%E6%8C%81%E8%A7%86%E9%A2%91%E3%80%81%E5%9B%BE%E9%9B%86%E3%80%81%E5%90%88%E9%9B%86%E3%80%81%E9%9F%B3%E4%B9%90%28%E5%8E%9F%E5%A3%B0%29%E3%80%82%0A%E5%85%8D%E8%B4%B9%EF%BC%81%E5%85%8D%E8%B4%B9%EF%BC%81%E5%85%8D%E8%B4%B9%EF%BC%81&description=1&font=Jost&forks=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fjiji262%2Fdouyin-downloader%2Frefs%2Fheads%2Fmain%2Fimg%2Flogo.png&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Light)

Một công cụ mạnh mẽ để tải hàng loạt nội dung Douyin, hỗ trợ video, bộ ảnh, nhạc, livestream và nhiều loại nội dung khác. Có hai phiên bản: V1.0 (ổn định) và V2.0 (tăng cường).

## 📋 Mục lục

- [Bắt đầu nhanh](#-bắt-đầu-nhanh)
- [Giới thiệu phiên bản](#-giới-thiệu-phiên-bản)
- [Hướng dẫn V1.0](#-v10-hướng-dẫn)
- [Hướng dẫn V2.0](#-v20-hướng-dẫn)
- [Công cụ cấu hình Cookie](#-công-cụ-cấu-hình-cookie)
- [Các loại liên kết hỗ trợ](#-các-loại-liên-kết-hỗ-trợ)
- [Câu hỏi thường gặp](#-câu-hỏi-thường-gặp)
- [Nhật ký cập nhật](#-nhật-ký-cập-nhật)

## ⚡ Bắt đầu nhanh

![qun](./img/fuye.jpg)

### Yêu cầu môi trường

- **Python 3.9+**
- **Hệ điều hành**: Windows, macOS, Linux

### Các bước cài đặt

1. **Clone dự án**
```bash
git clone https://github.com/jiji262/douyin-downloader.git
cd douyin-downloader
```

2. **Cài đặt phụ thuộc**
```bash
pip install -r requirements.txt
```

3. **Cấu hình Cookie** (cần cho lần đầu)
```bash
# Cách 1: Lấy tự động (khuyến nghị)
python cookie_extractor.py

# Cách 2: Lấy thủ công
python get_cookies_manual.py
```

## 📦 Giới thiệu phiên bản

### V1.0 (DouYinCommand.py) - Ổn định
- ✅ **Đã kiểm chứng**: ổn định, đã thử nghiệm nhiều
- ✅ **Dễ dùng**: điều khiển qua file cấu hình
- ✅ **Đầy đủ tính năng**: hỗ trợ mọi loại nội dung
- ✅ **Tải đơn lẻ**: hoạt động bình thường cho video đơn
- ⚠️ **Cần cấu hình thủ công**: phải tự lấy và khai báo Cookie

### V2.0 (downloader.py) - Tăng cường
- 🚀 **Quản lý Cookie tự động**: tự lấy và làm mới Cookie
- 🚀 **Một lối vào duy nhất**: gom mọi tính năng vào một script
- 🚀 **Kiến trúc bất đồng bộ**: hiệu năng tốt, hỗ trợ tải song song
- 🚀 **Tự động thử lại**: tự lặp lại và phục hồi lỗi
- 🚀 **Tải bổ sung**: tránh tải trùng lặp
- ⚠️ **Tải video đơn**: hiện API trả về rỗng (lỗi đã biết)
- ✅ **Tải trang cá nhân**: hoạt động hoàn chỉnh

## 🎯 V1.0 Hướng dẫn

### Thiết lập file cấu hình

1. **Chỉnh file cấu hình**
```bash
cp config.example.yml config.yml
# Chỉnh sửa file config.yml
```

2. **Ví dụ cấu hình**
```yaml
# Liên kết tải
link:
  - https://v.douyin.com/xxxxx/                    # Video đơn
  - https://www.douyin.com/user/xxxxx              # Trang cá nhân
  - https://www.douyin.com/collection/xxxxx        # Bộ sưu tập

# Đường dẫn lưu
path: ./Downloaded/

# Cấu hình Cookie (bắt buộc)
cookies:
  msToken: YOUR_MS_TOKEN_HERE
  ttwid: YOUR_TTWID_HERE
  odin_tt: YOUR_ODIN_TT_HERE
  passport_csrf_token: YOUR_PASSPORT_CSRF_TOKEN_HERE
  sid_guard: YOUR_SID_GUARD_HERE

# Tuỳ chọn tải
music: True    # Tải nhạc
cover: True    # Tải ảnh bìa
avatar: True   # Tải avatar
json: True     # Lưu dữ liệu JSON

# Chế độ tải
mode:
  - post       # Tải tác phẩm đã đăng
  # - like     # Tải tác phẩm đã thích
  # - mix      # Tải bộ sưu tập

# Số lượng tải (0 là tất cả)
number:
  post: 0      # Số tác phẩm đã đăng
  like: 0      # Số tác phẩm đã thích
  allmix: 0    # Số bộ sưu tập
  mix: 0       # Số tác phẩm trong một bộ sưu tập

# Cài đặt khác
thread: 5      # Số luồng tải
database: True # Dùng cơ sở dữ liệu ghi nhận
```

### Chạy chương trình

```bash
# Dùng file cấu hình
python DouYinCommand.py

# Hoặc dùng tham số dòng lệnh
python DouYinCommand.py --cmd False
```

### Ví dụ sử dụng

```bash
# Tải video đơn
# Đặt link trong config.yml thành liên kết video
python DouYinCommand.py

# Tải trang cá nhân
# Đặt link trong config.yml thành liên kết trang cá nhân
python DouYinCommand.py

# Tải bộ sưu tập
# Đặt link trong config.yml thành liên kết bộ sưu tập
python DouYinCommand.py
```

## 🚀 V2.0 Hướng dẫn

### Dòng lệnh

```bash
# Tải video đơn (cần cấu hình Cookie trước)
python downloader.py -u "https://v.douyin.com/xxxxx/"

# Tải trang cá nhân (khuyến nghị)
python downloader.py -u "https://www.douyin.com/user/xxxxx"

# Tự lấy Cookie rồi tải
python downloader.py --auto-cookie -u "https://www.douyin.com/user/xxxxx"

# Chỉ định đường dẫn lưu
python downloader.py -u "link" --path "./my_videos/"

# Dùng file cấu hình
python downloader.py --config
```

### Dùng file cấu hình

1. **Tạo file cấu hình**
```bash
cp config.example.yml config_simple.yml
```

2. **Ví dụ cấu hình**
```yaml
# Liên kết tải
link:
  - https://www.douyin.com/user/xxxxx

# Đường dẫn lưu
path: ./Downloaded/

# Quản lý Cookie tự động
auto_cookie: true

# Tuỳ chọn tải
music: true
cover: true
avatar: true
json: true

# Chế độ tải
mode:
  - post

# Số lượng tải
number:
  post: 10

# Tải bổ sung
increase:
  post: false

# Cơ sở dữ liệu
database: true
```

3. **Chạy chương trình**
```bash
python downloader.py --config
```

### Tham số dòng lệnh

```bash
python downloader.py [tuỳ chọn] [link...]

tuỳ chọn:
  -u, --url URL          Liên kết tải
  -p, --path PATH        Đường dẫn lưu
  -c, --config           Dùng file cấu hình
  --auto-cookie          Tự lấy Cookie
  --cookies COOKIES      Nhập Cookie thủ công
  -h, --help            Hiển thị trợ giúp
```

## 🍪 Công cụ cấu hình Cookie

### 1. cookie_extractor.py - Lấy tự động

**Chức năng**: dùng Playwright mở trình duyệt và tự lấy Cookie

**Cách dùng**:
```bash
# Cài Playwright
pip install playwright
playwright install chromium

# Chạy lấy tự động
python cookie_extractor.py
```

**Đặc điểm**:
- ✅ Mở trình duyệt tự động
- ✅ Hỗ trợ quét mã đăng nhập
- ✅ Tự phát hiện trạng thái đăng nhập
- ✅ Tự lưu vào file cấu hình
- ✅ Hỗ trợ nhiều cách đăng nhập

**Các bước**:
1. Chạy `python cookie_extractor.py`
2. Chọn phương thức trích xuất (gợi ý chọn 1)
3. Đăng nhập trong cửa sổ trình duyệt
4. Chương trình tự trích và lưu Cookie

### 2. get_cookies_manual.py - Lấy thủ công

**Chức năng**: lấy Cookie qua công cụ DevTools của trình duyệt

**Cách dùng**:
```bash
python get_cookies_manual.py
```

**Đặc điểm**:
- ✅ Không cần cài Playwright
- ✅ Hướng dẫn thao tác chi tiết
- ✅ Hỗ trợ kiểm tra Cookie
- ✅ Tự lưu vào file cấu hình
- ✅ Hỗ trợ sao lưu và khôi phục

**Các bước**:
1. Chạy `python get_cookies_manual.py`
2. Chọn "Lấy Cookie mới"
3. Làm theo hướng dẫn trong trình duyệt để lấy Cookie
4. Dán nội dung Cookie
5. Chương trình tự phân tích và lưu

### Hướng dẫn lấy Cookie

#### Cách 1: DevTools của trình duyệt

1. Mở trình duyệt, truy cập [Douyin Web](https://www.douyin.com)
2. Đăng nhập tài khoản Douyin
3. Nhấn `F12` mở DevTools
4. Chuyển sang tab `Network`
5. Refresh trang, chọn bất kỳ request nào
6. Tìm trường `Cookie` trong request header
7. Sao chép các cookie quan trọng:
   - `msToken`
   - `ttwid`
   - `odin_tt`
   - `passport_csrf_token`
   - `sid_guard`

#### Cách 2: Dùng công cụ tự động

```bash
# Khuyến nghị dùng công cụ tự động
python cookie_extractor.py
```

## 📋 Các loại liên kết hỗ trợ

### 🎬 Nội dung video
- **Liên kết chia sẻ video đơn**: `https://v.douyin.com/xxxxx/`
- **Liên kết trực tiếp video đơn**: `https://www.douyin.com/video/xxxxx`
- **Tác phẩm bộ ảnh**: `https://www.douyin.com/note/xxxxx`

### 👤 Nội dung người dùng
- **Trang cá nhân**: `https://www.douyin.com/user/xxxxx`
  - Hỗ trợ tải tất cả tác phẩm đã đăng
  - Hỗ trợ tải tác phẩm đã thích (cần quyền)

### 📚 Nội dung bộ sưu tập
- **Bộ sưu tập người dùng**: `https://www.douyin.com/collection/xxxxx`
- **Bộ sưu tập nhạc**: `https://www.douyin.com/music/xxxxx`

### 🔴 Nội dung livestream
- **Phòng livestream**: `https://live.douyin.com/xxxxx`
