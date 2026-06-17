import requests
import json
from datetime import datetime, timedelta

API_KEY = "bd55add9779d4c238d54ad33b1eed09d"
BASE_URL = "https://open-api-v3.coinglass.com"

headers = {
    "accept": "application/json",
    "coinglassSecret": API_KEY
}

def test_endpoint(url, params, name):
    """Test 1 endpoint và in kết quả"""
    print(f"\n{'='*50}")
    print(f"🔍 Test: {name}")
    print(f"   URL: {url}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                print(f"   ✅ THÀNH CÔNG - Trả về {len(data)} dòng")
                if len(data) > 0:
                    print(f"   Mẫu dòng đầu: {json.dumps(data[0], indent=4)[:300]}")
            elif isinstance(data, dict):
                print(f"   ✅ THÀNH CÔNG - Trả về dict với {len(data)} keys")
                print(f"   Keys: {list(data.keys())[:10]}")
            else:
                print(f"   ⚠️ Định dạng lạ: {type(data)}")
        elif resp.status_code == 401:
            print(f"   ❌ 401 Unauthorized - API key không có quyền (gói miễn phí không hỗ trợ)")
        elif resp.status_code == 429:
            print(f"   ❌ 429 Rate Limit - Vượt giới hạn gọi")
        else:
            print(f"   ❌ Lỗi khác: {resp.text[:200]}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")

# ============================================
# Test 1: Open Interest History (BTC, 1h)
# ============================================
test_endpoint(
    url=f"{BASE_URL}/api/futures/openInterestHistory",
    params={
        "symbol": "BTC",
        "interval": "1h",
        "limit": 5
    },
    name="Open Interest History (1h)"
)

# ============================================
# Test 2: Liquidation History (BTC, 1h)
# ============================================
test_endpoint(
    url=f"{BASE_URL}/api/futures/liquidationHistory",
    params={
        "symbol": "BTC",
        "interval": "1h",
        "limit": 5
    },
    name="Liquidation History (1h)"
)

# ============================================
# Test 3: Funding Rate History (aggregate)
# ============================================
test_endpoint(
    url=f"{BASE_URL}/api/futures/fundingRateHistory",
    params={
        "symbol": "BTC",
        "interval": "1h",
        "limit": 5
    },
    name="Funding Rate History (aggregate)"
)

# ============================================
# Test 4: Open Interest (tất cả sàn) - snapshot
# ============================================
test_endpoint(
    url=f"{BASE_URL}/api/futures/openInterest",
    params={
        "symbol": "BTC",
    },
    name="Open Interest (snapshot tổng)"
)

print(f"\n{'='*50}")
print("🏁 Test hoàn tất. Xem kết quả trên để biết endpoint nào khả dụng.")