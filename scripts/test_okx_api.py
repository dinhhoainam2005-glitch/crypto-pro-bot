"""
Test OKX API cho Open Interest & Liquidation history
- 1 lần gọi duy nhất, in kết quả chi tiết
- Không retry, không vòng lặp
"""
import requests
from datetime import datetime, timezone

# OKX dùng Unix timestamp dạng giây
start_s = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
end_s = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp())

print("="*50)
print("🔍 TEST OKX API")

# Test 1: Open Interest history
print("\n1️⃣ Open Interest History:")
url = "https://www.okx.com/api/v5/rubik/stat/trading-data/contract-summary/open-interest-history"
params = {
    'instId': 'BTC-USDT-SWAP',
    'period': '1H',
    'begin': start_s,
    'end': end_s,
    'limit': '5'
}
try:
    resp = requests.get(url, params=params, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ THÀNH CÔNG - code: {data.get('code')}")
        result = data.get('data', [])
        print(f"   Số dòng: {len(result)}")
        if result:
            print(f"   Mẫu: {result[0]}")
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

# Test 2: Liquidation history
print("\n2️⃣ Liquidation History:")
url = "https://www.okx.com/api/v5/rubik/stat/trading-data/contract-summary/liquidation-history"
params = {
    'instId': 'BTC-USDT-SWAP',
    'period': '1H',
    'begin': start_s,
    'end': end_s,
    'limit': '5'
}
try:
    resp = requests.get(url, params=params, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ THÀNH CÔNG - code: {data.get('code')}")
        result = data.get('data', [])
        print(f"   Số dòng: {len(result)}")
        if result:
            print(f"   Mẫu: {result[0]}")
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

print("\n🏁 Test OKX hoàn tất.")