"""
Bước 1.3 - Tính CVD & Volume Profile từ dữ liệu Perp thật
- CVD (Cumulative Volume Delta): Ước lượng buy/sell volume từ OHLCV 1h
- Volume Profile: Phân phối volume theo mức giá
- Nguồn: btc_perp_1h.parquet (dữ liệu thật Binance)
- Lưu: btc_cvd_1h.parquet, btc_volume_profile.parquet
"""

import pandas as pd
import numpy as np
from tqdm import tqdm
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
PERP_FILE = os.path.join(DATA_DIR, "btc_perp_1h.parquet")

# ============================================================
# KIỂM TRA DỮ LIỆU ĐẦU VÀO
# ============================================================
print("📂 Đọc dữ liệu Perp...")
df = pd.read_parquet(PERP_FILE)
print(f"   ✅ {len(df)} nến, từ {df.index[0]} đến {df.index[-1]}")
print(f"   Cột: {list(df.columns)}\n")

# ============================================================
# 1. TÍNH CVD (Cumulative Volume Delta)
# ============================================================
# Công thức ước lượng từ OHLCV:
# delta_volume = volume * (close - open) / (high - low) nếu high != low
# Nếu high == low: delta = 0 (không có biến động)
# CVD = tổng tích lũy của delta_volume
# Buy volume = volume - sell_volume
# Sell volume: nếu giá đóng > mở → phần volume bán = volume * (high - close)/(high - low)
# Đơn giản hơn: delta = volume * (2*close - high - low) / (high - low) khi high != low

print("🟡 Tính CVD (Cumulative Volume Delta)...")

def calculate_delta_volume(df):
    """Tính delta volume cho từng nến dựa trên OHLCV"""
    high_low_range = df['high'] - df['low']
    
    # Tránh chia cho 0
    mask = high_low_range > 0
    
    delta = pd.Series(0.0, index=df.index)
    
    # Với nến có range > 0: dùng công thức ước lượng
    # buy pressure = (close - open) / (high - low)
    # sell pressure = (open - close) / (high - low)
    # delta = volume * (buy_pressure - sell_pressure) = volume * 2*(close - open) / (high - low)
    # Nhưng công thức chuẩn hơn: delta = volume * ((close - low) - (high - close)) / (high - low)
    # = volume * (2*close - high - low) / (high - low)
    
    close = df.loc[mask, 'close']
    high = df.loc[mask, 'high']
    low = df.loc[mask, 'low']
    volume = df.loc[mask, 'volume']
    
    delta.loc[mask] = volume * (2 * close - high - low) / (high - low).replace(0, np.nan)
    delta = delta.fillna(0)
    
    return delta

df['delta_volume'] = calculate_delta_volume(df)
df['cvd'] = df['delta_volume'].cumsum()

print(f"   ✅ Delta volume range: [{df['delta_volume'].min():.2f}, {df['delta_volume'].max():.2f}]")
print(f"   ✅ CVD range: [{df['cvd'].min():.2f}, {df['cvd'].max():.2f}]\n")

# ============================================================
# 2. TÍNH VOLUME PROFILE
# ============================================================
print("🟡 Tính Volume Profile...")

# Chia giá thành các bin (mỗi bin ~$100 với BTC)
price_min = df['low'].min()
price_max = df['high'].max()
bin_size = 100  # $100 mỗi bin
num_bins = int((price_max - price_min) / bin_size) + 1

# Phân phối volume vào các bin giá cho từng nến
volume_profile = np.zeros(num_bins)
price_bins = np.linspace(price_min, price_max, num_bins + 1)
bin_centers = (price_bins[:-1] + price_bins[1:]) / 2

pbar = tqdm(total=len(df), desc="   Phân phối volume", unit="nến")
for idx, row in df.iterrows():
    low = row['low']
    high = row['high']
    volume = row['volume']
    
    # Tìm bin chứa low và high
    low_bin = max(0, int((low - price_min) / bin_size))
    high_bin = min(num_bins - 1, int((high - price_min) / bin_size))
    
    if low_bin <= high_bin:
        # Phân phối đều volume cho các bin trong range
        num_bins_touched = high_bin - low_bin + 1
        vol_per_bin = volume / num_bins_touched
        volume_profile[low_bin:high_bin + 1] += vol_per_bin
    
    pbar.update(1)
pbar.close()

# Tìm Point of Control (POC - mức giá có volume cao nhất)
poc_idx = np.argmax(volume_profile)
poc_price = bin_centers[poc_idx]
print(f"   ✅ POC (Point of Control): ${poc_price:,.0f}")
print(f"   ✅ Volume tại POC: {volume_profile[poc_idx]:,.0f}\n")

# ============================================================
# 3. LƯU KẾT QUẢ
# ============================================================
print("💾 Lưu kết quả...")

# CVD
cvd_df = df[['cvd', 'delta_volume']].copy()
cvd_file = os.path.join(DATA_DIR, "btc_cvd_1h.parquet")
cvd_df.to_parquet(cvd_file)
print(f"   ✅ CVD: {cvd_file}")

# Volume Profile
vp_df = pd.DataFrame({
    'price_level': bin_centers,
    'volume': volume_profile,
    'volume_pct': volume_profile / volume_profile.sum() * 100
})
vp_file = os.path.join(DATA_DIR, "btc_volume_profile.parquet")
vp_df.to_parquet(vp_file)
print(f"   ✅ Volume Profile: {vp_file}")

# ============================================================
# 4. TỔNG KẾT
# ============================================================
print("\n" + "="*50)
print("📊 TỔNG KẾT DATA LAKE HIỆN TẠI:")
for f in sorted(os.listdir(DATA_DIR)):
    size_mb = os.path.getsize(os.path.join(DATA_DIR, f)) / (1024*1024)
    print(f"   📄 {f} ({size_mb:.2f} MB)")
print("="*50)
print("🎯 Hoàn thành Bước 1.3!")
print("   CVD và Volume Profile đã sẵn sàng.")
print("   Tiếp theo: Bước 1.4 - Test API Bybit/OKX cho OI & Liquidation.")