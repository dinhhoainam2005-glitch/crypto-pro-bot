"""
Test Bybit API cho Open Interest & Liquidation history
- 1 lần gọi duy nhất, in kết quả chi tiết
- Không retry, không vòng lặp
"""
import requests
from datetime import datetime, timezone

start_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
end_ms = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)

print("="*50)
print("🔍 TEST BYBIT API")

# Test 1: Open Interest history
print("\n1️⃣ Open Interest History:")
url = "https://api.bybit.com/v5/market/open-interest"
params = {
    'category': 'linear',
    'symbol': 'BTCUSDT',
    'intervalTime': '1h',
    'startTime': start_ms,
    'endTime': end_ms,
    'limit': 5
}
try:
    resp = requests.get(url, params=params, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ THÀNH CÔNG - retCode: {data.get('retCode')}")
        result = data.get('result', {})
        if 'list' in result:
            print(f"   Số dòng: {len(result['list'])}")
            if result['list']:
                print(f"   Mẫu: {result['list'][0]}")
        else:
            print(f"   Keys result: {list(result.keys()) if result else 'None'}")
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

# Test 2: Liquidation history
print("\n2️⃣ Liquidation History:")
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
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ THÀNH CÔNG - retCode: {data.get('retCode')}")
        result = data.get('result', {})
        if 'list' in result:
            print(f"   Số dòng: {len(result['list'])}")
            if result['list']:
                print(f"   Mẫu: {result['list'][0]}")
        else:
            print(f"   Keys result: {list(result.keys()) if result else 'None'}")
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

print("\n🏁 Test Bybit hoàn tất.")