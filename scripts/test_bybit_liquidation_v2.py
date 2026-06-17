"""
Test Bybit Liquidation - endpoint chuẩn theo docs mới nhất
"""
import requests
from datetime import datetime, timezone

start_ms = int(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
end_ms = int(datetime(2024, 6, 2, tzinfo=timezone.utc).timestamp() * 1000)

print("🔍 TEST BYBIT LIQUIDATION (endpoint chuẩn)")

url = "https://api.bybit.com/v5/market/liquidation"
params = {
    'category': 'linear',
    'symbol': 'BTCUSDT',
    'startTime': start_ms,
    'endTime': end_ms,
    'limit': 5
}

try:
    resp = requests.get(url, params=params, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")