"""
Test Telegram Bot - Gửi 1 tin nhắn test
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

print(f"Token: {TOKEN[:10]}...{TOKEN[-5:] if TOKEN else 'None'}")
print(f"Chat ID: {CHAT_ID}")

if not TOKEN or not CHAT_ID:
    print("❌ Thiếu TOKEN hoặc CHAT_ID trong .env")
    exit(1)

# Test 1: Kiểm tra kết nối
url = f"https://api.telegram.org/bot{TOKEN}/getMe"
resp = requests.get(url)
print(f"\nTest getMe: {resp.status_code}")
print(f"Response: {resp.json()}")

# Test 2: Gửi tin nhắn
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    'chat_id': CHAT_ID,
    'text': '🧪 Test tin nhắn từ Crypto Pro Bot!'
}
resp = requests.post(url, json=payload)
print(f"\nTest sendMessage: {resp.status_code}")
print(f"Response: {resp.json()}")

if resp.status_code == 200:
    print("\n✅ THÀNH CÔNG! Kiểm tra Telegram của bạn.")
else:
    print(f"\n❌ LỖI: {resp.json().get('description', 'Unknown error')}")
    print("Kiểm tra lại:")
    print("1. Bot Token có đúng không?")
    print("2. Đã gửi ít nhất 1 tin nhắn cho Bot chưa?")
    print("3. Chat ID có đúng không? Vào https://api.telegram.org/bot<TOKEN>/getUpdates để xem")