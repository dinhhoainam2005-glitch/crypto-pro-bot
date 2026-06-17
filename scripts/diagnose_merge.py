"""
Chẩn đoán lỗi merge dữ liệu
- Kiểm tra index, overlap, NaN của từng nguồn
- Không sửa gì cả, chỉ quan sát
"""
import pandas as pd
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")

# Load từng file
perp = pd.read_parquet(os.path.join(DATA_DIR, "btc_perp_1h.parquet"))
spot = pd.read_parquet(os.path.join(DATA_DIR, "btc_spot_1h.parquet"))
funding = pd.read_parquet(os.path.join(DATA_DIR, "btc_funding_1h.parquet"))
oi = pd.read_parquet(os.path.join(DATA_DIR, "btc_open_interest_1h.parquet"))
cvd = pd.read_parquet(os.path.join(DATA_DIR, "btc_cvd_1h.parquet"))

print("="*60)
print("🔍 CHẨN ĐOÁN DỮ LIỆU")
print("="*60)

for name, d in [("Perp", perp), ("Spot", spot), ("Funding", funding), ("OI", oi), ("CVD", cvd)]:
    print(f"\n📄 {name}:")
    print(f"   Shape: {d.shape}")
    print(f"   Index type: {type(d.index)}")
    print(f"   Index dtype: {d.index.dtype}")
    print(f"   Time range: {d.index[0]} → {d.index[-1]}")
    print(f"   Tần suất index: {d.index[1] - d.index[0]}")
    print(f"   NaN count: {d.isna().sum().sum()}")
    print(f"   Duplicate index: {d.index.duplicated().sum()}")
    if hasattr(d.index, 'tz'):
        print(f"   Timezone: {d.index.tz}")
    # In vài index đầu và cuối
    print(f"   First 3 index: {list(d.index[:3])}")
    print(f"   Last 3 index: {list(d.index[-3:])}")

# Kiểm tra overlap thời gian
print(f"\n🔗 OVERLAP:")
print(f"   Perp & Funding: {(perp.index.min() <= funding.index.max()) and (funding.index.min() <= perp.index.max())}")
print(f"   Perp & OI: {(perp.index.min() <= oi.index.max()) and (oi.index.min() <= perp.index.max())}")

# Test merge nhỏ
test_merge = perp.join(funding, how='inner')
print(f"\n🔧 TEST MERGE Perp + Funding (inner): {len(test_merge)} nến")
test_merge2 = perp.join(oi, how='inner')
print(f"🔧 TEST MERGE Perp + OI (inner): {len(test_merge2)} nến")
test_merge3 = perp.join(funding, how='left').join(oi, how='left')
print(f"🔧 TEST MERGE Perp + Funding + OI (left): {len(test_merge3)} nến")
print(f"   NaN trong merge left: {test_merge3.isna().sum().sum()}")