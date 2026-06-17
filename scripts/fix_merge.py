"""
Sửa lỗi merge dữ liệu - Forward fill Funding & OI
- Merge Perp + Funding + OI + CVD đúng cách
- Forward fill các giá trị NaN
- Kiểm tra kết quả từng bước
- Lưu file merged mới
"""

import pandas as pd
import numpy as np
from tqdm import tqdm
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# ============================================================
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("🔧 SỬA MERGE DỮ LIỆU")
print("="*60)

print("\n📥 Load dữ liệu...")
perp = pd.read_parquet(os.path.join(DATA_DIR, "btc_perp_1h.parquet"))
funding = pd.read_parquet(os.path.join(DATA_DIR, "btc_funding_1h.parquet"))
oi = pd.read_parquet(os.path.join(DATA_DIR, "btc_open_interest_1h.parquet"))
cvd = pd.read_parquet(os.path.join(DATA_DIR, "btc_cvd_1h.parquet"))

print(f"   Perp: {len(perp)} nến")
print(f"   Funding: {len(funding)} dòng (tần suất ~8h)")
print(f"   OI: {len(oi)} dòng (tần suất 1h)")
print(f"   CVD: {len(cvd)} dòng (tần suất 1h)")

# ============================================================
# 2. CHUẨN HÓA CỘT
# ============================================================
print("\n🔧 Chuẩn hóa cột...")

# Perp: giữ nguyên, đổi tên
perp_cols = {
    'open': 'perp_open',
    'high': 'perp_high',
    'low': 'perp_low',
    'close': 'perp_close',
    'volume': 'perp_volume'
}
perp = perp.rename(columns=perp_cols)

# Funding: lấy đúng cột fundingRate
if 'fundingRate' in funding.columns:
    funding = funding[['fundingRate']].copy()
    funding.columns = ['funding_rate']
elif 'funding_rate' in funding.columns:
    funding = funding[['funding_rate']].copy()
else:
    # Thử lấy cột đầu tiên là số
    num_cols = funding.select_dtypes(include=[np.number]).columns
    funding = funding[[num_cols[0]]].copy()
    funding.columns = ['funding_rate']

print(f"   Funding column: {list(funding.columns)}")
print(f"   Funding sample: {funding['funding_rate'].iloc[:3].values}")

# OI: lấy cột oi
if 'oi' in oi.columns:
    oi = oi[['oi']].copy()
elif 'openInterest' in oi.columns:
    oi = oi[['openInterest']].copy()
    oi.columns = ['oi']
else:
    oi = oi[[oi.columns[0]]].copy()
    oi.columns = ['oi']

print(f"   OI column: {list(oi.columns)}")
print(f"   OI sample: {oi['oi'].iloc[:3].values}")

# CVD: giữ nguyên
if 'cvd' in cvd.columns and 'delta_volume' in cvd.columns:
    cvd = cvd[['cvd', 'delta_volume']].copy()
else:
    cvd_cols = cvd.columns[:2]
    cvd = cvd[[cvd_cols[0], cvd_cols[1]]].copy()
    cvd.columns = ['cvd', 'delta_volume']

# ============================================================
# 3. MERGE + FORWARD FILL
# ============================================================
print("\n🔗 Merge dữ liệu...")

# Merge tuần tự bằng left join
df = perp.copy()
df = df.join(funding, how='left')
df = df.join(oi, how='left')
df = df.join(cvd, how='left')

print(f"   Sau merge: {len(df)} nến, {df.columns.tolist()}")

# Đếm NaN trước khi fill
nan_before = df.isna().sum()
print(f"\n📊 NaN trước khi forward fill:")
for col in ['funding_rate', 'oi', 'cvd', 'delta_volume']:
    if col in df.columns:
        print(f"   {col}: {nan_before.get(col, 0)} NaN ({nan_before.get(col, 0)/len(df)*100:.1f}%)")

# Forward fill - đây là bước QUAN TRỌNG
print(f"\n🔄 Forward fill...")
df['funding_rate'] = df['funding_rate'].ffill()
df['oi'] = df['oi'].ffill()
df['cvd'] = df['cvd'].ffill()
df['delta_volume'] = df['delta_volume'].ffill()

# Kiểm tra NaN còn lại sau forward fill
nan_after = df.isna().sum()
print(f"\n📊 NaN sau khi forward fill:")
for col in ['funding_rate', 'oi', 'cvd', 'delta_volume']:
    if col in df.columns:
        remaining = nan_after.get(col, 0)
        print(f"   {col}: {remaining} NaN ({remaining/len(df)*100:.1f}%)")

# ============================================================
# 4. KIỂM TRA CHẤT LƯỢNG
# ============================================================
print(f"\n✅ KIỂM TRA CHẤT LƯỢNG:")

# Số nến có đủ dữ liệu
complete = df.dropna(subset=['funding_rate', 'oi', 'cvd'])
print(f"   Nến đầy đủ: {len(complete)} / {len(df)} ({len(complete)/len(df)*100:.1f}%)")

# Khoảng thời gian
print(f"   Thời gian: {df.index[0]} → {df.index[-1]}")

# Kiểm tra funding rate hợp lý
fr = df['funding_rate'].dropna()
print(f"   Funding rate: min={fr.min():.6f}, max={fr.max():.6f}, mean={fr.mean():.6f}")

# Kiểm tra OI hợp lý
oi_vals = df['oi'].dropna()
print(f"   OI: min={oi_vals.min():,.0f}, max={oi_vals.max():,.0f}, mean={oi_vals.mean():,.0f}")

# Kiểm tra CVD hợp lý
cvd_vals = df['cvd'].dropna()
print(f"   CVD: min={cvd_vals.min():,.0f}, max={cvd_vals.max():,.0f}")

# Forward fill có làm sai lệch không?
# So sánh funding rate gốc vs forward-filled tại các thời điểm funding thật
funding_original = funding.dropna()
common_idx = df.index.intersection(funding_original.index)
if len(common_idx) > 0:
    diff = (df.loc[common_idx, 'funding_rate'] - funding_original.loc[common_idx, 'funding_rate']).abs()
    print(f"\n🔍 Sai khác funding rate tại {len(common_idx)} điểm gốc:")
    print(f"   Max diff: {diff.max():.10f}")
    print(f"   Mean diff: {diff.mean():.10f}")
    print(f"   Diff = 0: {(diff == 0).sum()} / {len(diff)}")

# ============================================================
# 5. LƯU FILE MỚI
# ============================================================
print(f"\n💾 Lưu file merged mới...")

output_path = os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet")
df.to_parquet(output_path)
file_size = os.path.getsize(output_path) / (1024*1024)
print(f"   ✅ {output_path}")
print(f"   Kích thước: {file_size:.2f} MB")
print(f"   Số dòng: {len(df)}")
print(f"   Số cột: {len(df.columns)}")
print(f"   Các cột: {list(df.columns)}")

print(f"\n🎯 Hoàn thành sửa merge!")
print(f"   File mới: btc_merged_1h_v2.parquet")
print(f"   Sẵn sàng chạy lại EDA trên dữ liệu đầy đủ.")