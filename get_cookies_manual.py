#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Trợ lý lấy Cookie Douyin (thủ công)
Không cần cài đặt Playwright, lấy thủ công qua công cụ nhà phát triển trình duyệt
"""

import json
import yaml
import os
import sys
from datetime import datetime
from typing import Dict

def print_instructions():
    """In hướng dẫn chi tiết để lấy Cookie"""
    print("\n" + "="*60)
    print("Hướng dẫn lấy Cookie Douyin")
    print("="*60)
    print("\n📝 Các bước thực hiện：\n")
    print("1. Mở trình duyệt (khuyên dùng Chrome/Edge)")
    print("2. Truy cập phiên bản web của Douyin：https://www.douyin.com")
    print("3. Đăng nhập tài khoản của bạn (quét mã/số điện thoại/đăng nhập bên thứ ba)")
    print("4. Sau khi đăng nhập thành công, nhấn F12 để mở công cụ nhà phát triển")
    print("5. Chuyển sang tab Network (Mạng)")
    print("6. Làm mới trang (F5)")
    print("7. Trong danh sách yêu cầu, tìm bất kỳ yêu cầu nào đến douyin.com")
    print("8. Nhấp vào yêu cầu đó, tìm Request Headers (Tiêu đề yêu cầu) ở bên phải")
    print("9. Tìm trường Cookie, sao chép toàn bộ giá trị Cookie")
    print("\n" + "="*60)
    
    print("\n⚠️ Lưu ý quan trọng：")
    print("• Cookie chứa thông tin đăng nhập của bạn, vui lòng không chia sẻ cho người khác")
    print("• Cookie thường có hiệu lực từ 7-30 ngày, cần lấy lại khi hết hạn")
    print("• Nên cập nhật Cookie định kỳ để đảm bảo tỷ lệ tải xuống thành công")
    print("\n" + "="*60)

def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    """Phân tích chuỗi Cookie thành dictionary"""
    cookies = {}
    
    # Làm sạch đầu vào
    cookie_str = cookie_str.strip()
    if cookie_str.startswith('"') and cookie_str.endswith('"'):
        cookie_str = cookie_str[1:-1]
    
    # Chia tách Cookie
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    
    return cookies

def validate_cookies(cookies: Dict[str, str]) -> bool:
    """Xác thực Cookie có chứa các trường cần thiết không"""
    # Các trường Cookie cần thiết
    required_fields = ['ttwid']  # Ít nhất cần ttwid
    important_fields = ['sessionid', 'sessionid_ss', 'passport_csrf_token', 'msToken']
    
    # Kiểm tra các trường cần thiết
    missing_required = []
    for field in required_fields:
        if field not in cookies:
            missing_required.append(field)
    
    if missing_required:
        print(f"\n❌ Thiếu các trường Cookie cần thiết: {', '.join(missing_required)}")
        return False
    
    # Kiểm tra các trường quan trọng
    missing_important = []
    for field in important_fields:
        if field not in cookies:
            missing_important.append(field)
    
    if missing_important:
        print(f"\n⚠️ Thiếu một số trường Cookie quan trọng: {', '.join(missing_important)}")
        print("Có thể ảnh hưởng đến một số chức năng, nhưng có thể thử sử dụng")
    
    return True

def save_cookies(cookies: Dict[str, str], config_path: str = "config_simple.yml"):
    """Lưu Cookie vào file cấu hình"""
    # Đọc cấu hình hiện có
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    # Cập nhật cấu hình Cookie
    config['cookies'] = cookies
    
    # Lưu cấu hình
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"\n✅ Cookie đã lưu vào {config_path}")
    
    # Đồng thời lưu chuỗi Cookie đầy đủ
    cookie_string = '; '.join([f'{k}={v}' for k, v in cookies.items()])
    with open('cookies.txt', 'w', encoding='utf-8') as f:
        f.write(cookie_string)
    print(f"✅ Chuỗi Cookie đầy đủ đã lưu vào cookies.txt")
    
    # Lưu bản sao lưu có dấu thời gian
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'cookies_backup_{timestamp}.json'
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump({
            'cookies': cookies,
            'cookie_string': cookie_string,
            'timestamp': timestamp,
            'note': 'Sao lưu Cookie Douyin'
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ Sao lưu Cookie đã lưu vào {backup_file}")

def load_existing_cookies(config_path: str = "config_simple.yml") -> Dict[str, str]:
    """Tải Cookie hiện có"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            return config.get('cookies', {})
    return {}

def main():
    """Hàm chính"""
    print("\n🍪 Trợ lý cấu hình Cookie Douyin")
    print("-" * 40)
    
    # Hiển thị tùy chọn
    print("\nVui lòng chọn thao tác：")
    print("1. Lấy Cookie mới")
    print("2. Xem Cookie hiện tại")
    print("3. Xác thực tính hợp lệ của Cookie")
    print("4. Hiển thị hướng dẫn")
    
    choice = input("\nVui lòng nhập lựa chọn (1-4): ").strip()
    
    if choice == '1':
        # Lấy Cookie mới
        print_instructions()
        
        print("\nVui lòng dán nội dung Cookie bạn đã sao chép：")
        print("（Gợi ý: Dán xong nhấn Enter để xác nhận）")
        print("-" * 40)
        
        # Hỗ trợ nhập nhiều dòng
        lines = []
        while True:
            line = input()
            if line:
                lines.append(line)
            else:
                break
        
        cookie_str = ' '.join(lines)
        
        if not cookie_str:
            print("\n❌ Chưa nhập Cookie")
            return
        
        # Phân tích Cookie
        cookies = parse_cookie_string(cookie_str)
        
        if not cookies:
            print("\n❌ Phân tích Cookie thất bại, vui lòng kiểm tra định dạng")
            return
        
        print(f"\n✅ Đã phân tích thành công {len(cookies)} trường Cookie")
        
        # Hiển thị Cookie quan trọng
        print("\n📋 Các Cookie quan trọng đã phân tích：")
        important_fields = ['sessionid', 'sessionid_ss', 'ttwid', 'passport_csrf_token', 'msToken']
        for field in important_fields:
            if field in cookies:
                value = cookies[field]
                display_value = f"{value[:20]}..." if len(value) > 20 else value
                print(f"  • {field}: {display_value}")
        
        # Xác thực Cookie
        if validate_cookies(cookies):
            # Hỏi có muốn lưu không
            save_choice = input("\nCó muốn lưu Cookie vào file cấu hình không？(y/n): ").strip().lower()
            if save_choice == 'y':
                save_cookies(cookies)
                print("\n🎉 Cấu hình hoàn tất! Bạn có thể chạy trình tải xuống ngay bây giờ：")
                print("python3 downloader.py -c config_simple.yml")
            else:
                print("\nĐã hủy lưu")
        
    elif choice == '2':
        # Xem Cookie hiện tại
        cookies = load_existing_cookies()
        if cookies:
            print("\n📋 Cookie hiện tại đã cấu hình：")
            for key, value in cookies.items():
                display_value = f"{value[:30]}..." if len(value) > 30 else value
                print(f"  • {key}: {display_value}")
        else:
            print("\n❌ Không tìm thấy Cookie đã cấu hình")
    
    elif choice == '3':
        # Xác thực Cookie
        cookies = load_existing_cookies()
        if cookies:
            print("\n🔍 Đang xác thực Cookie...")
            if validate_cookies(cookies):
                print("✅ Định dạng Cookie chính xác")
                print("\nLưu ý: Đây chỉ là xác thực định dạng, tính hợp lệ thực tế cần kiểm tra chức năng tải xuống")
        else:
            print("\n❌ Không tìm thấy Cookie đã cấu hình")
    
    elif choice == '4':
        # Hiển thị hướng dẫn
        print_instructions()
    
    else:
        print("\n❌ Lựa chọn không hợp lệ")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Đã thoát")
    except Exception as e:
        print(f"\n❌ Xảy ra lỗi: {e}")
        import traceback
        traceback.print_exc()