"""
Chẩn đoán: Xem dữ liệu thô Hyperliquid để tìm BTC fills
In 5 fills đầu tiên có coin='BTC' để biết cấu trúc thật
"""
import requests

print("🔍 Lấy fills từ Hyperliquid...")
resp = requests.post(
    "https://api.hyperliquid.xyz/info",
    json={"type": "userFills", "user": "0x0000000000000000000000000000000000000000"},
    timeout=30
)

fills = resp.json()
print(f"✅ Tổng fills: {len(fills)}")

# Lọc fills của BTC
btc_fills = [f for f in fills if f.get('coin') == 'BTC']
print(f"✅ BTC fills: {len(btc_fills)}")

# In 5 mẫu đầu tiên
print("\n📋 5 mẫu BTC fill đầu tiên:")
for i, f in enumerate(btc_fills[:5]):
    print(f"\n--- Fill {i+1} ---")
    for k, v in f.items():
        print(f"   {k}: {v}")

# Thống kê các dir có trong BTC fills
from collections import Counter
dirs = Counter(f.get('dir', '?') for f in btc_fills)
print(f"\n📊 Các loại dir trong BTC fills: {dirs}")