"""
In tất cả dir có trong Hyperliquid fills để tìm liquidation
"""
import requests
from collections import Counter

resp = requests.post(
    "https://api.hyperliquid.xyz/info",
    json={"type": "userFills", "user": "0x0000000000000000000000000000000000000000"},
    timeout=30
)
fills = resp.json()

# Thống kê TẤT CẢ các dir
dirs = Counter(f.get('dir', 'None') for f in fills)
print("📊 Tất cả dir trong fills:")
for d, count in dirs.most_common():
    print(f"   {d}: {count}")

# Thống kê TẤT CẢ các coin
coins = Counter(f.get('coin', 'None') for f in fills)
print(f"\n📊 Tất cả coin trong fills (top 20):")
for c, count in coins.most_common(20):
    print(f"   {c}: {count}")

# In 3 fill đầu tiên để xem cấu trúc
print("\n📋 3 fill đầu tiên:")
for f in fills[:3]:
    print(f)