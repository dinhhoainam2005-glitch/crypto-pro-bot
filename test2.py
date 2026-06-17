import os
import requests

# KHÔNG dùng dotenv, đọc thủ công
env_vars = {}
with open('.env', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            env_vars[key.strip()] = value.strip()

TOKEN = env_vars.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = env_vars.get('TELEGRAM_CHAT_ID')

print(f"Token: {TOKEN}")
print(f"Chat ID: {CHAT_ID}")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
resp = requests.post(url, json={'chat_id': CHAT_ID, 'text': '🧪 Test từ Crypto Pro Bot!'})
print(f"Status: {resp.status_code}")
print(f"Response: {resp.json()}")