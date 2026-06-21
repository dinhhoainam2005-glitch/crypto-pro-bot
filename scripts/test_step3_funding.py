"""
TEST BƯỚC 3: FUNDING RATE RESAMPLE & FUND_RISING
- Kiểm tra funding rate có bị NaN sau resample không
- Kiểm tra FUND_RISING có hoạt động không
"""
import requests
import pandas as pd
import numpy as np

print("="*60)
print("🔍 TEST BƯỚC 3: FUNDING RATE & FUND_RISING")
print("="*60)

# ============================================================
# 1. LẤY FUNDING RATE GỐC (8h)
# ============================================================
print("\n📡 1. Funding Rate gốc từ Binance...")
url = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=100"
resp = requests.get(url, timeout=10)
fund_data = resp.json()
fund_df = pd.DataFrame(fund_data)
fund_df['timestamp'] = pd.to_datetime(fund_df['fundingTime'], unit='ms')
fund_df['funding_rate'] = fund_df['fundingRate'].astype(float)
fund_df.set_index('timestamp', inplace=True)
print(f"   ✅ {len(fund_df)} dòng funding rate (tần suất 8h)")
print(f"   Range: {fund_df['funding_rate'].min()*100:.4f}% → {fund_df['funding_rate'].max()*100:.4f}%")
print(f"   FUND_RISING (diff 1): {(fund_df['funding_rate'].diff() > 0).sum()} lần tăng")

# ============================================================
# 2. RESAMPLE VỀ 15M VÀ 1H
# ============================================================
print("\n📡 2. Resample về 15m và 1h...")

# Tạo DataFrame 15m rỗng
idx_15m = pd.date_range(fund_df.index[0], fund_df.index[-1], freq='15min')
df_15m = pd.DataFrame(index=idx_15m)
df_15m = df_15m.join(fund_df['funding_rate'], how='left')
nan_before = df_15m['funding_rate'].isna().sum()
df_15m['funding_rate'] = df_15m['funding_rate'].ffill()
nan_after = df_15m['funding_rate'].isna().sum()
print(f"   15m: {len(df_15m)} nến | NaN trước fill: {nan_before} | sau fill: {nan_after}")

# Tương tự 1h
idx_1h = pd.date_range(fund_df.index[0], fund_df.index[-1], freq='1h')
df_1h = pd.DataFrame(index=idx_1h)
df_1h = df_1h.join(fund_df['funding_rate'], how='left')
nan_before_1h = df_1h['funding_rate'].isna().sum()
df_1h['funding_rate'] = df_1h['funding_rate'].ffill()
nan_after_1h = df_1h['funding_rate'].isna().sum()
print(f"   1h:  {len(df_1h)} nến | NaN trước fill: {nan_before_1h} | sau fill: {nan_after_1h}")

# ============================================================
# 3. TEST FUND_RISING VỚI diff() GIỐNG BOT
# ============================================================
print("\n📡 3. Test FUND_RISING với diff()...")

for tf, df_tf, n_per_day in [('15m', df_15m, 96), ('1h', df_1h, 24)]:
    diff_window = max(1, n_per_day // 6)
    df_tf['funding_chg'] = df_tf['funding_rate'].diff(diff_window)
    df_tf['funding_rising'] = (df_tf['funding_chg'] > 0).astype(int)
    
    rising_count = df_tf['funding_rising'].sum()
    rising_pct = rising_count / len(df_tf) * 100
    zero_count = (df_tf['funding_chg'] == 0).sum()
    
    print(f"   {tf}: diff({diff_window})")
    print(f"      FUND_RISING=True: {rising_count}/{len(df_tf)} ({rising_pct:.1f}%)")
    print(f"      FUND_CHG=0: {zero_count}/{len(df_tf)} ({zero_count/len(df_tf)*100:.1f}%)")
    print(f"      FUND_CHG min/max: {df_tf['funding_chg'].min()*100:.6f}% / {df_tf['funding_chg'].max()*100:.6f}%")
    
    if rising_pct < 5:
        print(f"      ⚠️ FUND_RISING quá ít! Edge dùng FUND_RISING gần như không kích hoạt")
    elif rising_pct > 40:
        print(f"      ⚠️ FUND_RISING quá nhiều! Có thể nhiễu")
    else:
        print(f"      ✅ FUND_RISING hợp lý")

# ============================================================
# 4. SO SÁNH diff() CŨ vs MỚI
# ============================================================
print("\n📡 4. So sánh diff cũ (n_per_day//3) vs mới (n_per_day//6)...")

for tf, n_per_day in [('15m', 96), ('1h', 24)]:
    old_window = max(1, n_per_day // 3)
    new_window = max(1, n_per_day // 6)
    print(f"   {tf}: cũ={old_window} nến, mới={new_window} nến")

print(f"\n🎯 Hoàn thành Bước 3!")