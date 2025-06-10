import os
import requests
from urllib.parse import urljoin
from requests_toolbelt import MultipartEncoder
from uuid import uuid4
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

# ✅ 从环境变量读取配置
USERNAME = os.environ.get("ZHUIMI_USERNAME")
PASSWORD = os.environ.get("ZHUIMI_PASSWORD")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ✅ 网站基础配置
BASE_URL = "https://zhuimi.xn--v4q818bf34b.com/"
SESSION = requests.Session()

auth_token = "未知"
api_count = "未知"

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[通知] 未配置 Telegram Bot 环境变量，跳过发送。")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("[通知] Telegram 消息已发送。")
        else:
            print(f"[通知] Telegram 发送失败，状态码：{response.status_code}")
    except Exception as e:
        print(f"[通知异常] Telegram：{str(e)}")


def get_captcha():
    captcha_url = urljoin(BASE_URL, "/utils/captcha")
    SESSION.get(captcha_url)
    return "来抽奖吧"  # 如验证码变动请自行替换


def login():
    global auth_token, api_count

    if not USERNAME or not PASSWORD:
        print("❌ 未设置ZHUIMI_USERNAME或ZHUIMI_PASSWORD环境变量")
        print("用户名：" + USERNAME + "密码：" + PASSWORD)
        send_telegram("❌ 未设置ZHUIMI_USERNAME或ZHUIMI_PASSWORD环境变量，登录失败")
        return False

    login_url = urljoin(BASE_URL, "/user/login")
    SESSION.get(login_url)
    captcha_token = get_captcha()

    boundary = f"----WebKitFormBoundary{uuid4().hex[:16]}"
    encoder = MultipartEncoder(
        fields={
            "username": USERNAME,
            "password": PASSWORD,
            "login_token": captcha_token
        },
        boundary=boundary
    )

    headers = {
        "Content-Type": encoder.content_type,
        "Referer": login_url,
        "User-Agent": "Mozilla/5.0",
        "Origin": BASE_URL
    }

    response = SESSION.post(
        urljoin(BASE_URL, "/user/doLogin"),
        data=encoder.to_string(),
        headers=headers
    )

    try:
        login_data = response.json()
        if login_data.get('success'):
            auth_token = login_data.get('data', {}).get('token', '未知')
            user_info = login_data.get('data', {}).get('user', {})
            api_count = user_info.get('api_count', '未知')
            return True
    except ValueError:
        pass

    print("登录失败")
    print("响应内容:", response.text)
    return False


def main():
    if not login():
        send_telegram("❌ 登录失败，请检查账号、密码或验证码是否过期。")
        return

    # 当前北京时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

    # 获取 API 信息
    try:
        headers = {
            "Referer": urljoin(BASE_URL, "/user/login"),
            "User-Agent": "Mozilla/5.0",
            "Upgrade-Insecure-Requests": "1"
        }

        response = SESSION.get(urljoin(BASE_URL, "/dashboard"), headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        tvbox_container = soup.select_one('#tvboxLinkContainer .endpoint-url code')
        api_link = tvbox_container.text.strip() if tvbox_container else soup.select_one('.endpoint-url code').text.strip()

        expire_element = soup.select_one('.expire-time')
        expire_time_str = expire_element.text.strip() if expire_element else "未知"

        expire_time = datetime.strptime(expire_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=beijing_tz)
        remaining_days = (expire_time - datetime.now(beijing_tz)).days + 1
    except Exception as e:
        api_link = "获取失败"
        expire_time_str = "获取失败"
        remaining_days = "未知"

    # 执行签到
    try:
        page_headers = {
            "Referer": urljoin(BASE_URL, "/dashboard"),
            "User-Agent": "Mozilla/5.0"
        }
        SESSION.get(urljoin(BASE_URL, "/signin"), headers=page_headers)

        api_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "Referer": urljoin(BASE_URL, "/signin"),
            "Origin": BASE_URL
        }

        api_response = SESSION.post(urljoin(BASE_URL, "/doSignin"), headers=api_headers, json={})
        print("签到响应：", api_response.text)
        
        if api_response.status_code == 200:
            result = api_response.json()
            if result.get("code") == 0:
                reward = result.get("data", {}).get("reward", "?")
                sign_msg = f"🎉 签到成功，奖励：{reward} 次API调用"
            else:
                sign_msg = f"⚠️ 签到失败：{result.get('message')}"
        else:
            sign_msg = f"❌ 签到失败，状态码：{api_response.status_code}"
    except Exception as e:
        sign_msg = f"⚠️ 签到异常：{str(e)}"

    # 整合消息并发送
    telegram_msg = f"""📅 *逐觅签到通知*

👤 用户名：{USERNAME}
🔐 Token：{auth_token}
🔗 专属链接：{api_link}
📆 到期时间：{expire_time_str}
📊 剩余天数：{remaining_days} 天
🧮 剩余API次数：{api_count}  次

{sign_msg}
🕒 时间：{now}
"""
    print(telegram_msg)
    send_telegram(telegram_msg)


if __name__ == "__main__":
    main()
