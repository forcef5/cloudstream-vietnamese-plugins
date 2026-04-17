#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fshare API Login & Getlink Tool
Dựa trên cách addon plugin.video.vietmediaF đăng nhập và getlink
Sử dụng API trực tiếp của Fshare
"""

import argparse
import json
import requests
import time
import sys
import re
import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

# Cấu hình encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Constants từ addon
LOGIN_API = 'https://api.fshare.vn/api/user/login'
PROFILE_API = 'https://api.fshare.vn/api/user/get'
DOWNLOAD_API = 'https://api.fshare.vn/api/session/download'
FOLDER_API = 'https://api.fshare.vn/api/fileops/getFolderList'
UPLOAD_API = 'https://api.fshare.vn/api/session/upload'
USER_AGENT = 'kodivietmediaf-K58W6U'
APP_KEY = 'dMnqMMZMUnN5YpvKENaEhdQQ5jxDqddt'

# File để lưu token và session ID
SESSION_FILE = 'fshare_session.json'
DEFAULT_EMAIL = "rimvak@vuk.edu.vn"
DEFAULT_PASSWORD = "tyfsPRVZIx545QJfIMO_1762701271"
DEFAULT_DOMAIN = "@fshare.vn"


def save_session(email: str, token: str, session_id: str, account_id: str = None) -> bool:
    """
    Lưu token và session ID vào file
    
    Args:
        email: Email đăng nhập
        token: Token từ FShare
        session_id: Session ID từ FShare
        account_id: Account ID (optional)
    
    Returns:
        True nếu lưu thành công, False nếu có lỗi
    """
    try:
        session_data = {
            "email": email,
            "token": token,
            "session_id": session_id,
            "account_id": account_id,
            "saved_at": time.time(),
            "saved_at_str": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
        
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"⚠️ Lỗi khi lưu session: {str(e)}")
        return False


def load_session() -> Optional[Dict[str, Any]]:
    """
    Đọc token và session ID từ file
    
    Returns:
        Dict chứa session data hoặc None nếu không tìm thấy/không hợp lệ
    """
    if not os.path.exists(SESSION_FILE):
        return None
    
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Kiểm tra các trường bắt buộc
        if not all(key in session_data for key in ['email', 'token', 'session_id']):
            return None
        
        return session_data
    except Exception as e:
        print(f"⚠️ Lỗi khi đọc session: {str(e)}")
        return None


def timestamp_to_date(timestamp_str: str) -> str:
    """
    Chuyển đổi timestamp sang định dạng dd/mm/yyyy
    
    Args:
        timestamp_str: Timestamp dạng string hoặc số
    
    Returns:
        Chuỗi ngày tháng định dạng dd/mm/yyyy hoặc "N/A" nếu lỗi
    """
    try:
        # Chuyển string sang int nếu cần
        if isinstance(timestamp_str, str):
            timestamp = int(timestamp_str)
        else:
            timestamp = timestamp_str
        
        # Kiểm tra timestamp hợp lệ (không quá lớn)
        if timestamp > 2147483647:  # Timestamp quá lớn, có thể là timestamp milliseconds
            timestamp = timestamp // 1000
        
        # Chuyển đổi sang datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d/%m/%Y")
    except (ValueError, OSError, OverflowError):
        return "N/A"


def print_progress_bar(current: int, total: int, bar_length: int = 50, 
                       show_speed: bool = True, start_time: float = None) -> None:
    """
    In progress bar đẹp lên cùng một dòng
    
    Args:
        current: Giá trị hiện tại (bytes đã upload)
        total: Tổng giá trị (tổng bytes của file)
        bar_length: Độ dài thanh progress bar (mặc định: 50)
        show_speed: Có hiển thị tốc độ upload không (mặc định: True)
        start_time: Thời gian bắt đầu upload (để tính speed và ETA)
    """
    if total == 0:
        return
    
    percent = (current / total) * 100
    filled_length = int(bar_length * current // total)
    
    # Tạo thanh progress bar
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    # Format số liệu
    current_mb = current / (1024 ** 2)
    total_mb = total / (1024 ** 2)
    
    # Tính tốc độ và ETA nếu có
    speed_str = ""
    eta_str = ""
    if show_speed and start_time:
        elapsed = time.time() - start_time
        if elapsed > 0:
            speed = current / elapsed  # bytes per second
            speed_mb = speed / (1024 ** 2)
            speed_str = f" | {speed_mb:.2f} MB/s"
            
            # Tính ETA
            remaining = total - current
            if speed > 0:
                eta_seconds = int(remaining / speed)
                eta_minutes = eta_seconds // 60
                eta_secs = eta_seconds % 60
                eta_str = f" | ETA: {eta_minutes:02d}:{eta_secs:02d}"
    
    # In progress bar (dùng \r để overwrite dòng cũ)
    print(f"\r📤 [{bar}] {percent:.1f}% | {current_mb:.2f}/{total_mb:.2f} MB{speed_str}{eta_str}", 
          end='', flush=True)


class FshareAPI:
    """Class để đăng nhập và getlink Fshare sử dụng API (giống addon)"""
    
    def __init__(self, email: str, password: str, domain: str = '@fshare.vn'):
        """
        Khởi tạo FshareAPI
        
        Args:
            email: Email đăng nhập (có thể có hoặc không có domain)
            password: Mật khẩu đăng nhập
            domain: Domain mặc định nếu email không có @ (mặc định: @fshare.vn)
        """
        # Xử lý email - thêm domain nếu chưa có @
        if '@' not in email:
            self.email = email.strip() + domain
        else:
            self.email = email.strip()
        self.password = password.strip()
        
        self.token = None
        self.session_id = None
        self.is_logged_in = False
        self.account_id = None  # ID tài khoản Fshare
        self._verifying_session = False  # Flag để tránh recursive call
        
        # Tạo session với headers mặc định (giống addon)
        self.session = requests.Session()
        # Không set Content-Type mặc định để tránh lỗi 405
        
        # Tắt verify SSL để tránh lỗi certificate (giống addon)
        self.session.verify = False
        
        # Tắt warning về SSL
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def set_session(self, token: str, session_id: str, account_id: str = None) -> None:
        """
        Set token và session_id trực tiếp (không cần login)
        
        Args:
            token: Token từ FShare
            session_id: Session ID từ FShare
            account_id: Account ID (optional)
        """
        self.token = token
        self.session_id = session_id
        self.is_logged_in = True
        if account_id:
            self.account_id = account_id
    
    def verify_session(self, silent: bool = False) -> bool:
        """
        Kiểm tra token và session_id còn hợp lệ không
        Gọi API trực tiếp để tránh vòng lặp đệ quy với get_user_info()
        
        Args:
            silent: Nếu True, không in thông báo (mặc định: False)
        
        Returns:
            True nếu còn hợp lệ, False nếu không
        """
        if not self.is_logged_in or not self.token or not self.session_id:
            return False
        
        # Tránh recursive call
        if self._verifying_session:
            return False
        
        self._verifying_session = True
        
        try:
            # Gọi API trực tiếp để kiểm tra (không thông qua get_user_info để tránh vòng lặp)
            headers = {
                'useragent': USER_AGENT,
                'Cookie': f'session_id={self.session_id}'
            }
            
            response = self.session.get(PROFILE_API, headers=headers, timeout=10)
            
            # Nếu status code là 200 thì session còn hợp lệ
            is_valid = response.status_code == 200
            return is_valid
        except:
            return False
        finally:
            self._verifying_session = False
    
    def auto_login(self, use_saved_session: bool = True) -> Dict[str, Any]:
        """
        Tự động đăng nhập: thử dùng session đã lưu trước, nếu không hợp lệ thì login lại
        
        Args:
            use_saved_session: Có sử dụng session đã lưu không (mặc định: True)
        
        Returns:
            Dict chứa status và thông tin đăng nhập
        """
        # Thử load session đã lưu
        if use_saved_session:
            saved_session = load_session()
            
            if saved_session:
                print(f"\n{'='*60}")
                print(f"📥 Tìm thấy session đã lưu cho email: {saved_session.get('email')}")
                if saved_session.get('saved_at_str'):
                    print(f"📅 Lưu lúc: {saved_session.get('saved_at_str')}")
                print(f"{'='*60}\n")
                
                # Set session từ file đã lưu
                self.set_session(
                    token=saved_session.get('token'),
                    session_id=saved_session.get('session_id'),
                    account_id=saved_session.get('account_id')
                )
                
                # Kiểm tra session còn hợp lệ không
                print("🔍 Đang kiểm tra token và session ID...")
                if self.verify_session():
                    print("✅ Token và session ID còn hợp lệ!")
                    return {
                        "status": "success",
                        "message": "Sử dụng session đã lưu thành công",
                        "token": self.token,
                        "session_id": self.session_id,
                        "account_id": self.account_id,
                        "from_saved": True
                    }
                else:
                    print("⚠️ Token và session ID không còn hợp lệ, sẽ đăng nhập lại...")
        
        # Nếu không có session hoặc session không hợp lệ, đăng nhập lại
        print(f"\n{'='*60}")
        print("📤 Đang đăng nhập mới...")
        print(f"{'='*60}\n")
        
        login_result = self.login()
        
        if login_result.get("status") == "success":
            login_result["from_saved"] = False
        
        return login_result
    
    def ensure_logged_in(self) -> bool:
        """
        Đảm bảo đã đăng nhập: tự động login lại nếu token hết hạn
        
        Returns:
            True nếu đã đăng nhập, False nếu không thể đăng nhập
        """
        if not self.is_logged_in or not self.token or not self.session_id:
            # Chưa đăng nhập, thử auto_login
            result = self.auto_login(use_saved_session=True)
            return result.get("status") == "success"
        
        # Đã có session, kiểm tra còn hợp lệ không (silent mode để tránh spam)
        if not self.verify_session(silent=True):
            # Session hết hạn, đăng nhập lại (chỉ in 1 lần)
            if not getattr(self, '_relogging', False):
                self._relogging = True
                print("⚠️ Session đã hết hạn, đang đăng nhập lại...")
                result = self.login()
                self._relogging = False
                return result.get("status") == "success"
            else:
                # Đang trong quá trình đăng nhập lại rồi, không gọi lại
                return False
        
        return True
    
    def login(self) -> Dict[str, Any]:
        """
        Đăng nhập vào Fshare sử dụng API
        
        Returns:
            Dict chứa status, message, token và session_id
        """
        try:
            print(f"\n{'='*60}")
            print(f"Đang đăng nhập với email: {self.email}")
            print(f"{'='*60}\n")
            
            # Chuẩn bị payload (giống addon - string JSON, nhưng dùng json.dumps để đảm bảo hợp lệ)
            payload = json.dumps({
                "app_key": APP_KEY,
                "user_email": self.email,
                "password": self.password
            })
            
            # Headers giống hệt addon (không có Content-Type)
            headers = {
                'cache-control': "no-cache",
                'User-Agent': USER_AGENT
            }
            
            print("📤 Đang gửi yêu cầu đăng nhập...")
            
            # Gửi POST request
            response = self.session.post(
                LOGIN_API,
                data=payload,
                headers=headers,
                timeout=30
            )
            
            # Parse response
            try:
                jStr = json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": f"Response không phải JSON hợp lệ. Status: {response.status_code}, Content: {response.text[:200]}"
                }
            
            msg = jStr.get('msg', '')
            print(f"📥 Response: {msg}")
            
            # Xử lý các mã lỗi (giống addon)
            if response.status_code == 406:
                return {
                    "status": "error",
                    "message": "Account chưa được kích hoạt. Bạn vào e-mail rồi kích hoạt tài khoản"
                }
            
            if response.status_code == 409:
                return {
                    "status": "error",
                    "message": "Tài khoản đã bị khoá login"
                }
            
            if response.status_code == 410:
                return {
                    "status": "error",
                    "message": "Tài khoản đã bị khoá"
                }
            
            if response.status_code == 424:
                return {
                    "status": "error",
                    "message": f"Tài khoản đã bị khoá do nhập sai mật khẩu quá 3 lần. Kiểm tra thông tin và đợi 10 phút sau thử lại\nE-mail: {self.email}\nPassword: {self.password}"
                }
            
            if response.status_code == 403:
                return {
                    "status": "error",
                    "message": "HTTP 403 Forbidden. Có thể cần xác thực thêm."
                }
            
            if response.status_code == 405:
                return {
                    "status": "error",
                    "message": f"Có thể đã nhập sai email hoặc mật khẩu.\nEmail: {self.email}\nMật khẩu: {self.password}"
                }
            
            # Kiểm tra đăng nhập thành công
            if response.status_code == 200:
                self.token = jStr.get('token')
                self.session_id = jStr.get('session_id')
                
                if not self.token or not self.session_id:
                    return {
                        "status": "error",
                        "message": "Đăng nhập thành công nhưng không nhận được token hoặc session_id"
                    }
                
                self.is_logged_in = True
                
                # Lưu account_id nếu có trong response
                if 'id' in jStr:
                    self.account_id = str(jStr.get('id'))
                elif 'user_id' in jStr:
                    self.account_id = str(jStr.get('user_id'))
                
                print("✅ Đăng nhập thành công!")
                print(f"🔑 Token: {self.token}")
                print(f"🆔 Session ID: {self.session_id}")
                if self.account_id:
                    print(f"🆔 Account ID: {self.account_id}")
                
                # Tự động lưu token và session ID vào file
                if save_session(self.email, self.token, self.session_id, self.account_id):
                    print(f"💾 Đã lưu token và session ID vào file: {SESSION_FILE}")
                
                return {
                    "status": "success",
                    "message": msg or "Đăng nhập thành công",
                    "token": self.token,
                    "session_id": self.session_id,
                    "account_id": self.account_id
                }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {msg or response.text[:200]}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi đăng nhập. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi đăng nhập: {str(e)}"
            }
    
    def get_user_info(self) -> Dict[str, Any]:
        """
        Lấy thông tin tài khoản (tự động login lại nếu token hết hạn)
        
        Returns:
            Dict chứa thông tin tài khoản
        """
        # Đảm bảo đã đăng nhập
        if not self.ensure_logged_in():
            return {
                "status": "error",
                "message": "Không thể đăng nhập. Vui lòng kiểm tra lại email và password."
            }
        
        try:
            headers = {
                'useragent': USER_AGENT,
                'Cookie': f'session_id={self.session_id}'
            }
            
            response = self.session.get(PROFILE_API, headers=headers, timeout=30)
            
            # Nếu token hết hạn, thử login lại và retry
            if response.status_code in [201, 401, 400]:
                print("⚠️ Token đã hết hạn, đang đăng nhập lại...")
                login_result = self.login()
                if login_result.get("status") == "success":
                    # Retry với token mới
                    headers = {
                        'useragent': USER_AGENT,
                        'Cookie': f'session_id={self.session_id}'
                    }
                    response = self.session.get(PROFILE_API, headers=headers, timeout=30)
            
            if response.status_code == 200:
                jstr = json.loads(response.content)
                
                expiredDate = jstr.get("expire_vip", "N/A")
                expiredDate_formatted = timestamp_to_date(expiredDate) if expiredDate != "N/A" else "N/A"
                point = jstr.get('totalpoints', '0')
                mail = jstr.get('email', 'N/A')
                acc_type = jstr.get('account_type', 'N/A')
                webspace = float(jstr.get('webspace', 0)) / float(1073741824)
                webspace_used = '{0:.2f}'.format(float(jstr.get('webspace_used', 0)) / float(1073741824))
                
                # Lấy ID tài khoản (có thể từ cookies hoặc response)
                account_id = jstr.get('id') or jstr.get('user_id') or jstr.get('account_id')
                
                # Nếu không có trong response, thử lấy từ cookies
                if not account_id:
                    cookies_dict = self.session.cookies.get_dict()
                    # Thử lấy từ cookie _fsgaid hoặc _ftitfsi
                    account_id = cookies_dict.get('_fsgaid') or cookies_dict.get('_ftitfsi')
                
                return {
                    "status": "success",
                    "email": mail,
                    "account_type": acc_type,
                    "expire_vip": expiredDate,
                    "expire_vip_formatted": expiredDate_formatted,
                    "totalpoints": point,
                    "webspace_gb": f"{webspace:.2f}",
                    "webspace_used_gb": webspace_used,
                    "account_id": account_id
                }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {response.text[:200]}"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi khi lấy thông tin tài khoản: {str(e)}"
            }
    
    def get_download_link(self, fshare_url: str, password: str = "") -> Dict[str, Any]:
        """
        Lấy link download từ Fshare (tự động login lại nếu token hết hạn)
        
        Args:
            fshare_url: URL Fshare (ví dụ: https://www.fshare.vn/file/ABC123)
            password: Mật khẩu file nếu có (mặc định: "")
        
        Returns:
            Dict chứa status và download link
        """
        # Đảm bảo đã đăng nhập
        if not self.ensure_logged_in():
            return {
                "status": "error",
                "message": "Không thể đăng nhập. Vui lòng kiểm tra lại email và password."
            }
        
        try:
            print(f"\n{'='*60}")
            print(f"Đang lấy link cho: {fshare_url}")
            print(f"{'='*60}\n")
            
            # Thêm share parameter (giống addon)
            modified_link = fshare_url
            if "?" not in modified_link:
                modified_link = modified_link + "?share=8805984"
            else:
                modified_link = modified_link + "&share=8805984"
            
            # Chuẩn bị payload (giống addon - string JSON)
            payload = json.dumps({
                "zipflag": 0,
                "url": modified_link,
                "password": password,
                "token": self.token
            })
            
            headers = {
                'Content-Type': 'application/json',  # API download cần Content-Type
                'User-Agent': USER_AGENT,
                'Cookie': f'session_id={self.session_id}'
            }
            
            print("📤 Đang gửi yêu cầu getlink...")
            
            # Gửi POST request
            response = self.session.post(
                DOWNLOAD_API,
                headers=headers,
                data=payload,
                timeout=60
            )
            
            # Parse response
            try:
                jstr = json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": f"Response không phải JSON hợp lệ. Status: {response.status_code}, Content: {response.text[:200]}"
                }
            
            # Xử lý các mã lỗi (giống addon)
            if response.status_code == 404:
                return {
                    "status": "error",
                    "message": "Link này không tồn tại hoặc bị xoá"
                }
            
            # Nếu token hết hạn, tự động login lại và retry
            if response.status_code == 201:
                print("⚠️ Token đã hết hạn, đang đăng nhập lại...")
                login_result = self.login()
                if login_result.get("status") == "success":
                    # Retry với token mới
                    payload = json.dumps({
                        "zipflag": 0,
                        "url": modified_link,
                        "password": password,
                        "token": self.token
                    })
                    headers = {
                        'Content-Type': 'application/json',
                        'User-Agent': USER_AGENT,
                        'Cookie': f'session_id={self.session_id}'
                    }
                    response = self.session.post(
                        DOWNLOAD_API,
                        headers=headers,
                        data=payload,
                        timeout=60
                    )
                    try:
                        jstr = json.loads(response.content)
                    except json.JSONDecodeError:
                        return {
                            "status": "error",
                            "message": f"Response không phải JSON hợp lệ sau khi login lại. Status: {response.status_code}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": "Tài khoản chưa đăng nhập và không thể đăng nhập lại"
                    }
            
            if response.status_code == 471:
                return {
                    "status": "error",
                    "message": "Phiên tải quá nhiều. Vào fshare.vn/Thông tin tài khoản/Bảo mật/Xoá phiên tải và phiên đăng nhập"
                }
            
            if response.status_code == 200:
                # Kiểm tra xem có yêu cầu password không
                if jstr.get("code") == 123:
                    return {
                        "status": "password_required",
                        "message": "File này yêu cầu mật khẩu",
                        "code": 123
                    }
                
                # Lấy link download
                link_download = jstr.get("location")
                
                if not link_download:
                    return {
                        "status": "error",
                        "message": "Không tìm thấy link download trong response",
                        "response": jstr
                    }
                
                print("✅ Đã lấy link thành công!")
                print(f"🔗 Download URL: {link_download}")
                
                return {
                    "status": "success",
                    "download_url": link_download,
                    "response": jstr
                }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {jstr.get('msg', response.text[:200])}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi lấy link. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi lấy link: {str(e)}"
            }
    
    def get_folder_list(self, folder_url: str, page_index: int = 0, limit: int = 10000) -> Dict[str, Any]:
        """
        Lấy danh sách file và folder trong một folder Fshare (giống addon)
        
        Args:
            folder_url: URL folder Fshare (ví dụ: https://www.fshare.vn/folder/ABC123)
            page_index: Số trang (bắt đầu từ 0, mặc định: 0)
            limit: Số item mỗi trang (mặc định: 10000)
        
        Returns:
            Dict chứa status và danh sách items
        """
        if not self.is_logged_in or not self.token or not self.session_id:
            return {
                "status": "error",
                "message": "Chưa đăng nhập. Vui lòng gọi login() trước."
            }
        
        try:
            print(f"\n{'='*60}")
            print(f"Đang lấy danh sách folder: {folder_url}")
            print(f"Trang: {page_index + 1}")
            print(f"{'='*60}\n")
            
            # Kiểm tra URL hợp lệ
            if 'fshare.vn' not in folder_url or 'folder' not in folder_url:
                return {
                    "status": "error",
                    "message": "URL không hợp lệ! Phải là link folder Fshare (ví dụ: https://www.fshare.vn/folder/ABC123)"
                }
            
            # Chuẩn bị payload (giống addon)
            payload = json.dumps({
                "token": self.token,
                "url": folder_url,
                "dirOnly": 0,  # 0 = lấy cả file và folder
                "pageIndex": page_index,
                "limit": limit
            })
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': USER_AGENT,
                'Cookie': f'session_id={self.session_id}'
            }
            
            print("📤 Đang gửi yêu cầu lấy danh sách folder...")
            
            # Gửi POST request
            response = self.session.post(
                FOLDER_API,
                headers=headers,
                data=payload,
                timeout=60
            )
            
            # Parse response
            try:
                f_items = json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": f"Response không phải JSON hợp lệ. Status: {response.status_code}, Content: {response.text[:200]}"
                }
            
            # Xử lý các mã lỗi
            if response.status_code == 404 or (isinstance(f_items, str) and "[]" in f_items):
                return {
                    "status": "error",
                    "message": "Thư mục không tồn tại hoặc đã bị xóa."
                }
            
            if response.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {response.text[:200]}"
                }
            
            # Kiểm tra response rỗng
            if not f_items or len(f_items) == 0:
                return {
                    "status": "success",
                    "items": [],
                    "has_more": False,
                    "message": "Folder trống"
                }
            
            # Xử lý danh sách items
            items = []
            for f_item in f_items:
                name = f_item.get("name", "Unknown")
                linkcode = f_item.get("linkcode", "")
                
                # Xử lý size - chuyển sang int nếu là string
                size_raw = f_item.get("size", 0)
                try:
                    size = int(size_raw) if size_raw else 0
                except (ValueError, TypeError):
                    size = 0
                
                # Xử lý type - có thể là string "0" hoặc số 0
                item_type_raw = f_item.get("type", "1")
                item_type = str(item_type_raw)  # Chuyển sang string để so sánh
                
                # Tạo URL đầy đủ
                if item_type == "0" or item_type == 0:
                    item_url = f"https://www.fshare.vn/folder/{linkcode}"
                    is_folder = True
                else:
                    item_url = f"https://www.fshare.vn/file/{linkcode}"
                    is_folder = False
                
                # Format size
                if size > 0:
                    size_gb = size / (1024 ** 3)
                    size_str = f"{size_gb:.2f} GB" if size_gb >= 1 else f"{size / (1024 ** 2):.2f} MB"
                else:
                    size_str = "0 B"
                
                items.append({
                    "name": name,
                    "linkcode": linkcode,
                    "url": item_url,
                    "size": size,
                    "size_str": size_str,
                    "type": item_type,
                    "is_folder": is_folder
                })
            
            # Kiểm tra có trang tiếp theo không
            has_more = len(f_items) >= limit
            
            print(f"✅ Đã lấy được {len(items)} items")
            if has_more:
                print(f"📄 Còn trang tiếp theo (trang {page_index + 2})")
            
            return {
                "status": "success",
                "items": items,
                "has_more": has_more,
                "page_index": page_index,
                "total_items": len(items)
            }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi lấy danh sách folder. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi lấy danh sách folder: {str(e)}"
            }
    
    def get_all_files_from_folder(self, folder_url: str, recursive: bool = False, max_depth: int = 100) -> Dict[str, Any]:
        """
        Lấy tất cả file từ folder (có thể đệ quy vào các folder con)
        
        Args:
            folder_url: URL folder Fshare
            recursive: Có đệ quy vào folder con không (mặc định: False)
            max_depth: Độ sâu tối đa khi đệ quy (mặc định: 100 - đủ cho hầu hết trường hợp)
        
        Returns:
            Dict chứa danh sách tất cả file
        """
        all_files = []
        all_folders = []
        page_index = 0
        
        print(f"\n{'='*60}")
        print(f"Đang lấy tất cả file từ folder: {folder_url}")
        if recursive:
            print(f"Chế độ đệ quy: Bật (max_depth: {max_depth})")
        print(f"{'='*60}\n")
        
        def process_folder(url: str, depth: int = 0):
            """Hàm đệ quy để xử lý folder"""
            if depth > max_depth:
                print(f"⚠️ Đã đạt độ sâu tối đa ({max_depth}), dừng đệ quy")
                return
            
            current_page = 0
            
            while True:
                # Sử dụng limit=10000 để lấy nhiều items nhất có thể mỗi trang
                result = self.get_folder_list(url, page_index=current_page, limit=10000)
                
                if result["status"] != "success":
                    print(f"❌ Lỗi khi lấy danh sách folder: {result.get('message', 'Unknown error')}")
                    break
                
                items = result.get("items", [])
                
                for item in items:
                    if item["is_folder"]:
                        all_folders.append({
                            **item,
                            "depth": depth,
                            "parent_url": url
                        })
                        
                        # Nếu đệ quy, xử lý folder con
                        if recursive:
                            print(f"📁 Vào folder con: {item['name']} (depth: {depth + 1})")
                            process_folder(item["url"], depth + 1)
                    else:
                        all_files.append({
                            **item,
                            "depth": depth,
                            "parent_url": url
                        })
                
                # Kiểm tra có trang tiếp theo không
                if not result.get("has_more", False):
                    break
                
                current_page += 1
                print(f"📄 Đang lấy trang {current_page + 1}...")
        
        # Bắt đầu xử lý
        process_folder(folder_url)
        
        print(f"\n✅ Hoàn tất!")
        print(f"📁 Tổng số folder: {len(all_folders)}")
        print(f"📄 Tổng số file: {len(all_files)}")
        
        return {
            "status": "success",
            "files": all_files,
            "folders": all_folders,
            "total_files": len(all_files),
            "total_folders": len(all_folders)
        }
    
    def get_download_links_from_folder(self, folder_url: str, recursive: bool = False, 
                                       max_depth: int = 100, include_folders: bool = False) -> Dict[str, Any]:
        """
        Lấy download link cho tất cả file trong folder
        
        Args:
            folder_url: URL folder Fshare
            recursive: Có đệ quy vào folder con không (mặc định: False)
            max_depth: Độ sâu tối đa khi đệ quy (mặc định: 100)
            include_folders: Có bao gồm folder trong kết quả không (mặc định: False)
        
        Returns:
            Dict chứa danh sách file với download link
        """
        print(f"\n{'='*60}")
        print(f"Đang lấy download link cho tất cả file trong folder")
        print(f"{'='*60}\n")
        
        # Lấy tất cả file
        result = self.get_all_files_from_folder(folder_url, recursive=recursive, max_depth=max_depth)
        
        if result["status"] != "success":
            return result
        
        files = result.get("files", [])
        
        if len(files) == 0:
            return {
                "status": "success",
                "message": "Không có file nào trong folder",
                "files_with_links": []
            }
        
        print(f"\n📥 Đang lấy download link cho {len(files)} file...")
        
        files_with_links = []
        success_count = 0
        error_count = 0
        
        for idx, file_item in enumerate(files, 1):
            print(f"\n[{idx}/{len(files)}] Đang xử lý: {file_item['name']}")
            
            # Lấy download link
            link_result = self.get_download_link(file_item["url"])
            
            if link_result["status"] == "success":
                files_with_links.append({
                    **file_item,
                    "download_url": link_result.get("download_url"),
                    "getlink_status": "success"
                })
                success_count += 1
                print(f"✅ Thành công!")
            else:
                files_with_links.append({
                    **file_item,
                    "download_url": None,
                    "getlink_status": "error",
                    "error_message": link_result.get("message", "Unknown error")
                })
                error_count += 1
                print(f"❌ Lỗi: {link_result.get('message', 'Unknown error')}")
            
            # Delay nhỏ để tránh rate limit
            if idx < len(files):
                time.sleep(0.5)
        
        print(f"\n{'='*60}")
        print(f"✅ Hoàn tất!")
        print(f"✅ Thành công: {success_count}/{len(files)}")
        print(f"❌ Lỗi: {error_count}/{len(files)}")
        print(f"{'='*60}\n")
        
        return {
            "status": "success",
            "files_with_links": files_with_links,
            "total_files": len(files),
            "success_count": success_count,
            "error_count": error_count
        }
    
    def get_otp_from_api(self, account_id: str) -> Dict[str, Any]:
        """
        Lấy OTP từ API https://otp.fspoint.shop/otp?id={account_id}
        
        Args:
            account_id: ID tài khoản Fshare
        
        Returns:
            Dict chứa status và OTP code
        """
        try:
            otp_url = f"https://otp.fspoint.shop/otp?id={account_id}"
            
            headers = {
                'User-Agent': USER_AGENT,
                'Accept': 'application/json, text/plain, */*'
            }
            
            print(f"📥 Đang lấy OTP từ API cho account ID: {account_id}...")
            
            response = self.session.get(otp_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                try:
                    # Thử parse JSON
                    result = json.loads(response.text)
                    otp_code = result.get('otp') or result.get('code') or result.get('data')
                    
                    if otp_code:
                        print(f"✅ Đã lấy OTP: {otp_code}")
                        return {
                            "status": "success",
                            "otp": str(otp_code)
                        }
                    else:
                        # Nếu response là string chứa OTP
                        otp_code = response.text.strip()
                        if otp_code.isdigit() and len(otp_code) >= 4:
                            print(f"✅ Đã lấy OTP: {otp_code}")
                            return {
                                "status": "success",
                                "otp": otp_code
                            }
                except json.JSONDecodeError:
                    # Response không phải JSON, thử lấy trực tiếp từ text
                    otp_code = response.text.strip()
                    if otp_code.isdigit() and len(otp_code) >= 4:
                        print(f"✅ Đã lấy OTP: {otp_code}")
                        return {
                            "status": "success",
                            "otp": otp_code
                        }
                
                return {
                    "status": "error",
                    "message": f"Không tìm thấy OTP trong response: {response.text[:100]}"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi lấy OTP. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối khi lấy OTP. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi lấy OTP: {str(e)}"
            }
    
    def get_web_cookies_from_api_session(self) -> Dict[str, Any]:
        """
        Lấy web cookies từ API session (sử dụng token và session_id đã có)
        Bằng cách truy cập trang web với API session_id để lấy cookies
        
        Returns:
            Dict chứa status và cookies
        """
        if not self.is_logged_in or not self.session_id:
            return {
                "status": "error",
                "message": "Chưa đăng nhập API. Vui lòng gọi login() trước."
            }
        
        try:
            print("📥 Đang lấy web cookies từ API session...")
            
            # Headers giống trình duyệt đầy đủ
            browser_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            # Bước 1: Truy cập trang chủ với API session_id để lấy cookies ban đầu
            home_url = "https://www.fshare.vn"
            browser_headers['Cookie'] = f'session_id={self.session_id}'
            
            print("   → Truy cập trang chủ...")
            response = self.session.get(home_url, headers=browser_headers, timeout=30)
            
            # Lấy cookies từ response
            cookies_dict = self.session.cookies.get_dict()
            
            # Bước 2: Truy cập trang security để lấy thêm cookies và CSRF
            security_url = "https://www.fshare.vn/account/security"
            
            # Xây dựng cookie string với session_id và cookies đã có
            cookie_parts = [f'session_id={self.session_id}']
            for key, value in cookies_dict.items():
                cookie_parts.append(f"{key}={value}")
            cookie_string = "; ".join(cookie_parts)
            
            browser_headers['Cookie'] = cookie_string
            browser_headers['Referer'] = home_url
            browser_headers['Sec-Fetch-Site'] = 'same-origin'
            
            print("   → Truy cập trang security...")
            response = self.session.get(security_url, headers=browser_headers, timeout=30)
            
            # Cập nhật cookies sau khi truy cập security
            cookies_dict = self.session.cookies.get_dict()
            
            # Kiểm tra xem có cookies cần thiết không
            if 'fshare-app' in cookies_dict or 'PHPSESSID' in cookies_dict or len(cookies_dict) > 0:
                print("✅ Đã lấy web cookies từ API session")
                return {
                    "status": "success",
                    "cookies": cookies_dict
                }
            else:
                return {
                    "status": "error",
                    "message": "Không thể lấy web cookies từ API session. Có thể cần đăng nhập qua web interface."
                }
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 412:
                return {
                    "status": "error",
                    "message": "HTTP 412 Precondition Failed. Server có thể yêu cầu headers đặc biệt. Thử đăng nhập qua web interface."
                }
            return {
                "status": "error",
                "message": f"Lỗi HTTP {e.response.status_code} khi lấy web cookies"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi khi lấy web cookies: {str(e)}"
            }
    
    def login_web_interface(self) -> Dict[str, Any]:
        """
        Đăng nhập qua web interface để lấy web cookies (fshare-app, PHPSESSID, _csrf)
        Sử dụng email và password đã có
        
        Returns:
            Dict chứa status và cookies
        """
        try:
            print("📥 Đang đăng nhập qua web interface...")
            
            # Bước 1: Truy cập trang login để lấy CSRF token
            login_url = "https://www.fshare.vn/login"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            print("   → Truy cập trang login...")
            response = self.session.get(login_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Không thể truy cập trang login. HTTP {response.status_code}"
                }
            
            # Lấy CSRF token từ trang login
            csrf_token = None
            csrf_patterns = [
                r'<meta name="csrf-token" content="([^"]+)"',
                r'<input[^>]*name=["\']_csrf-app["\'][^>]*value=["\']([^"]+)["\']',
                r'csrf-token["\']?\s*[:=]\s*["\']([^"]+)["\']'
            ]
            
            for pattern in csrf_patterns:
                match = re.search(pattern, response.text)
                if match:
                    csrf_token = match.group(1)
                    break
            
            if not csrf_token:
                return {
                    "status": "error",
                    "message": "Không thể lấy CSRF token từ trang login"
                }
            
            print(f"   ✅ Đã lấy CSRF token: {csrf_token[:20]}...")
            
            # Lấy cookies ban đầu
            initial_cookies = self.session.cookies.get_dict()
            
            # Bước 2: Gửi POST request đăng nhập
            login_post_url = "https://www.fshare.vn/login"
            
            # Xây dựng cookie string
            cookie_parts = []
            for key, value in initial_cookies.items():
                cookie_parts.append(f"{key}={value}")
            cookie_string = "; ".join(cookie_parts) if cookie_parts else ""
            
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers['Origin'] = 'https://www.fshare.vn'
            headers['Referer'] = login_url
            headers['Sec-Fetch-Site'] = 'same-origin'
            headers['Sec-Fetch-Mode'] = 'navigate'
            headers['Sec-Fetch-Dest'] = 'document'
            if cookie_string:
                headers['Cookie'] = cookie_string
            
            # Data form đăng nhập
            login_data = {
                '_csrf-app': csrf_token,
                'LoginForm[email]': self.email,
                'LoginForm[password]': self.password,
                'LoginForm[rememberMe]': '1'
            }
            
            print("   → Đang gửi yêu cầu đăng nhập...")
            response = self.session.post(
                login_post_url,
                headers=headers,
                data=login_data,
                timeout=30,
                allow_redirects=True
            )
            
            # Kiểm tra kết quả đăng nhập
            if response.status_code in [200, 302]:
                # Lấy cookies sau khi đăng nhập
                final_cookies = self.session.cookies.get_dict()
                
                # Kiểm tra xem có cookies cần thiết không
                if 'fshare-app' in final_cookies or 'PHPSESSID' in final_cookies or len(final_cookies) > len(initial_cookies):
                    print("✅ Đăng nhập web interface thành công!")
                    return {
                        "status": "success",
                        "cookies": final_cookies
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Đăng nhập không thành công. Không có cookies mới."
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code} khi đăng nhập web interface"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi đăng nhập web interface. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối khi đăng nhập web interface. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi đăng nhập web interface: {str(e)}"
            }
    
    def delete_all_download_sessions(self, csrf_token: Optional[str] = None, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Xóa tất cả download session (giải quyết lỗi 471 - quá nhiều phiên tải)
        Sử dụng web interface như curl command
        
        Args:
            csrf_token: CSRF token từ trang web (nếu None, sẽ tự động lấy)
            account_id: ID tài khoản để lấy OTP (nếu None, sẽ tự động lấy)
        
        Returns:
            Dict chứa status và message
        """
        if not self.is_logged_in:
            return {
                "status": "error",
                "message": "Chưa đăng nhập. Vui lòng gọi login() trước."
            }
        
        try:
            print(f"\n{'='*60}")
            print("Đang xóa tất cả download session...")
            print(f"{'='*60}\n")
            
            # Bước 1: Lấy web cookies từ API session (sử dụng token và session_id đã có)
            cookies_result = self.get_web_cookies_from_api_session()
            
            if cookies_result.get("status") != "success":
                # Nếu không lấy được từ API session, thử đăng nhập web interface
                print("⚠️ Không lấy được cookies từ API session, thử đăng nhập web interface...")
                web_login_result = self.login_web_interface()
                
                if web_login_result.get("status") != "success":
                    return web_login_result
                
                web_cookies = web_login_result.get("cookies", {})
            else:
                web_cookies = cookies_result.get("cookies", {})
            
            # Bước 2: Lấy CSRF token từ trang security
            if not csrf_token:
                print("📥 Đang lấy CSRF token từ trang security...")
                security_url = "https://www.fshare.vn/account/security"
                
                # Xây dựng cookie string: kết hợp API session_id và web cookies
                cookie_parts = []
                # Thêm API session_id (quan trọng để authenticate)
                if self.session_id:
                    cookie_parts.append(f"session_id={self.session_id}")
                # Thêm web cookies
                for key, value in web_cookies.items():
                    cookie_parts.append(f"{key}={value}")
                cookie_string = "; ".join(cookie_parts)
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                    'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'Cookie': cookie_string,
                    'Referer': 'https://www.fshare.vn/account/security'
                }
                
                response = self.session.get(security_url, headers=headers, timeout=30)
                
                if response.status_code == 412:
                    # Nếu gặp lỗi 412, thử đăng nhập web interface
                    print("⚠️ HTTP 412, thử đăng nhập web interface...")
                    web_login_result = self.login_web_interface()
                    
                    if web_login_result.get("status") == "success":
                        # Cập nhật web_cookies từ web login
                        web_cookies = web_login_result.get("cookies", {})
                        # Cập nhật lại cookies trong session
                        for key, value in web_cookies.items():
                            self.session.cookies.set(key, value)
                        
                        # Xây dựng lại cookie string
                        cookie_parts = []
                        if self.session_id:
                            cookie_parts.append(f"session_id={self.session_id}")
                        for key, value in web_cookies.items():
                            cookie_parts.append(f"{key}={value}")
                        cookie_string = "; ".join(cookie_parts)
                        headers['Cookie'] = cookie_string
                        
                        # Thử lại truy cập trang security
                        print("   → Thử lại truy cập trang security...")
                        response = self.session.get(security_url, headers=headers, timeout=30)
                        
                        if response.status_code != 200:
                            return {
                                "status": "error",
                                "message": f"Vẫn gặp lỗi HTTP {response.status_code} sau khi đăng nhập web interface"
                            }
                    else:
                        return {
                            "status": "error",
                            "message": f"HTTP 412 và không thể đăng nhập web interface: {web_login_result.get('message', 'Unknown error')}"
                        }
                
                if response.status_code == 200:
                    # Tìm CSRF token
                    csrf_pattern = r'<meta name="csrf-token" content="([^"]+)"'
                    match = re.search(csrf_pattern, response.text)
                    if match:
                        csrf_token = match.group(1)
                    else:
                        csrf_pattern = r'<input[^>]*name=["\']_csrf-app["\'][^>]*value=["\']([^"]+)["\']'
                        match = re.search(csrf_pattern, response.text)
                        if match:
                            csrf_token = match.group(1)
                    
                    if csrf_token:
                        print(f"✅ Đã lấy CSRF token: {csrf_token[:20]}...")
                    else:
                        return {
                            "status": "error",
                            "message": "Không thể lấy CSRF token từ trang security"
                        }
                else:
                    return {
                        "status": "error",
                        "message": f"Không thể truy cập trang security. HTTP {response.status_code}"
                    }
            
            # Bước 3: Lấy OTP nếu cần
            if not account_id:
                account_id = self.account_id
                if not account_id:
                    user_info = self.get_user_info()
                    if user_info.get("status") == "success":
                        account_id = user_info.get("account_id")
                        self.account_id = account_id
            
            if account_id:
                print("🔐 Đang lấy OTP...")
                otp_result = self.get_otp_from_api(account_id)
                
                if otp_result.get("status") != "success":
                    return {
                        "status": "otp_error",
                        "message": f"Không thể lấy OTP: {otp_result.get('message', 'Unknown error')}"
                    }
                
                otp_code = otp_result.get("otp")
            else:
                return {
                    "status": "error",
                    "message": "Không tìm thấy account_id để lấy OTP. Vui lòng cung cấp account_id."
                }
            
            # Bước 4: Gửi request xóa download session (giống curl command)
            delete_url = "https://www.fshare.vn/account/delete-all-download-session"
            
            # Xây dựng cookie string: kết hợp API session_id và web cookies
            cookie_parts = []
            # Thêm API session_id (quan trọng để authenticate)
            if self.session_id:
                cookie_parts.append(f"session_id={self.session_id}")
            # Thêm web cookies
            for key, value in web_cookies.items():
                cookie_parts.append(f"{key}={value}")
            cookie_string = "; ".join(cookie_parts)
            
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'max-age=0',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://www.fshare.vn',
                'referer': 'https://www.fshare.vn/account/security',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'Cookie': cookie_string
            }
            
            # Data form (giống curl command)
            data = {
                '_csrf-app': csrf_token,
                'DeleteDownloadSessionForm[otp]': otp_code
            }
            
            print("📤 Đang gửi yêu cầu xóa download session với OTP...")
            
            response = self.session.post(
                delete_url,
                headers=headers,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                # Kiểm tra thành công
                if 'thành công' in response.text.lower() or 'success' in response.text.lower() or response.url != delete_url:
                    print("✅ Đã xóa tất cả download session thành công!")
                    return {
                        "status": "success",
                        "message": "Đã xóa tất cả download session thành công"
                    }
                else:
                    # Kiểm tra xem có lỗi gì không
                    if 'lỗi' in response.text.lower() or 'error' in response.text.lower():
                        return {
                            "status": "error",
                            "message": f"Có lỗi khi xóa download session: {response.text[:300]}"
                        }
                    
                    print("✅ Đã gửi yêu cầu xóa download session")
                    return {
                        "status": "success",
                        "message": "Đã gửi yêu cầu xóa download session"
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi xóa download session. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi xóa download session: {str(e)}"
            }
    
    def get_upload_link(self, file_name: str, file_size: int, path: str = "/", secured: int = 1) -> Dict[str, Any]:
        """
        Lấy upload link từ Fshare API (tự động login lại nếu token hết hạn)
        
        Args:
            file_name: Tên file cần upload
            file_size: Kích thước file (bytes)
            path: Đường dẫn thư mục đích (mặc định: "/")
            secured: Có bảo mật không (1 = có, 0 = không, mặc định: 1)
        
        Returns:
            Dict chứa status và location URL
        """
        # Đảm bảo đã đăng nhập
        if not self.ensure_logged_in():
            return {
                "status": "error",
                "message": "Không thể đăng nhập. Vui lòng kiểm tra lại email và password."
            }
        
        try:
            print(f"\n{'='*60}")
            print(f"Đang lấy upload link cho file: {file_name}")
            print(f"Kích thước: {file_size / (1024**2):.2f} MB")
            print(f"{'='*60}\n")
            
            # Chuẩn bị payload
            payload = json.dumps({
                "name": file_name,
                "size": str(file_size),  # API yêu cầu string
                "path": path,
                "token": self.token,
                "secured": secured
            })
            
            headers = {
                'Content-Type': 'application/json; charset=UTF-8',
                'User-Agent': USER_AGENT,
                'Cookie': f'session_id={self.session_id}'
            }
            
            print("📤 Đang gửi yêu cầu lấy upload link...")
            
            response = self.session.post(
                UPLOAD_API,
                headers=headers,
                data=payload,
                timeout=60
            )
            
            # Parse response
            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": f"Response không phải JSON hợp lệ. Status: {response.status_code}, Content: {response.text[:200]}"
                }
            
            # Xử lý các mã lỗi - tự động login lại nếu token hết hạn
            if response.status_code == 400:
                print("⚠️ Token có thể đã hết hạn, đang đăng nhập lại...")
                login_result = self.login()
                if login_result.get("status") == "success":
                    # Retry với token mới
                    payload = json.dumps({
                        "name": file_name,
                        "size": str(file_size),
                        "path": path,
                        "token": self.token,
                        "secured": secured
                    })
                    headers = {
                        'Content-Type': 'application/json; charset=UTF-8',
                        'User-Agent': USER_AGENT,
                        'Cookie': f'session_id={self.session_id}'
                    }
                    response = self.session.post(
                        UPLOAD_API,
                        headers=headers,
                        data=payload,
                        timeout=60
                    )
                    try:
                        result = json.loads(response.content)
                    except json.JSONDecodeError:
                        return {
                            "status": "error",
                            "message": f"Response không phải JSON hợp lệ sau khi login lại. Status: {response.status_code}"
                        }
                else:
                    return {
                        "status": "error",
                        "message": "Bad request. Token có thể không đúng hoặc đã hết hạn. Không thể đăng nhập lại."
                    }
            
            if response.status_code == 200:
                code = result.get("code", 0)
                location = result.get("location", "")
                
                if code == 200 and location:
                    print(f"✅ Đã lấy upload link thành công!")
                    print(f"🔗 Upload URL: {location}")
                    return {
                        "status": "success",
                        "location": location,
                        "upload_url": location
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Không tìm thấy location trong response. Code: {code}",
                        "response": result
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code}: {result.get('msg', response.text[:200])}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi lấy upload link. Vui lòng thử lại."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi lấy upload link: {str(e)}"
            }
    
    def upload_file_chunk(self, upload_url: str, file_path: str, start_byte: int, 
                         end_byte: int, chunk_index: int, total_chunks: int) -> Dict[str, Any]:
        """
        Upload một chunk của file (dùng cho đa luồng)
        
        Args:
            upload_url: URL upload
            file_path: Đường dẫn file
            start_byte: Byte bắt đầu của chunk
            end_byte: Byte kết thúc của chunk
            chunk_index: Chỉ số chunk (0-based)
            total_chunks: Tổng số chunks
        
        Returns:
            Dict chứa status của chunk upload
        """
        try:
            with open(file_path, 'rb') as f:
                f.seek(start_byte)
                chunk_data = f.read(end_byte - start_byte + 1)
            
            headers = {
                'User-Agent': USER_AGENT,
                'Content-Type': 'application/octet-stream',
                'Content-Range': f'bytes {start_byte}-{end_byte}/*',
                'Content-Length': str(len(chunk_data))
            }
            
            response = self.session.put(
                upload_url,
                headers=headers,
                data=chunk_data,
                timeout=600
            )
            
            if response.status_code in [200, 201, 206]:  # 206 = Partial Content (resume)
                return {
                    "status": "success",
                    "chunk_index": chunk_index,
                    "start_byte": start_byte,
                    "end_byte": end_byte
                }
            else:
                return {
                    "status": "error",
                    "chunk_index": chunk_index,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }
        except Exception as e:
            return {
                "status": "error",
                "chunk_index": chunk_index,
                "message": str(e)
            }
    
    def upload_file_multithreaded(self, file_path: str, upload_path: str = "/", 
                                  secured: int = 1, num_threads: int = 4, 
                                  chunk_size_mb: int = 100) -> Dict[str, Any]:
        """
        Upload file lên Fshare với đa luồng (chia file thành nhiều phần và upload song song)
        
        Args:
            file_path: Đường dẫn file cần upload
            upload_path: Đường dẫn thư mục đích trên Fshare (mặc định: "/")
            secured: Có bảo mật không (1 = có, 0 = không, mặc định: 1)
            num_threads: Số luồng upload đồng thời (mặc định: 4)
            chunk_size_mb: Kích thước mỗi chunk (MB, mặc định: 100MB)
        
        Returns:
            Dict chứa status và thông tin file đã upload
        """
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File không tồn tại: {file_path}"
            }
        
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            chunk_size = chunk_size_mb * 1024 * 1024  # Convert to bytes
            
            print(f"\n{'='*60}")
            print(f"Đang upload file (đa luồng): {file_name}")
            print(f"Kích thước: {file_size / (1024**2):.2f} MB")
            print(f"Số luồng: {num_threads}")
            print(f"Kích thước chunk: {chunk_size_mb} MB")
            print(f"{'='*60}\n")
            
            # Bước 1: Lấy upload link
            upload_link_result = self.get_upload_link(
                file_name=file_name,
                file_size=file_size,
                path=upload_path,
                secured=secured
            )
            
            if upload_link_result["status"] != "success":
                return upload_link_result
            
            upload_url = upload_link_result.get("location")
            
            # Bước 2: Chia file thành chunks
            total_chunks = (file_size + chunk_size - 1) // chunk_size
            print(f"📦 Chia file thành {total_chunks} chunks...")
            
            chunks = []
            for i in range(total_chunks):
                start_byte = i * chunk_size
                end_byte = min((i + 1) * chunk_size - 1, file_size - 1)
                chunks.append((start_byte, end_byte, i))
            
            # Bước 3: Upload các chunks song song
            print(f"📤 Đang upload {total_chunks} chunks với {num_threads} luồng...")
            
            success_count = 0
            error_count = 0
            results = []
            
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                # Submit tất cả tasks
                future_to_chunk = {
                    executor.submit(
                        self.upload_file_chunk,
                        upload_url,
                        file_path,
                        start,
                        end,
                        idx,
                        total_chunks
                    ): (start, end, idx)
                    for start, end, idx in chunks
                }
                
                # Xử lý kết quả khi hoàn thành
                for future in as_completed(future_to_chunk):
                    result = future.result()
                    results.append(result)
                    
                    if result["status"] == "success":
                        success_count += 1
                        chunk_idx = result["chunk_index"]
                        print(f"✅ Chunk {chunk_idx + 1}/{total_chunks} đã upload thành công")
                    else:
                        error_count += 1
                        chunk_idx = result["chunk_index"]
                        print(f"❌ Chunk {chunk_idx + 1}/{total_chunks} lỗi: {result.get('message', 'Unknown')}")
            
            if success_count == total_chunks:
                print(f"\n✅ Upload thành công tất cả {total_chunks} chunks!")
                return {
                    "status": "success",
                    "message": "Upload thành công (đa luồng)",
                    "file_name": file_name,
                    "file_size": file_size,
                    "total_chunks": total_chunks,
                    "success_chunks": success_count
                }
            else:
                return {
                    "status": "partial",
                    "message": f"Upload một phần: {success_count}/{total_chunks} chunks thành công",
                    "file_name": file_name,
                    "file_size": file_size,
                    "total_chunks": total_chunks,
                    "success_chunks": success_count,
                    "error_chunks": error_count,
                    "results": results
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi upload file (đa luồng): {str(e)}"
            }
    
    def upload_file_with_resume(self, file_path: str, upload_path: str = "/", 
                                secured: int = 1, resume_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload file với khả năng resume (tiếp tục từ vị trí đã dừng)
        Sau khi upload xong, tự động lấy link Fshare của file
        
        Args:
            file_path: Đường dẫn file cần upload
            upload_path: Đường dẫn thư mục đích trên Fshare (mặc định: "/")
            secured: Có bảo mật không (1 = có, 0 = không, mặc định: 1)
            resume_file: Đường dẫn file lưu trạng thái resume (mặc định: {file_path}.resume)
        
        Returns:
            Dict chứa status, thông tin file đã upload và link Fshare
        """
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File không tồn tại: {file_path}"
            }
        
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # File lưu trạng thái resume
            if not resume_file:
                resume_file = file_path + ".resume"
            
            # Kiểm tra xem có file resume không
            uploaded_bytes = 0
            upload_url = None
            
            if os.path.exists(resume_file):
                print(f"📥 Tìm thấy file resume: {resume_file}")
                try:
                    with open(resume_file, 'r') as f:
                        resume_data = json.load(f)
                        uploaded_bytes = resume_data.get("uploaded_bytes", 0)
                        upload_url = resume_data.get("upload_url")
                        
                        if uploaded_bytes >= file_size:
                            print("✅ File đã được upload hoàn tất!")
                            os.remove(resume_file)
                            # Lấy link Fshare từ response đã lưu hoặc query lại
                            fshare_link = resume_data.get("fshare_link")
                            return {
                                "status": "success",
                                "message": "File đã được upload hoàn tất (từ resume)",
                                "file_name": file_name,
                                "file_size": file_size,
                                "fshare_link": fshare_link
                            }
                except Exception as e:
                    print(f"⚠️ Không thể đọc file resume: {e}")
                    uploaded_bytes = 0
            
            print(f"\n{'='*60}")
            print(f"Đang upload file: {file_name}")
            print(f"Kích thước: {file_size / (1024**2):.2f} MB")
            if uploaded_bytes > 0:
                print(f"Tiếp tục từ: {uploaded_bytes / (1024**2):.2f} MB ({uploaded_bytes / file_size * 100:.1f}%)")
            print(f"{'='*60}")
            
            # Nếu chưa có upload_url, lấy mới
            if not upload_url:
                upload_link_result = self.get_upload_link(
                    file_name=file_name,
                    file_size=file_size,
                    path=upload_path,
                    secured=secured
                )
                
                if upload_link_result["status"] != "success":
                    return upload_link_result
                
                upload_url = upload_link_result.get("location")
            
            # Upload file từ vị trí đã dừng
            chunk_size = 1024 * 1024  # 1MB chunks
            total_uploaded = uploaded_bytes
            upload_start_time = time.time()
            last_response = None
            
            try:
                with open(file_path, 'rb') as f:
                    f.seek(uploaded_bytes)
                    
                    while total_uploaded < file_size:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        
                        # Upload chunk với Range header
                        headers = {
                            'User-Agent': USER_AGENT,
                            'Content-Type': 'application/octet-stream',
                            'Content-Range': f'bytes {total_uploaded}-{total_uploaded + len(chunk) - 1}/{file_size}',
                            'Content-Length': str(len(chunk))
                        }
                        
                        response = self.session.put(
                            upload_url,
                            headers=headers,
                            data=chunk,
                            timeout=300
                        )
                        
                        if response.status_code in [200, 201, 206, 308]:  # 206 = Partial, 308 = Resume
                            total_uploaded += len(chunk)
                            last_response = response  # Lưu response cuối cùng
                            
                            # Lưu trạng thái resume
                            resume_data = {
                                "uploaded_bytes": total_uploaded,
                                "upload_url": upload_url,
                                "file_size": file_size,
                                "timestamp": time.time()
                            }
                            with open(resume_file, 'w') as rf:
                                json.dump(resume_data, rf)
                            
                            # Hiển thị progress bar đẹp
                            print_progress_bar(total_uploaded, file_size, bar_length=50, 
                                             show_speed=True, start_time=upload_start_time)
                        else:
                            print()  # Xuống dòng khi có lỗi
                            return {
                                "status": "error",
                                "message": f"Lỗi HTTP {response.status_code} khi upload: {response.text[:200]}",
                                "uploaded_bytes": total_uploaded,
                                "resume_file": resume_file
                            }
                
                # Upload hoàn tất
                print()  # Xuống dòng sau progress bar
                
                if os.path.exists(resume_file):
                    os.remove(resume_file)
                
                print("✅ Upload thành công!")
                
                # Lấy link Fshare từ response
                fshare_link = None
                if last_response and last_response.status_code in [200, 201]:
                    try:
                        # Parse response để lấy linkcode hoặc URL
                        result_text = last_response.text
                        if result_text:
                            # Thử parse JSON
                            try:
                                result = json.loads(result_text)
                                
                                # Debug: in ra response để kiểm tra
                                print(f"🔍 Response JSON: {result}")
                                
                                # Thử các key có thể chứa linkcode hoặc URL
                                linkcode = result.get('linkcode') or result.get('code') or result.get('filecode') or result.get('id') or result.get('url')
                                
                                if linkcode:
                                    # Tạo Fshare URL
                                    if str(linkcode).startswith('http'):
                                        fshare_link = str(linkcode)
                                    else:
                                        fshare_link = f"https://www.fshare.vn/file/{linkcode}"
                                elif 'location' in result:
                                    location = result.get('location')
                                    if location and 'fshare.vn' in location:
                                        fshare_link = location
                            except json.JSONDecodeError:
                                # Response không phải JSON, thử tìm linkcode trong text
                                print(f"🔍 Response không phải JSON, text: {result_text[:200]}")
                                import re
                                # Tìm linkcode trong text (có thể là HTML hoặc text khác)
                                linkcode_patterns = [
                                    r'file/([A-Za-z0-9]+)',
                                    r'linkcode["\']?\s*[:=]\s*["\']?([A-Za-z0-9]+)',
                                    r'code["\']?\s*[:=]\s*["\']?([A-Za-z0-9]+)'
                                ]
                                for pattern in linkcode_patterns:
                                    linkcode_match = re.search(pattern, result_text)
                                    if linkcode_match:
                                        linkcode = linkcode_match.group(1)
                                        if len(linkcode) > 5:  # Linkcode thường dài hơn 5 ký tự
                                            fshare_link = f"https://www.fshare.vn/file/{linkcode}"
                                            break
                    except Exception as e:
                        print(f"🔍 Lỗi khi parse response: {e}")
                        pass
                
                # Nếu chưa có link, đợi một chút rồi tìm file trong folder list
                if not fshare_link:
                    print("📥 Đang lấy link Fshare của file vừa upload...")
                    # Đợi 3 giây để file xuất hiện trong folder list
                    time.sleep(3)
                    
                    # Hàm helper để tìm file trong folder list bằng cách gọi API trực tiếp
                    def find_file_in_path(target_path, target_file_name):
                        """Tìm file trong folder list của path đã cho"""
                        try:
                            # Theo tài liệu API, url phải là URL đầy đủ như https://www.fshare.vn/folder/ABC123
                            # Với root folder (path="/"), thử một số cách:
                            api_urls_to_try = []
                            
                            if target_path == "/":
                                # Root folder - thử các cách khác nhau
                                api_urls_to_try = [
                                    "",  # URL rỗng
                                    "https://www.fshare.vn/",  # Root URL
                                ]
                            elif target_path.startswith('http'):
                                # Đã là URL đầy đủ
                                api_urls_to_try = [target_path]
                            elif target_path.startswith('/folder/'):
                                # Path dạng /folder/ABC123
                                api_urls_to_try = [f"https://www.fshare.vn{target_path}"]
                            else:
                                # Path dạng folder/ABC123 hoặc ABC123
                                api_urls_to_try = [f"https://www.fshare.vn/folder/{target_path.strip('/')}"]
                            
                            print(f"🔍 Đang tìm file '{target_file_name}' trong path: '{target_path}'")
                            print(f"🔍 Sẽ thử các URL: {api_urls_to_try}")
                            
                            # Thử với mỗi URL
                            for api_url in api_urls_to_try:
                                print(f"🔍 Thử với URL: '{api_url}'")
                                
                                # Thử tìm trong 3 trang đầu
                                for page in range(0, 3):
                                    payload = json.dumps({
                                        "token": self.token,
                                        "url": api_url,  # URL đầy đủ hoặc rỗng
                                        "dirOnly": 0,
                                        "pageIndex": page,
                                        "limit": 10000
                                    })
                                    
                                    headers = {
                                        'Content-Type': 'application/json',
                                        'User-Agent': USER_AGENT,
                                        'Cookie': f'session_id={self.session_id}'
                                    }
                                    
                                    response = self.session.post(
                                        FOLDER_API,
                                        headers=headers,
                                        data=payload,
                                        timeout=30
                                    )
                                    
                                    if response.status_code == 200:
                                        try:
                                            items = json.loads(response.content)
                                            if items and len(items) > 0:
                                                print(f"🔍 Trang {page + 1}: Tìm thấy {len(items)} items")
                                                # Tìm file có tên trùng (duyệt từ cuối lên = mới nhất trước)
                                                for item in reversed(items):
                                                    # item["type"] == "0" là folder, "1" là file (theo tài liệu)
                                                    item_type = str(item.get("type", "1"))
                                                    item_name = item.get("name", "")
                                                    # Debug: in ra một vài file đầu tiên
                                                    if len(items) <= 10:  # Nếu ít items, in ra tất cả
                                                        print(f"   - {item_name} (type: {item_type}, folder: {item_type == '0'})")
                                                    
                                                    if item_type != "0":  # Là file (type="1")
                                                        if item_name == target_file_name:
                                                            linkcode = item.get("linkcode", "")
                                                            if linkcode:
                                                                print(f"✅ Tìm thấy file! Linkcode: {linkcode}")
                                                                return f"https://www.fshare.vn/file/{linkcode}"
                                                
                                                # Nếu không tìm thấy và còn items, tiếp tục trang sau
                                            else:
                                                # Không còn items, dừng
                                                print(f"🔍 Trang {page + 1}: Không có items")
                                                break
                                        except json.JSONDecodeError as e:
                                            print(f"🔍 Lỗi parse JSON: {e}, response: {response.text[:200]}")
                                            break
                                    else:
                                        print(f"🔍 Lỗi HTTP {response.status_code}: {response.text[:200]}")
                                        # Nếu lỗi 400/404 với URL này, thử URL tiếp theo
                                        if response.status_code in [400, 404]:
                                            break  # Break ra khỏi vòng lặp page, thử URL tiếp theo
                                        
                                # Nếu đã tìm thấy với URL này, return luôn
                                # Nếu chưa tìm thấy, thử URL tiếp theo
                                
                        except Exception as e:
                            print(f"🔍 Exception khi tìm file: {e}")
                            import traceback
                            traceback.print_exc()
                            pass
                        return None
                    
                    try:
                        # Thử tìm file trong upload_path
                        found_link = find_file_in_path(upload_path, file_name)
                        if found_link:
                            fshare_link = found_link
                    except Exception as e:
                        print(f"🔍 Exception: {e}")
                        pass
                
                result_dict = {
                    "status": "success",
                    "message": "Upload thành công (với resume)",
                    "file_name": file_name,
                    "file_size": file_size,
                    "fshare_link": fshare_link
                }
                
                if fshare_link:
                    print(f"🔗 Link Fshare: {fshare_link}")
                else:
                    print("⚠️ Không thể lấy link Fshare tự động")
                
                return result_dict
                
            except KeyboardInterrupt:
                print("\n⚠️ Upload bị dừng bởi người dùng")
                print(f"💾 Trạng thái đã được lưu vào: {resume_file}")
                print(f"💡 Chạy lại để tiếp tục upload từ vị trí đã dừng")
                return {
                    "status": "paused",
                    "message": "Upload bị dừng, có thể resume sau",
                    "uploaded_bytes": total_uploaded,
                    "resume_file": resume_file
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi upload file (với resume): {str(e)}"
            }
    
    def upload_file(self, file_path: str, upload_path: str = "/", secured: int = 1, 
                   chunk_size: int = 8192, use_multithread: bool = False, 
                   num_threads: int = 4, use_resume: bool = False) -> Dict[str, Any]:
        """
        Upload file lên Fshare (tự động lấy upload link và upload file)
        
        Args:
            file_path: Đường dẫn file cần upload
            upload_path: Đường dẫn thư mục đích trên Fshare (mặc định: "/")
            secured: Có bảo mật không (1 = có, 0 = không, mặc định: 1)
            chunk_size: Kích thước chunk khi upload (mặc định: 8192 bytes) - không dùng nếu use_multithread=True
            use_multithread: Sử dụng đa luồng (mặc định: False)
            num_threads: Số luồng nếu dùng đa luồng (mặc định: 4)
            use_resume: Sử dụng resume upload (mặc định: False)
        
        Returns:
            Dict chứa status và thông tin file đã upload
        """
        # Nếu dùng resume, gọi hàm resume
        if use_resume:
            return self.upload_file_with_resume(file_path, upload_path, secured)
        
        # Nếu dùng đa luồng, gọi hàm đa luồng
        if use_multithread:
            return self.upload_file_multithreaded(file_path, upload_path, secured, num_threads)
        
        # Upload thông thường (single thread)
        import os
        
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File không tồn tại: {file_path}"
            }
        
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            print(f"\n{'='*60}")
            print(f"Đang upload file: {file_name}")
            print(f"Kích thước: {file_size / (1024**2):.2f} MB")
            print(f"Đường dẫn đích: {upload_path}")
            print(f"{'='*60}\n")
            
            # Bước 1: Lấy upload link
            upload_link_result = self.get_upload_link(
                file_name=file_name,
                file_size=file_size,
                path=upload_path,
                secured=secured
            )
            
            if upload_link_result["status"] != "success":
                return upload_link_result
            
            upload_url = upload_link_result.get("location")
            
            # Bước 2: Upload file binary lên location
            print(f"📤 Đang upload file lên: {upload_url}")
            
            headers = {
                'User-Agent': USER_AGENT,
                'Content-Type': 'application/octet-stream'
            }
            
            # Đọc và upload file
            # Với file lớn, cần upload trực tiếp với file object
            print(f"📤 Đang upload file ({file_size / (1024**2):.2f} MB)...")
            print("⏳ Vui lòng đợi, quá trình này có thể mất vài phút với file lớn...")
            
            # Upload file trực tiếp (requests sẽ tự động xử lý chunk)
            # Sử dụng file object trực tiếp để tránh đọc toàn bộ vào memory
            with open(file_path, 'rb') as f:
                try:
                    response = self.session.post(
                        upload_url,
                        headers=headers,
                        data=f,
                        timeout=1800,  # Timeout 30 phút cho file lớn
                        stream=False  # Không dùng stream để tránh lỗi
                    )
                except requests.exceptions.ChunkedEncodingError:
                    # Nếu lỗi chunked encoding, thử upload lại với cách khác
                    print("⚠️ Lỗi chunked encoding, thử upload lại...")
                    f.seek(0)  # Reset file pointer
                    # Thử upload với Content-Length header
                    headers['Content-Length'] = str(file_size)
                    response = self.session.post(
                        upload_url,
                        headers=headers,
                        data=f,
                        timeout=1800
                    )
            
            if response.status_code == 200:
                print("✅ Upload thành công!")
                
                # Parse response để lấy thông tin file
                try:
                    result = json.loads(response.text)
                    return {
                        "status": "success",
                        "message": "Upload thành công",
                        "file_name": file_name,
                        "file_size": file_size,
                        "response": result
                    }
                except json.JSONDecodeError:
                    # Response có thể không phải JSON
                    return {
                        "status": "success",
                        "message": "Upload thành công",
                        "file_name": file_name,
                        "file_size": file_size,
                        "response_text": response.text[:500]
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Lỗi HTTP {response.status_code} khi upload: {response.text[:200]}"
                }
                
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"File không tồn tại: {file_path}"
            }
        except PermissionError:
            return {
                "status": "error",
                "message": f"Không có quyền đọc file: {file_path}"
            }
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Timeout khi upload file. File có thể quá lớn hoặc kết nối chậm."
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "message": "Lỗi kết nối khi upload. Vui lòng kiểm tra kết nối mạng."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi không xác định khi upload file: {str(e)}"
            }
    
    def logout(self) -> bool:
        """
        Đăng xuất khỏi Fshare
        
        Returns:
            True nếu thành công, False nếu thất bại
        """
        if not self.session_id:
            return False
        
        try:
            headers = {
                'Cookie': f'session_id={self.session_id}'
            }
            response = self.session.get(
                'https://api.fshare.vn/api/user/logout',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                self.is_logged_in = False
                self.token = None
                self.session_id = None
                print("✅ Đã đăng xuất thành công")
                return True
            else:
                print(f"⚠️ Lỗi khi đăng xuất: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"⚠️ Lỗi khi đăng xuất: {str(e)}")
            return False
def handle_cli_commands(args: argparse.Namespace) -> None:
    """
    Xử lý các lệnh CLI (upload, xem thông tin folder).
    """
    # Thiết lập thông tin đăng nhập (ưu tiên token/session cho gọn)
    email = args.email or DEFAULT_EMAIL
    password = args.password or DEFAULT_PASSWORD
    domain_arg = args.domain or DEFAULT_DOMAIN
    domain = domain_arg if domain_arg.startswith('@') else f"@{domain_arg}"
    
    fshare = FshareAPI(email, password, domain)
    
    if args.token and args.session_id:
        # Dùng trực tiếp token/session_id (nhanh, không cần login)
        fshare.set_session(token=args.token, session_id=args.session_id, account_id=args.account_id)
        print("✅ Đã set token/session_id cho CLI")
    else:
        # Tự động login (có thể dùng session lưu)
        login_result = fshare.auto_login(use_saved_session=not args.no_saved_session)
        if login_result.get("status") != "success":
            print(f"❌ Đăng nhập thất bại: {login_result.get('message', 'Lỗi không xác định')}")
            sys.exit(1)
        print("✅ Đăng nhập thành công (CLI mode)")
    
    if args.command == "upload":
        secured = 0 if args.public else 1
        if args.resume:
            result = fshare.upload_file_with_resume(
                file_path=args.file,
                upload_path=args.dest,
                secured=secured
            )
        else:
            # Dùng đa luồng nếu người dùng chỉ định
            if args.multithread:
                result = fshare.upload_file_multithreaded(
                    file_path=args.file,
                    upload_path=args.dest,
                    secured=secured,
                    num_threads=args.threads,
                    chunk_size_mb=args.chunk_size_mb
                )
            else:
                result = fshare.upload_file(
                    file_path=args.file,
                    upload_path=args.dest,
                    secured=secured,
                    use_resume=False,
                    use_multithread=False
                )
        
        if result.get("status") in ["success", "partial"]:
            print(f"📁 File: {result.get('file_name', os.path.basename(args.file))}")
            print(f"💾 Kích thước: {result.get('file_size', 0) / (1024**2):.2f} MB")
            if result.get("fshare_link"):
                # Ghi chú: sở thích của user về log upload chỉ in URL với '@'
                print(f"@{result.get('fshare_link')}")
            else:
                print(result.get("message", "Hoàn tất"))
        else:
            print(f"❌ Lỗi upload: {result.get('message', 'Không rõ lỗi')}")
            sys.exit(1)
    
    elif args.command == "folder":
        if args.recursive:
            result = fshare.get_all_files_from_folder(
                folder_url=args.url,
                recursive=True,
                max_depth=args.max_depth
            )
            if result.get("status") == "success":
                files = result.get("files", [])
                folders = result.get("folders", [])
                print(f"📁 Folder: {len(folders)} | 📄 File: {len(files)}")
                for item in files:
                    indent = "  " * item.get("depth", 0)
                    print(f"{indent}- {item['name']} ({item['size_str']}) -> {item['url']}")
            else:
                print(f"❌ Lỗi: {result.get('message', 'Không rõ lỗi')}")
                sys.exit(1)
        else:
            result = fshare.get_folder_list(args.url, page_index=0, limit=args.limit)
            if result.get("status") == "success":
                items = result.get("items", [])
                print(f"✅ {len(items)} items")
                for item in items:
                    icon = "[DIR]" if item["is_folder"] else "[FILE]"
                    print(f"{icon} {item['name']} ({item['size_str']}) -> {item['url']}")
                if result.get("has_more"):
                    print("⚠️ Còn item khác, tăng --limit hoặc dùng --recursive.")
            else:
                print(f"❌ Lỗi: {result.get('message', 'Không rõ lỗi')}")
                sys.exit(1)


def build_arg_parser() -> argparse.ArgumentParser:
    """Tạo parser cho CLI."""
    parser = argparse.ArgumentParser(
        description="Fshare CLI: upload và lấy thông tin file/folder."
    )
    parser.add_argument("--email", help="Email Fshare (mặc định dùng tài khoản preset)")
    parser.add_argument("--password", help="Mật khẩu Fshare (mặc định dùng mật khẩu preset)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Domain nếu email không có @ (mặc định: @fshare.vn)")
    parser.add_argument("--no-saved-session", action="store_true", help="Bỏ qua session đã lưu, luôn login mới")
    parser.add_argument("--token", help="Token API (nếu có sẵn để bỏ qua login)")
    parser.add_argument("--session-id", help="Session ID (đi kèm token nếu có sẵn)")
    parser.add_argument("--account-id", help="Account ID (tuỳ chọn, dùng kèm token/session)")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Lệnh upload
    upload_parser = subparsers.add_parser("upload", help="Upload file lên Fshare")
    upload_parser.add_argument("--file", required=True, help="Đường dẫn file cần upload")
    upload_parser.add_argument("--dest", default="/", help="Đường dẫn thư mục đích trên Fshare (mặc định: /)")
    upload_parser.add_argument("--public", action="store_true", help="Đặt secured=0 (công khai)")
    upload_parser.add_argument("--resume", action="store_true", help="Dùng chế độ resume upload")
    upload_parser.add_argument("--multithread", action="store_true", help="Upload đa luồng")
    upload_parser.add_argument("--threads", type=int, default=4, help="Số luồng khi đa luồng (mặc định: 4)")
    upload_parser.add_argument("--chunk-size-mb", type=int, default=100, help="Kích thước chunk MB khi đa luồng (mặc định: 100)")
    
    # Lệnh folder
    folder_parser = subparsers.add_parser("folder", help="Lấy thông tin folder")
    folder_parser.add_argument("--url", required=True, help="URL folder Fshare")
    folder_parser.add_argument("--limit", type=int, default=10000, help="Số item tối đa (mặc định 10000)")
    folder_parser.add_argument("--recursive", action="store_true", help="Đệ quy vào folder con")
    folder_parser.add_argument("--max-depth", type=int, default=100, help="Độ sâu tối đa khi đệ quy")
    
    return parser


def main():
    """Hàm main: hỗ trợ CLI và giữ tương tác cũ nếu không truyền args."""
    # Quick mode:
    # - python fshare_api3.py <file_path> <folder_dest>
    # - python fshare_api3.py <file_path>           (dest mặc định "/")
    if len(sys.argv) in (2, 3) and not any(arg in ["upload", "folder"] for arg in sys.argv):
        file_path = sys.argv[1]
        dest_path = sys.argv[2] if len(sys.argv) == 3 else "/"
        print(f"🚀 Quick upload: {file_path} -> {dest_path}")
        
        fshare = FshareAPI(DEFAULT_EMAIL, DEFAULT_PASSWORD, DEFAULT_DOMAIN)
        login_result = fshare.auto_login(use_saved_session=True)
        if login_result.get("status") != "success":
            print(f"❌ Đăng nhập thất bại: {login_result.get('message', 'Lỗi không xác định')}")
            sys.exit(1)
        
        res = fshare.upload_file_with_resume(
            file_path=file_path,
            upload_path=dest_path,
            secured=1
        )
        if res.get("status") == "success":
            print(f"✅ Upload xong: {res.get('file_name')} ({res.get('file_size', 0)/(1024**2):.2f} MB)")
            if res.get("fshare_link"):
                print(f"@{res.get('fshare_link')}")
        else:
            print(f"❌ Lỗi upload: {res.get('message', 'Không rõ lỗi')}")
            sys.exit(1)
        return

    # Nếu không có tham số subcommand, vẫn giữ chế độ tương tác cũ
    if len(sys.argv) > 1 and any(arg in ["upload", "folder"] for arg in sys.argv):
        parser = build_arg_parser()
        args = parser.parse_args()
        handle_cli_commands(args)
        return
    
    # --- Chế độ tương tác cũ ---
    print("="*60)
    print("Fshare API Login & Getlink Tool")
    print("Dựa trên cách addon plugin.video.vietmediaF")
    print("="*60)
    print()
    
    # Nhập thông tin đăng nhập (hoặc dùng mặc định)
    use_default = input(f"Sử dụng tài khoản mặc định? (y/n, mặc định: y): ").strip().lower()
    
    if use_default == '' or use_default == 'y':
        email = DEFAULT_EMAIL
        password = DEFAULT_PASSWORD
        print(f"✅ Sử dụng tài khoản mặc định: {email}")
    else:
        email = input("Nhập email Fshare (có thể không có @fshare.vn): ").strip()
        password = input("Nhập password Fshare: ").strip()
        
        if not email or not password:
            print("❌ Email và password không được để trống!")
            return
    
    # Hỏi domain nếu email không có @
    domain = '@fshare.vn'
    if '@' not in email:
        domain_input = input(f"Nhập domain (mặc định: @fshare.vn): ").strip()
        if domain_input:
            domain = domain_input if domain_input.startswith('@') else '@' + domain_input
    
    # Khởi tạo FshareAPI
    fshare = FshareAPI(email, password, domain)
    
    # Tự động đăng nhập (thử dùng session đã lưu, nếu không thì login mới)
    login_result = fshare.auto_login(use_saved_session=True)
    
    if login_result["status"] == "success":
        print("\n✅ Đăng nhập thành công!")
        
        # Hiển thị đầy đủ token và session_id
        print(f"\n🔑 Token: {login_result.get('token', 'N/A')}")
        print(f"🆔 Session ID: {login_result.get('session_id', 'N/A')}")
        
        # Lấy thông tin tài khoản
        print("\n📋 Đang lấy thông tin tài khoản...")
        account_info = fshare.get_user_info()
        if account_info["status"] == "success":
            print(f"📧 Email: {account_info.get('email', 'N/A')}")
            print(f"💎 Loại tài khoản: {account_info.get('account_type', 'N/A')}")
            print(f"⭐ Điểm: {account_info.get('totalpoints', 'N/A')}")
            print(f"💾 Dung lượng: {account_info.get('webspace_used_gb', 'N/A')} GB / {account_info.get('webspace_gb', 'N/A')} GB")
            print(f"📅 Hạn VIP: {account_info.get('expire_vip_formatted', 'N/A')} (timestamp: {account_info.get('expire_vip', 'N/A')})")
        
        # Lặp để getlink nhiều file hoặc xử lý folder
        while True:
            print("\n" + "="*60)
            print("Chọn hành động:")
            print("1. Getlink một file")
            print("2. Xem danh sách file trong folder")
            print("3. Lấy tất cả file từ folder (không đệ quy)")
            print("4. Lấy tất cả file từ folder (có đệ quy)")
            print("5. Lấy download link cho tất cả file trong folder")
            print("6. Xóa tất cả download session (giải quyết lỗi 471)")
            print("7. Upload file lên Fshare")
            print("q. Thoát")
            
            choice = input("\nNhập lựa chọn (1-7/q): ").strip().lower()
            
            if choice == 'q':
                break
            
            if choice not in ['1', '2', '3', '4', '5', '6', '7']:
                print("⚠️ Lựa chọn không hợp lệ!")
                continue
            
            # Xử lý các option không cần URL trước
            if choice == '6':
                # Xóa tất cả download session
                confirm = input("Bạn có chắc chắn muốn xóa tất cả download session? (y/n): ").strip().lower()
                if confirm != 'y':
                    print("Đã hủy")
                    continue
                
                # Lấy account_id nếu chưa có
                account_id = fshare.account_id
                if not account_id:
                    print("📥 Đang lấy account ID...")
                    user_info = fshare.get_user_info()
                    if user_info.get("status") == "success":
                        account_id = user_info.get("account_id")
                        fshare.account_id = account_id
                        if account_id:
                            print(f"✅ Account ID: {account_id}")
                
                result = fshare.delete_all_download_sessions(account_id=account_id)
                
                if result["status"] == "success":
                    print(f"\n✅ {result.get('message', 'Thành công')}")
                elif result["status"] == "otp_required":
                    print(f"\n⚠️ {result.get('message', 'Yêu cầu OTP')}")
                    print("💡 Bạn có thể:")
                    print("   1. Vào trang https://www.fshare.vn/account/security để xóa thủ công")
                    print("   2. Hoặc sử dụng web interface với OTP")
                elif result["status"] == "otp_error":
                    print(f"\n❌ {result.get('message', 'Lỗi khi lấy OTP')}")
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
                continue
            
            elif choice == '7':
                # Upload file lên Fshare (chỉ dùng resume)
                file_path = input("Nhập đường dẫn file cần upload: ").strip()
                
                if not file_path:
                    print("⚠️ Đường dẫn file không được để trống!")
                    continue
                
                upload_path = input("Nhập đường dẫn thư mục đích trên Fshare (mặc định: /): ").strip()
                if not upload_path:
                    upload_path = "/"
                
                secured_input = input("File có bảo mật? (y/n, mặc định: y): ").strip().lower()
                secured = 1 if (secured_input == '' or secured_input == 'y') else 0
                
                # Upload với resume (chức năng duy nhất)
                result = fshare.upload_file_with_resume(
                    file_path=file_path,
                    upload_path=upload_path,
                    secured=secured
                )
                
                if result["status"] == "success":
                    print(f"\n✅ {result.get('message', 'Upload thành công')}")
                    print(f"📁 File: {result.get('file_name', 'N/A')}")
                    print(f"💾 Kích thước: {result.get('file_size', 0) / (1024**2):.2f} MB")
                    if result.get("fshare_link"):
                        print(f"🔗 Link Fshare: {result.get('fshare_link')}")
                elif result["status"] == "paused":
                    print(f"\n⚠️ {result.get('message', 'Upload bị dừng')}")
                    print(f"💾 File resume: {result.get('resume_file', 'N/A')}")
                    print(f"📊 Đã upload: {result.get('uploaded_bytes', 0) / (1024**2):.2f} MB")
                    print(f"💡 Chạy lại để tiếp tục upload từ vị trí đã dừng")
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
                continue
            
            # Các option 1-5 cần URL
            fshare_url = input("Nhập URL Fshare: ").strip()
            
            if not fshare_url:
                print("⚠️ URL không được để trống!")
                continue
            
            # Kiểm tra URL hợp lệ
            if 'fshare.vn' not in fshare_url:
                print("⚠️ URL không hợp lệ! Phải chứa 'fshare.vn'")
                continue
            
            if choice == '1':
                # Getlink một file
                result = fshare.get_download_link(fshare_url)
                
                if result["status"] == "success":
                    print(f"\n✅ Thành công!")
                    print(f"🔗 Download URL: {result.get('download_url', 'N/A')}")
                elif result["status"] == "password_required":
                    print(f"\n🔒 File này yêu cầu mật khẩu")
                    password = input("Nhập mật khẩu file: ").strip()
                    if password:
                        result = fshare.get_download_link(fshare_url, password)
                        if result["status"] == "success":
                            print(f"\n✅ Thành công!")
                            print(f"🔗 Download URL: {result.get('download_url', 'N/A')}")
                        else:
                            print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
            
            elif choice == '2':
                # Xem danh sách file trong folder (tự động lấy tất cả với limit 10000)
                print("📥 Đang lấy danh sách file và folder...")
                result = fshare.get_folder_list(fshare_url, page_index=0, limit=10000)
                
                if result["status"] == "success":
                    items = result.get("items", [])
                    print(f"\n✅ Tìm thấy {len(items)} items:")
                    print("-" * 60)
                    for idx, item in enumerate(items, 1):
                        icon = "📁" if item["is_folder"] else "📄"
                        print(f"{idx}. {icon} {item['name']} ({item['size_str']})")
                        print(f"   URL: {item['url']}")
                    print("-" * 60)
                    
                    if result.get("has_more"):
                        print(f"\n⚠️ Còn items khác (vượt quá giới hạn 10000 items). Sử dụng lựa chọn 3 hoặc 4 để lấy tất cả.")
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
            
            elif choice == '3':
                # Lấy tất cả file từ folder (không đệ quy)
                result = fshare.get_all_files_from_folder(fshare_url, recursive=False)
                
                if result["status"] == "success":
                    files = result.get("files", [])
                    folders = result.get("folders", [])
                    
                    print(f"\n✅ Tổng kết:")
                    print(f"📁 Folder: {len(folders)}")
                    print(f"📄 File: {len(files)}")
                    print("\n📄 Danh sách file:")
                    print("-" * 60)
                    for idx, file_item in enumerate(files, 1):
                        print(f"{idx}. {file_item['name']} ({file_item['size_str']})")
                        print(f"   URL: {file_item['url']}")
                    print("-" * 60)
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
            
            elif choice == '4':
                # Lấy tất cả file từ folder (có đệ quy)
                depth = input("Nhập độ sâu tối đa (mặc định: 100): ").strip()
                max_depth = int(depth) if depth.isdigit() else 100
                
                result = fshare.get_all_files_from_folder(fshare_url, recursive=True, max_depth=max_depth)
                
                if result["status"] == "success":
                    files = result.get("files", [])
                    folders = result.get("folders", [])
                    
                    print(f"\n✅ Tổng kết:")
                    print(f"📁 Folder: {len(folders)}")
                    print(f"📄 File: {len(files)}")
                    print("\n📄 Danh sách file (có đệ quy):")
                    print("-" * 60)
                    for idx, file_item in enumerate(files, 1):
                        indent = "  " * file_item.get("depth", 0)
                        print(f"{idx}. {indent}{file_item['name']} ({file_item['size_str']})")
                        print(f"   {indent}URL: {file_item['url']}")
                    print("-" * 60)
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
            
            elif choice == '5':
                # Lấy download link cho tất cả file trong folder
                recursive = input("Có đệ quy vào folder con? (y/n, mặc định: n): ").strip().lower() == 'y'
                depth = input("Nhập độ sâu tối đa nếu đệ quy (mặc định: 100): ").strip()
                max_depth = int(depth) if depth.isdigit() else 100
                
                result = fshare.get_download_links_from_folder(
                    fshare_url, 
                    recursive=recursive, 
                    max_depth=max_depth
                )
                
                if result["status"] == "success":
                    files_with_links = result.get("files_with_links", [])
                    
                    print(f"\n✅ Hoàn tất!")
                    print(f"📊 Thống kê:")
                    print(f"   ✅ Thành công: {result.get('success_count', 0)}")
                    print(f"   ❌ Lỗi: {result.get('error_count', 0)}")
                    print(f"\n📄 Danh sách file với download link:")
                    print("-" * 60)
                    for idx, file_item in enumerate(files_with_links, 1):
                        status_icon = "✅" if file_item.get("getlink_status") == "success" else "❌"
                        print(f"{idx}. {status_icon} {file_item['name']} ({file_item['size_str']})")
                        if file_item.get("download_url"):
                            print(f"   🔗 {file_item['download_url']}")
                        else:
                            print(f"   ❌ {file_item.get('error_message', 'Unknown error')}")
                    print("-" * 60)
                else:
                    print(f"\n❌ Lỗi: {result.get('message', 'Lỗi không xác định')}")
            
        
        # Đăng xuất
        print("\n📤 Đang đăng xuất...")
        fshare.logout()
    else:
        print(f"\n❌ Đăng nhập thất bại: {login_result.get('message', 'Lỗi không xác định')}")


if __name__ == "__main__":
    main()

