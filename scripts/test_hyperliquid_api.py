"""
Test Hyperliquid API cho Open Interest & Liquidation
- API public, không cần key
- 1 lần gọi duy nhất mỗi endpoint
"""
import requests
import time

BASE = "https://api.hyperliquid.xyz"

print("="*50)
print("🔍 TEST HYPERLIQUID API")

# Test 1: Metadata (lấy thông tin BTC perpetual)
print("\n1️⃣ Metadata BTC-USD:")
url = f"{BASE}/info"
payload = {"type": "meta"}
try:
    resp = requests.post(url, json=payload, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        universe = data.get('universe', [])
        # Tìm BTC
        for asset in universe:
            if asset.get('name') == 'BTC':
                print(f"   ✅ Tìm thấy BTC:")
                print(f"      MaxLeverage: {asset.get('maxLeverage')}")
                print(f"      SzDecimals: {asset.get('szDecimals')}")
                print(f"      Index: {asset.get('index')}")
                btc_index = asset.get('index')
                break
        else:
            btc_index = None
            print("   ⚠️ Không tìm thấy BTC trong universe")
    else:
        print(f"   ❌ {resp.text[:200]}")
        btc_index = None
except Exception as e:
    print(f"   ❌ Exception: {e}")
    btc_index = None

# Test 2: Open Interest (dùng endpoint khác - lấy từ perpetual metadata)
print("\n2️⃣ Open Interest (từ market summary):")
# Hyperliquid cung cấp OI qua endpoint l2 snapshot hoặc qua frontend API
# Endpoint: /info với type "meta" đã có open interest trong trường "openInterest" 
# nếu dùng đúng endpoint
url = f"{BASE}/info"
payload = {"type": "metaAndAssetCtxs"}
try:
    resp = requests.post(url, json=payload, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        # Kiểm tra cấu trúc
        if isinstance(data, list) and len(data) >= 2:
            universe = data[0].get('universe', [])
            asset_ctxs = data[1]
            for asset in universe:
                if asset.get('name') == 'BTC':
                    idx = asset.get('index')
                    if idx is not None and idx < len(asset_ctxs):
                        ctx = asset_ctxs[idx]
                        print(f"   ✅ Open Interest: {ctx.get('openInterest', 'N/A')}")
                        print(f"   ✅ Funding Rate: {ctx.get('funding', 'N/A')}")
                        print(f"   ✅ Mark Price: {ctx.get('markPx', 'N/A')}")
                        print(f"   Full ctx mẫu: {ctx}")
                    else:
                        print(f"   ⚠️ idx={idx} vượt quá asset_ctxs length={len(asset_ctxs)}")
                    break
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

# Test 3: Liquidation data (Hyperliquid lưu trên chain)
print("\n3️⃣ Liquidation History (thử qua info API):")
# Hyperliquid có thể có endpoint khác cho liquidations
url = f"{BASE}/info"
payload = {"type": "userFills", "user": "0x0000000000000000000000000000000000000000"}  # dummy
try:
    resp = requests.post(url, json=payload, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ Response type: {type(data)}")
        print(f"   Length: {len(data) if isinstance(data, list) else 'N/A'}")
        if isinstance(data, list) and len(data) > 0:
            print(f"   Mẫu: {data[0]}")
    else:
        print(f"   ❌ {resp.text[:200]}")
except Exception as e:
    print(f"   ❌ Exception: {e}")

print("\n🏁 Test Hyperliquid hoàn tất.")