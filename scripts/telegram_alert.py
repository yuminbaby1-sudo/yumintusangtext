import urllib.request
import urllib.parse
import json

def send_telegram_alert(bot_token, chat_id, message_text):
    if not bot_token or not chat_id:
        return False, "未設定 Bot Token 或 Chat ID"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return True, "發送成功"
    except Exception as e:
        return False, f"發送失敗：{str(e)}"
