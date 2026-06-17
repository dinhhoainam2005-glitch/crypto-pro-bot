"""
Bước 2.2 - PHÂN TÍCH KHÁM PHÁ DỮ LIỆU (EDA) TOÀN DIỆN
- Phân phối từng biến
- Tương quan chéo, lead-lag
- Hành vi theo regime
- Cấu trúc thị trường: đỉnh/đáy OI, CVD
- Nhân quả: cái gì dẫn dắt cái gì?
"""

import pandas as pd
import numpy as np
from datetime import datetime
from tqdm import tqdm
import os
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDA_DIR = os.path.join(BASE_DIR, "data", "eda")
os.makedirs(EDA_DIR, exist_ok=True)

# ============================================================
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📊 PHÂN TÍCH KHÁM PHÁ DỮ LIỆU (EDA)")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h.parquet"))
print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")
print(f"📋 Cột: {list(df.columns)}")

# Tạo bản sao với các cột chuẩn hóa
eda = pd.DataFrame(index=df.index)
eda['price'] = df['perp_close']
eda['volume'] = df['perp_volume']
eda['funding'] = df['funding_rate']
eda['oi'] = df['open_interest']
eda['cvd'] = df['cvd']
eda['delta_vol'] = df['delta_volume']
eda['regime'] = df['regime']

# Loại bỏ NaN
eda = eda.dropna(subset=['price', 'funding', 'oi', 'cvd'])
print(f"✅ Dữ liệu sạch: {len(eda)} nến")

# ============================================================
# 2. PHÂN PHỐI TỪNG BIẾN
# ============================================================
print(f"\n{'='*40}")
print(f"📊 1. PHÂN PHỐI TỪNG BIẾN")
print(f"{'='*40}")

# Returns
eda['return_1h'] = eda['price'].pct_change()
eda['return_24h'] = eda['price'].pct_change(24)
eda['return_7d'] = eda['price'].pct_change(168)

print(f"\n📈 Price Returns:")
for col, label in [('return_1h', '1h'), ('return_24h', '24h'), ('return_7d', '7d')]:
    s = eda[col].dropna()
    print(f"   {label:4s}: mean={s.mean()*100:+.4f}% | std={s.std()*100:.2f}% | "
          f"skew={s.skew():+.2f} | kurt={s.kurtosis():+.2f} | "
          f"P1={np.percentile(s,1)*100:+.2f}% | P99={np.percentile(s,99)*100:+.2f}%")

print(f"\n💵 Funding Rate:")
s = eda['funding'].dropna()
print(f"   mean={s.mean()*100:.4f}% | std={s.std()*100:.4f}% | "
      f"P5={np.percentile(s,5)*100:.4f}% | P95={np.percentile(s,95)*100:.4f}% | "
      f"max={s.max()*100:.4f}% | min={s.min()*100:.4f}%")

print(f"\n📊 Open Interest:")
s = eda['oi'].dropna()
oi_chg = eda['oi'].pct_change(24).dropna()
print(f"   Current: {s.iloc[-1]:,.0f} | mean: {s.mean():,.0f} | max: {s.max():,.0f} | min: {s.min():,.0f}")
print(f"   OI 24h change: mean={oi_chg.mean()*100:+.3f}% | std={oi_chg.std()*100:.2f}% | "
      f"P5={np.percentile(oi_chg,5)*100:+.3f}% | P95={np.percentile(oi_chg,95)*100:+.3f}%")

print(f"\n📈 CVD:")
s = eda['cvd'].dropna()
print(f"   Current: {s.iloc[-1]:,.0f} | mean: {s.mean():,.0f} | max: {s.max():,.0f} | min: {s.min():,.0f}")

print(f"\n📊 Volume:")
s = eda['volume'].dropna()
print(f"   mean: {s.mean():,.0f} | median: {s.median():,.0f} | "
      f"P95: {np.percentile(s,95):,.0f} | P99: {np.percentile(s,99):,.0f}")

# ============================================================
# 3. TƯƠNG QUAN CHÉO & LEAD-LAG
# ============================================================
print(f"\n{'='*40}")
print(f"🔗 2. TƯƠNG QUAN CHÉO & LEAD-LAG")
print(f"{'='*40}")

# Tương quan đồng thời
corr_cols = ['return_1h', 'funding', 'oi', 'cvd', 'delta_vol', 'volume']
corr_df = eda[corr_cols].dropna()
corr_matrix = corr_df.corr()

print(f"\n📊 Ma trận tương quan (Pearson):")
print(f"   {'':>12} return_1h  funding    oi        cvd       delta_vol volume")
for col in corr_cols:
    vals = [f"{corr_matrix.loc[col, c]:+.3f}" for c in corr_cols]
    print(f"   {col:>12} " + " ".join(f"{v:>10}" for v in vals))

# Lead-Lag: Biến nào dẫn dắt biến nào?
print(f"\n⏱️ LEAD-LAG ANALYSIS (tương quan với độ trễ 1h-24h):")
print(f"   (Giá trị dương = biến X dẫn dắt return tương lai)")

for lag in [1, 6, 12, 24]:
    print(f"\n   --- Lag {lag}h ---")
    # Funding → Future Return
    corr_fund = eda['funding'].corr(eda['return_1h'].shift(-lag))
    # OI change → Future Return  
    oi_chg = eda['oi'].pct_change(24)
    corr_oi = oi_chg.corr(eda['return_1h'].shift(-lag))
    # Delta volume → Future Return
    corr_delta = eda['delta_vol'].corr(eda['return_1h'].shift(-lag))
    # CVD change → Future Return
    cvd_chg = eda['cvd'].diff(24)
    corr_cvd = cvd_chg.corr(eda['return_1h'].shift(-lag))
    # Volume → Future Return
    corr_vol = eda['volume'].corr(eda['return_1h'].shift(-lag))
    
    print(f"   Funding   → Return t+{lag:2d}h: {corr_fund:+.4f}")
    print(f"   OI chg    → Return t+{lag:2d}h: {corr_oi:+.4f}")
    print(f"   Delta Vol → Return t+{lag:2d}h: {corr_delta:+.4f}")
    print(f"   CVD chg   → Return t+{lag:2d}h: {corr_cvd:+.4f}")
    print(f"   Volume    → Return t+{lag:2d}h: {corr_vol:+.4f}")

# Ngược lại: Return → Future biến
print(f"\n📊 REVERSE: Return → Future Signals")
for lag in [1, 6, 12, 24]:
    corr = eda['return_1h'].corr(eda['funding'].shift(-lag))
    if abs(corr) > 0.01:
        print(f"   Return → Funding t+{lag:2d}h: {corr:+.4f}")

# ============================================================
# 4. HÀNH VI THEO REGIME
# ============================================================
print(f"\n{'='*40}")
print(f"🎯 3. HÀNH VI THEO REGIME")
print(f"{'='*40}")

for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = eda['regime'] == regime
    r = eda[mask]
    if len(r) < 50:
        continue
    
    print(f"\n   📌 {regime.upper()} (n={len(r):,})")
    print(f"   Return 24h: mean={r['return_24h'].mean()*100:+.3f}% | std={r['return_24h'].std()*100:.2f}%")
    print(f"   Funding:    mean={r['funding'].mean()*100:.4f}% | std={r['funding'].std()*100:.4f}%")
    
    oi_c = r['oi'].pct_change(24)
    print(f"   OI chg 24h: mean={oi_c.mean()*100:+.3f}% | std={oi_c.std()*100:.2f}%")
    
    cvd_c = r['cvd'].diff(24)
    print(f"   CVD chg 24h: mean={cvd_c.mean():+.0f} | std={cvd_c.std():.0f}")
    
    print(f"   Volume:      mean={r['volume'].mean():,.0f} | P95={np.percentile(r['volume'],95):,.0f}")
    
    # Tương quan Funding-Return trong regime này
    corr_fr = r['funding'].corr(r['return_24h'])
    print(f"   Corr(Funding, Return 24h): {corr_fr:+.3f}")

# ============================================================
# 5. CẤU TRÚC THỊ TRƯỜNG: ĐỈNH/ĐÁY
# ============================================================
print(f"\n{'='*40}")
print(f"🏔️ 4. CẤU TRÚC THỊ TRƯỜNG")
print(f"{'='*40}")

# Tìm đỉnh OI cục bộ và giá sau đó
eda['oi_peak'] = (eda['oi'] > eda['oi'].rolling(168).max().shift(1)).astype(int)  # Đỉnh OI 7 ngày
oi_peaks = eda[eda['oi_peak'] == 1]

if len(oi_peaks) > 0:
    print(f"\n📊 Đỉnh OI cục bộ (7 ngày): {len(oi_peaks)} lần")
    # Giá 24h, 72h, 168h sau đỉnh OI
    for horizon, label in [(24, '24h'), (72, '3d'), (168, '7d')]:
        future_ret = eda['price'].shift(-horizon) / eda['price'] - 1
        avg_after_peak = future_ret[oi_peaks.index].mean() * 100
        print(f"   Return {label} sau đỉnh OI: {avg_after_peak:+.2f}%")

# Tương tự cho đáy OI
eda['oi_trough'] = (eda['oi'] < eda['oi'].rolling(168).min().shift(1)).astype(int)
oi_troughs = eda[eda['oi_trough'] == 1]

if len(oi_troughs) > 0:
    print(f"\n📊 Đáy OI cục bộ (7 ngày): {len(oi_troughs)} lần")
    for horizon, label in [(24, '24h'), (72, '3d'), (168, '7d')]:
        future_ret = eda['price'].shift(-horizon) / eda['price'] - 1
        avg_after_trough = future_ret[oi_troughs.index].mean() * 100
        print(f"   Return {label} sau đáy OI: {avg_after_trough:+.2f}%")

# ============================================================
# 6. PHÂN TÍCH EXTREME EVENTS
# ============================================================
print(f"\n{'='*40}")
print(f"⚡ 5. PHÂN TÍCH SỰ KIỆN CỰC ĐOAN")
print(f"{'='*40}")

# Funding extreme (>P95) → giá sau đó?
fund_p95 = np.percentile(eda['funding'].dropna(), 95)
fund_p5 = np.percentile(eda['funding'].dropna(), 5)

eda['funding_extreme_high'] = eda['funding'] > fund_p95
eda['funding_extreme_low'] = eda['funding'] < fund_p5

for label, mask_col in [('Funding > P95', 'funding_extreme_high'), ('Funding < P5', 'funding_extreme_low')]:
    extreme = eda[eda[mask_col]]
    if len(extreme) > 0:
        print(f"\n   {label} (n={len(extreme)}):")
        for horizon in [1, 6, 12, 24, 72]:
            ret = eda['price'].shift(-horizon) / eda['price'] - 1
            avg = ret[extreme.index].mean() * 100
            wr = (ret[extreme.index] > 0).sum() / len(extreme) * 100
            print(f"   Return {horizon:3d}h sau: {avg:+.2f}% | WR={wr:.1f}%")

# Volume spike (>P99) → giá sau đó?
vol_p99 = np.percentile(eda['volume'].dropna(), 99)
eda['vol_spike'] = eda['volume'] > vol_p99
vol_spikes = eda[eda['vol_spike']]
if len(vol_spikes) > 0:
    print(f"\n   Volume > P99 (n={len(vol_spikes)}):")
    for horizon in [1, 6, 12, 24, 72]:
        ret = eda['price'].shift(-horizon) / eda['price'] - 1
        avg = ret[vol_spikes.index].mean() * 100
        wr = (ret[vol_spikes.index] > 0).sum() / len(vol_spikes) * 100
        print(f"   Return {horizon:3d}h sau: {avg:+.2f}% | WR={wr:.1f}%")

# ============================================================
# 7. PHÂN TÍCH XU HƯỚNG FUNDING
# ============================================================
print(f"\n{'='*40}")
print(f"📈 6. XU HƯỚNG FUNDING & GIÁ")
print(f"{'='*40}")

# Khi funding tăng/giảm liên tục 3 nến → giá sau đó?
eda['funding_dir'] = np.sign(eda['funding'].diff())
eda['funding_streak'] = (eda['funding_dir'] == eda['funding_dir'].shift(1)).astype(int) + \
                         (eda['funding_dir'] == eda['funding_dir'].shift(2)).astype(int)

streak_up = eda[(eda['funding_streak'] >= 2) & (eda['funding_dir'] > 0)]
streak_down = eda[(eda['funding_streak'] >= 2) & (eda['funding_dir'] < 0)]

print(f"\n   Funding tăng 3 nến liên tiếp (n={len(streak_up)}):")
for horizon in [1, 6, 12, 24]:
    ret = eda['price'].shift(-horizon) / eda['price'] - 1
    avg = ret[streak_up.index].mean() * 100
    wr = (ret[streak_up.index] > 0).sum() / len(streak_up) * 100
    print(f"   Return {horizon:2d}h sau: {avg:+.2f}% | WR={wr:.1f}%")

print(f"\n   Funding giảm 3 nến liên tiếp (n={len(streak_down)}):")
for horizon in [1, 6, 12, 24]:
    ret = eda['price'].shift(-horizon) / eda['price'] - 1
    avg = ret[streak_down.index].mean() * 100
    wr = (ret[streak_down.index] > 0).sum() / len(streak_down) * 100
    print(f"   Return {horizon:2d}h sau: {avg:+.2f}% | WR={wr:.1f}%")

# ============================================================
# 8. TỔNG KẾT PHÁT HIỆN
# ============================================================
print(f"\n{'='*60}")
print(f"🔍 TỔNG KẾT PHÁT HIỆN CHÍNH")
print(f"{'='*60}")

# Tự động phát hiện các mối quan hệ đáng chú ý
findings = []

# Funding - Return lead-lag
for lag in [1, 6, 12, 24]:
    c = eda['funding'].corr(eda['return_1h'].shift(-lag))
    if abs(c) > 0.01:
        findings.append(f"Funding → Return t+{lag}h: r={c:+.4f}")

# OI extreme
if len(oi_peaks) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[oi_peaks.index].mean() * 100
    findings.append(f"Sau đỉnh OI 24h: {ret_24:+.2f}%")

if len(oi_troughs) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[oi_troughs.index].mean() * 100
    findings.append(f"Sau đáy OI 24h: {ret_24:+.2f}%")

# Funding extreme
ext_high = eda[eda['funding_extreme_high']]
if len(ext_high) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[ext_high.index].mean() * 100
    findings.append(f"Funding > P95 → 24h return: {ret_24:+.2f}%")

ext_low = eda[eda['funding_extreme_low']]
if len(ext_low) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[ext_low.index].mean() * 100
    findings.append(f"Funding < P5 → 24h return: {ret_24:+.2f}%")

# Volume spike
if len(vol_spikes) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[vol_spikes.index].mean() * 100
    findings.append(f"Volume > P99 → 24h return: {ret_24:+.2f}%")

# Funding streak
if len(streak_up) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[streak_up.index].mean() * 100
    findings.append(f"Funding tăng 3 nến → 24h return: {ret_24:+.2f}%")

if len(streak_down) > 0:
    ret_24 = (eda['price'].shift(-24) / eda['price'] - 1)[streak_down.index].mean() * 100
    findings.append(f"Funding giảm 3 nến → 24h return: {ret_24:+.2f}%")

for i, f in enumerate(findings, 1):
    print(f"   {i}. {f}")

# Lưu dữ liệu EDA
eda.to_parquet(os.path.join(EDA_DIR, "eda_data.parquet"))
print(f"\n💾 Dữ liệu EDA đã lưu: {os.path.join(EDA_DIR, 'eda_data.parquet')}")
print(f"🎯 Hoàn thành EDA!")