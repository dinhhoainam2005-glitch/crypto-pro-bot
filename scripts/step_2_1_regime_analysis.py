"""
Bước 2.1 - Phân tích dữ liệu & Phân loại Regime thị trường
- Load toàn bộ Data Lake
- Merge thành 1 DataFrame thống nhất
- Phân loại Regime: Bull / Bear / Sideway / High Vol / Low Vol
- Trực quan hóa tổng quan
- Lưu kết quả phân loại regime
"""

import pandas as pd
import numpy as np
from datetime import datetime
from tqdm import tqdm
import os
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 1. LOAD TOÀN BỘ DỮ LIỆU
# ============================================================
print("="*60)
print("📂 BƯỚC 2.1: LOAD DỮ LIỆU & PHÂN LOẠI REGIME")
print("="*60)

print("\n📥 Load dữ liệu...")

# Load Perp (chính cho bot futures)
perp = pd.read_parquet(os.path.join(DATA_DIR, "btc_perp_1h.parquet"))
print(f"   ✅ Perp: {len(perp)} nến | {perp.index[0]} → {perp.index[-1]}")

# Load Spot
spot = pd.read_parquet(os.path.join(DATA_DIR, "btc_spot_1h.parquet"))
print(f"   ✅ Spot: {len(spot)} nến | {spot.index[0]} → {spot.index[-1]}")

# Load Funding Rate
funding = pd.read_parquet(os.path.join(DATA_DIR, "btc_funding_1h.parquet"))
print(f"   ✅ Funding: {len(funding)} dòng | {funding.index[0]} → {funding.index[-1]}")

# Load Open Interest
oi = pd.read_parquet(os.path.join(DATA_DIR, "btc_open_interest_1h.parquet"))
print(f"   ✅ OI: {len(oi)} dòng | {oi.index[0]} → {oi.index[-1]}")

# Load CVD
cvd = pd.read_parquet(os.path.join(DATA_DIR, "btc_cvd_1h.parquet"))
print(f"   ✅ CVD: {len(cvd)} dòng | {cvd.index[0]} → {cvd.index[-1]}")

# ============================================================
# 2. MERGE THÀNH 1 DATAFRAME THỐNG NHẤT
# ============================================================
print("\n🔗 Merge dữ liệu...")

# Đổi tên cột để phân biệt nguồn
perp_cols = {c: f'perp_{c}' for c in perp.columns}
spot_cols = {c: f'spot_{c}' for c in spot.columns}

perp_renamed = perp.rename(columns=perp_cols)
spot_renamed = spot.rename(columns=spot_cols)

# Merge tuần tự
df = perp_renamed.join(spot_renamed, how='left', rsuffix='_spot')
df = df.join(funding, how='left')
df = df.join(oi, how='left')
df = df.join(cvd, how='left')

# Điền tên cột funding và oi nếu bị thiếu
if 'funding' not in df.columns:
    # Tìm cột funding từ file
    funding_col = [c for c in funding.columns if 'fund' in c.lower() or 'rate' in c.lower()]
    if funding_col:
        df['funding_rate'] = funding[funding_col[0]]
    else:
        df['funding_rate'] = funding.iloc[:, 0] if funding.shape[1] > 0 else np.nan
else:
    df['funding_rate'] = df['funding']

if 'oi' not in df.columns:
    oi_col = [c for c in oi.columns if 'oi' in c.lower() or 'open' in c.lower() or 'interest' in c.lower()]
    if oi_col:
        df['open_interest'] = oi[oi_col[0]]
    else:
        df['open_interest'] = oi.iloc[:, 0] if oi.shape[1] > 0 else np.nan
else:
    df['open_interest'] = df['oi']

# Đảm bảo các cột cần thiết
if 'cvd' not in df.columns:
    df['cvd'] = cvd['cvd'] if 'cvd' in cvd.columns else cvd.iloc[:, 0]
if 'delta_volume' not in df.columns:
    df['delta_volume'] = cvd['delta_volume'] if 'delta_volume' in cvd.columns else 0

print(f"   ✅ DataFrame thống nhất: {len(df)} dòng, {len(df.columns)} cột")
print(f"   📅 Khoảng thời gian: {df.index[0]} → {df.index[-1]}")
print(f"   📋 Các cột: {list(df.columns)}")

# ============================================================
# 3. TÍNH CÁC CHỈ BÁO PHÂN LOẠI REGIME
# ============================================================
print("\n📊 Tính toán chỉ báo regime...")

# Sử dụng giá close của perp làm giá chính
price = df['perp_close'].ffill()

# 3.1. Moving Averages
df['ma_50'] = price.rolling(50).mean()
df['ma_200'] = price.rolling(200).mean()
df['ma_50_slope'] = df['ma_50'].diff(20) / df['ma_50'].shift(20) * 100  # % thay đổi 20 nến

# 3.2. ADX (Average Directional Index) - phiên bản đơn giản
def calculate_adx(high, low, close, period=14):
    """Tính ADX thủ công không cần thư viện"""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    up = high.diff()
    down = -low.diff()
    
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    
    plus_di = 100 * pd.Series(plus_dm, index=price.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=price.index).rolling(period).mean() / atr
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)
    adx = dx.rolling(period).mean()
    return adx

df['adx'] = calculate_adx(df['perp_high'], df['perp_low'], df['perp_close'], period=14)

# 3.3. Volatility (ATR %)
df['atr'] = (df['perp_high'] - df['perp_low']).rolling(14).mean()
df['atr_pct'] = df['atr'] / price * 100  # ATR dạng % giá

# 3.4. Volatility percentile (50 ngày)
df['vol_percentile'] = df['atr_pct'].rolling(200).apply(
    lambda x: (x.iloc[-1] > x).sum() / len(x) * 100 if len(x) > 50 else np.nan,
    raw=False
)

# 3.5. CVD xu hướng
df['cvd_slope'] = df['cvd'].diff(50)  # Thay đổi CVD trong 50 nến

# 3.6. Funding rate extreme
df['funding_percentile'] = df['funding_rate'].rolling(500).apply(
    lambda x: (x.iloc[-1] > x).sum() / len(x) * 100 if len(x) > 100 else np.nan,
    raw=False
)

# ============================================================
# 4. PHÂN LOẠI REGIME
# ============================================================
print("\n🏷️ Phân loại Regime...")

def classify_regime(row):
    """
    Phân loại regime dựa trên MA, ADX, Volatility
    Trả về: uptrend / downtrend / sideway / high_vol / low_vol
    Ưu tiên: Vol > Trend > Range
    """
    ma50 = row.get('ma_50', np.nan)
    ma200 = row.get('ma_200', np.nan)
    adx = row.get('adx', np.nan)
    atr_pct = row.get('atr_pct', np.nan)
    vol_perc = row.get('vol_percentile', np.nan)
    price_val = row.get('perp_close', np.nan)
    ma50_slope = row.get('ma_50_slope', np.nan)
    
    if pd.isna(ma50) or pd.isna(ma200) or pd.isna(adx):
        return 'unknown'
    
    # 1. Volatility regimes (ưu tiên cao nhất)
    if not pd.isna(vol_perc):
        if vol_perc > 80:
            return 'high_vol'
        if vol_perc < 20:
            return 'low_vol'
    
    # 2. Sideway detection
    if adx < 20:
        return 'sideway'
    
    # 3. Trend detection
    if price_val > ma50 and price_val > ma200:
        if ma50 > ma200:
            return 'uptrend'
        else:
            return 'uptrend'  # Golden cross sắp xảy ra
    elif price_val < ma50 and price_val < ma200:
        if ma50 < ma200:
            return 'downtrend'
        else:
            return 'downtrend'  # Death cross sắp xảy ra
    
    # 4. Default
    return 'sideway'

# Áp dụng phân loại
df['regime'] = df.apply(classify_regime, axis=1)

# Forward fill unknown
df['regime'] = df['regime'].replace('unknown', np.nan).ffill()

# ============================================================
# 5. THỐNG KÊ REGIME
# ============================================================
print("\n📊 Phân phối Regime:")
regime_counts = df['regime'].value_counts()
regime_pct = df['regime'].value_counts(normalize=True) * 100
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    count = regime_counts.get(regime, 0)
    pct = regime_pct.get(regime, 0)
    bar = '█' * int(pct / 2)
    print(f"   {regime:12s}: {count:6d} nến ({pct:5.1f}%) {bar}")

# ============================================================
# 6. PHÂN TÍCH HIỆU SUẤT THEO REGIME
# ============================================================
print("\n📈 Hiệu suất giá theo Regime:")

df['return_1h'] = df['perp_close'].pct_change()
df['return_24h'] = df['perp_close'].pct_change(24)
df['return_7d'] = df['perp_close'].pct_change(168)

for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = df['regime'] == regime
    if mask.sum() > 0:
        avg_1h = df.loc[mask, 'return_1h'].mean() * 100
        avg_24h = df.loc[mask, 'return_24h'].mean() * 100
        avg_7d = df.loc[mask, 'return_7d'].mean() * 100
        vol = df.loc[mask, 'return_1h'].std() * np.sqrt(24) * 100  # Annualized daily vol
        print(f"   {regime:12s}: 1h={avg_1h:+.4f}% | 24h={avg_24h:+.2f}% | 7d={avg_7d:+.2f}% | Vol(daily)={vol:.1f}%")

# ============================================================
# 7. LƯU DỮ LIỆU ĐÃ XỬ LÝ
# ============================================================
print("\n💾 Lưu dữ liệu đã xử lý...")

processed_file = os.path.join(OUTPUT_DIR, "btc_merged_1h.parquet")
df.to_parquet(processed_file)
print(f"   ✅ {processed_file}")
print(f"   Kích thước: {os.path.getsize(processed_file) / (1024*1024):.2f} MB")

# Lưu riêng bảng regime
regime_file = os.path.join(OUTPUT_DIR, "btc_regime_1h.parquet")
df[['regime', 'adx', 'atr_pct', 'vol_percentile', 'ma_50', 'ma_200', 'perp_close']].to_parquet(regime_file)
print(f"   ✅ {regime_file}")

# ============================================================
# 8. TỔNG KẾT
# ============================================================
print("\n" + "="*60)
print("🎯 Hoàn thành Bước 2.1!")
print(f"   DataFrame: {len(df)} dòng × {len(df.columns)} cột")
print(f"   Regime đã phân loại: {df['regime'].nunique()} trạng thái")
print(f"   File: {processed_file}")
print("="*60)
print("\n👉 Sẵn sàng cho Bước 2.2: Quét Edge-001 (Funding Rate Extreme Reversion)")