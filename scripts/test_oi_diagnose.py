"""
Script chẩn đoán: Test 1 lần gọi API Open Interest từ Binance
In CHI TIẾT lỗi để biết nguyên nhân thực sự
"""
import requests
from datetime import datetime, timezone

# 1 lần gọi duy nhất với tháng 9/2019
start_ms = int(datetime(2019, 9, 8, tzinfo=timezone.utc).timestamp() * 1000)
end_ms = int(datetime(2019, 10, 8, tzinfo=timezone.utc).timestamp() * 1000)

url = "https://fapi.binance.com/fapi/v1/openInterestHist"
params = {
    'symbol': 'BTCUSDT',
    'period': '5m',
    'startTime': start_ms,
    'endTime': end_ms,
    'limit': 500
}

print("🔍 Gọi thử Binance Open Interest API...")
print(f"   URL: {url}")
print(f"   Params: {params}")

try:
    resp = requests.get(url, params=params, timeout=15)
    print(f"\n📡 HTTP Status: {resp.status_code}")
    print(f"📡 Response Headers: {dict(resp.headers)}\n")
    
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list):
            print(f"✅ THÀNH CÔNG! Nhận {len(data)} dòng.")
            if len(data) > 0:
                print(f"   Mẫu dòng đầu: {data[0]}")
        else:
            print(f"⚠️ Nhận được dict thay vì list:")
            print(f"   {data}")
    else:
        print(f"❌ LỖI HTTP {resp.status_code}:")
        print(f"   {resp.text}")
        
except Exception as e:
    print(f"❌ EXCEPTION: {type(e).__name__}: {e}")