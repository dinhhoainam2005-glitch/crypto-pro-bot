"""
Bước 3.1 - QUÉT TỰ ĐỘNG TỔ HỢP ĐA BIẾN
- Quét tất cả tổ hợp 2-3 biến từ dữ liệu
- Tìm tổ hợp có Sharpe cao và ổn định
- Không lookahead, không data leakage
- Output: Bảng xếp hạng các tổ hợp tốt nhất
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
from itertools import combinations
import os
import json
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDA_DIR = os.path.join(BASE_DIR, "data", "eda")
os.makedirs(EDA_DIR, exist_ok=True)

# ============================================================
# 1. LOAD & CHUẨN BỊ DỮ LIỆU
# ============================================================
print("="*60)
print("🔍 QUÉT TỰ ĐỘNG TỔ HỢP ĐA BIẾN")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']
print(f"\n📥 {len(df)} nến")

# ============================================================
# 2. TẠO THƯ VIỆN BIẾN (FEATURE LIBRARY)
# ============================================================
print("\n🔧 Tạo thư viện biến...")

# Returns
df['ret_1h'] = df['perp_close'].pct_change()
df['ret_24h'] = df['perp_close'].pct_change(24)
df['ret_7d'] = df['perp_close'].pct_change(168)

# Funding features
df['funding'] = df['funding_rate']
df['funding_p1'] = df['funding'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 1), raw=True)
df['funding_p5'] = df['funding'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)
df['funding_p95'] = df['funding'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)
df['funding_p99'] = df['funding'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 99), raw=True)
df['funding_chg_8h'] = df['funding'].diff(8)

# OI features
df['oi_chg_1h'] = df['oi'].pct_change()
df['oi_chg_24h'] = df['oi'].pct_change(24)
df['oi_chg_7d'] = df['oi'].pct_change(168)
df['oi_p95'] = df['oi_chg_24h'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)
df['oi_p5'] = df['oi_chg_24h'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)

# CVD features
df['cvd_chg_1h'] = df['cvd'].diff()
df['cvd_chg_24h'] = df['cvd'].diff(24)
df['cvd_chg_7d'] = df['cvd'].diff(168)
df['cvd_p95'] = df['cvd_chg_24h'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)
df['cvd_p5'] = df['cvd_chg_24h'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)

# Volume features
df['vol'] = df['perp_volume']
df['vol_ma_24'] = df['vol'].rolling(24).mean()
df['vol_ratio'] = df['vol'] / df['vol_ma_24']
df['vol_p99'] = df['vol'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 99), raw=True)
df['vol_p95'] = df['vol'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)

# Delta Volume
df['delta_chg'] = df['delta_volume'].diff(24)

# Price action
df['price_ma_50'] = df['perp_close'].rolling(50).mean()
df['price_vs_ma50'] = df['perp_close'] / df['price_ma_50'] - 1
df['price_range'] = (df['perp_high'] - df['perp_low']) / df['perp_close']

# ============================================================
# 3. ĐỊNH NGHĨA CÁC ĐIỀU KIỆN (CONDITIONS)
# ============================================================
print("📋 Định nghĩa điều kiện...")

conditions = {
    # Funding
    'FUND_P1': ('funding < funding_p1', lambda d: d['funding'] < d['funding_p1']),
    'FUND_P5': ('funding < funding_p5', lambda d: d['funding'] < d['funding_p5']),
    'FUND_P95': ('funding > funding_p95', lambda d: d['funding'] > d['funding_p95']),
    'FUND_P99': ('funding > funding_p99', lambda d: d['funding'] > d['funding_p99']),
    'FUND_NEG': ('funding < 0', lambda d: d['funding'] < 0),
    'FUND_POS': ('funding > 0', lambda d: d['funding'] > 0),
    'FUND_RISING': ('funding_chg_8h > 0', lambda d: d['funding_chg_8h'] > 0),
    
    # OI
    'OI_SURGE': ('oi_chg_24h > oi_p95', lambda d: d['oi_chg_24h'] > d['oi_p95']),
    'OI_DROP': ('oi_chg_24h < oi_p5', lambda d: d['oi_chg_24h'] < d['oi_p5']),
    'OI_UP': ('oi_chg_24h > 0.02', lambda d: d['oi_chg_24h'] > 0.02),
    'OI_DOWN': ('oi_chg_24h < -0.02', lambda d: d['oi_chg_24h'] < -0.02),
    
    # CVD
    'CVD_SURGE': ('cvd_chg_24h > cvd_p95', lambda d: d['cvd_chg_24h'] > d['cvd_p95']),
    'CVD_DROP': ('cvd_chg_24h < cvd_p5', lambda d: d['cvd_chg_24h'] < d['cvd_p5']),
    'CVD_UP': ('cvd_chg_24h > 0', lambda d: d['cvd_chg_24h'] > 0),
    'CVD_DOWN': ('cvd_chg_24h < 0', lambda d: d['cvd_chg_24h'] < 0),
    
    # Volume
    'VOL_SPIKE': ('vol > vol_p99', lambda d: d['vol'] > d['vol_p99']),
    'VOL_HIGH': ('vol > vol_p95', lambda d: d['vol'] > d['vol_p95']),
    'VOL_RISING': ('vol > vol_ma_24', lambda d: d['vol'] > d['vol_ma_24']),
    
    # Delta
    'DELTA_POS': ('delta_chg > 0', lambda d: d['delta_chg'] > 0),
    'DELTA_NEG': ('delta_chg < 0', lambda d: d['delta_chg'] < 0),
    
    # Price Action
    'PRICE_ABOVE_MA50': ('price_vs_ma50 > 0', lambda d: d['price_vs_ma50'] > 0),
    'PRICE_DOWN_24H': ('ret_24h < -0.02', lambda d: d['ret_24h'] < -0.02),
    'PRICE_UP_24H': ('ret_24h > 0.02', lambda d: d['ret_24h'] > 0.02),
    'PRICE_DOWN_7D': ('ret_7d < -0.05', lambda d: d['ret_7d'] < -0.05),
}

print(f"   {len(conditions)} điều kiện đã định nghĩa")

# ============================================================
# 4. QUÉT TỔ HỢP 2 VÀ 3 ĐIỀU KIỆN
# ============================================================
print("\n🔍 Quét tổ hợp...")

cond_names = list(conditions.keys())
results = []

# Hàm tính Sharpe cho 1 tổ hợp
def evaluate_combo(cond_list, direction):
    """Tính Sharpe của tổ hợp điều kiện"""
    mask = pd.Series(True, index=df.index)
    for cond_name in cond_list:
        _, func = conditions[cond_name]
        mask = mask & func(df)
    
    # Shift để tránh lookahead
    signal = mask.astype(int) * direction
    signal_shifted = signal.shift(1)
    
    # Return 24h
    future_ret = (df['perp_close'].shift(-24) - df['perp_open']) / df['perp_open']
    strategy_ret = future_ret * signal_shifted
    
    valid = strategy_ret[signal_shifted != 0].dropna()
    
    if len(valid) < 30:
        return None
    
    avg_ret = valid.mean()
    std_ret = valid.std()
    sharpe = avg_ret / std_ret * np.sqrt(365) if std_ret > 0 else 0
    win_rate = (valid > 0).sum() / len(valid) * 100
    
    # OOS test
    oos_start = pd.Timestamp('2024-01-01')
    oos = valid[valid.index >= oos_start]
    is_valid = valid[valid.index < oos_start]
    
    oos_sharpe = oos.mean() / oos.std() * np.sqrt(365) if len(oos) >= 10 and oos.std() > 0 else -999
    is_sharpe = is_valid.mean() / is_valid.std() * np.sqrt(365) if len(is_valid) >= 20 and is_valid.std() > 0 else 0
    
    # Walk-Forward
    n_folds = 6
    if len(valid) >= 60:
        days = (valid.index[-1] - valid.index[0]).days // n_folds
        profitable = 0
        for i in range(n_folds):
            s = valid.index[0] + timedelta(days=i * days)
            e = s + timedelta(days=days)
            fold = valid[(valid.index >= s) & (valid.index < e)]
            if len(fold) >= 5 and fold.mean() > 0:
                profitable += 1
    else:
        profitable = 0
    
    return {
        'conditions': '+'.join(cond_list),
        'direction': 'LONG' if direction == 1 else 'SHORT',
        'n_signals': len(valid),
        'avg_ret_pct': round(avg_ret * 100, 3),
        'win_rate': round(win_rate, 1),
        'sharpe': round(sharpe, 2),
        'oos_sharpe': round(oos_sharpe, 2),
        'is_sharpe': round(is_sharpe, 2),
        'wf_profitable': profitable,
        'stability': round(oos_sharpe / is_sharpe, 2) if is_sharpe > 0 else -99
    }

# Quét tổ hợp 2 điều kiện
print("\n📊 Quét tổ hợp 2 điều kiện...")
combo_2 = list(combinations(cond_names, 2))
pbar = tqdm(total=len(combo_2) * 2, desc="   2-conditions", unit="combo")
for c1, c2 in combo_2:
    for direction in [1, -1]:
        res = evaluate_combo([c1, c2], direction)
        if res and res['sharpe'] > 0.5 and res['oos_sharpe'] > 0:
            results.append(res)
        pbar.update(1)
pbar.close()

# Quét tổ hợp 3 điều kiện
print("📊 Quét tổ hợp 3 điều kiện...")
combo_3 = list(combinations(cond_names, 3))
pbar = tqdm(total=len(combo_3) * 2, desc="   3-conditions", unit="combo")
for c1, c2, c3 in combo_3:
    for direction in [1, -1]:
        res = evaluate_combo([c1, c2, c3], direction)
        if res and res['sharpe'] > 1.0 and res['oos_sharpe'] > 0.5:
            results.append(res)
        pbar.update(1)
pbar.close()

# ============================================================
# 5. XẾP HẠNG
# ============================================================
print(f"\n📊 KẾT QUẢ: {len(results)} tổ hợp đạt yêu cầu")

if len(results) > 0:
    # Sắp xếp theo stability score (kết hợp Sharpe + OOS + WF)
    results_df = pd.DataFrame(results)
    results_df['score'] = results_df['sharpe'] * 0.3 + results_df['oos_sharpe'] * 0.4 + results_df['wf_profitable'] * 0.3
    results_df = results_df.sort_values('score', ascending=False)
    
    print(f"\n🏆 TOP 20 TỔ HỢP TỐT NHẤT:")
    print(f"   {'Rank':<5} {'Tổ hợp':<40} {'Dir':<6} {'n':<6} {'Ret%':<8} {'WR%':<6} {'Sharpe':<7} {'OOS':<7} {'WF':<5}")
    print(f"   {'-'*85}")
    for i, row in results_df.head(20).iterrows():
        print(f"   {i+1:<5} {row['conditions']:<40} {row['direction']:<6} {row['n_signals']:<6} "
              f"{row['avg_ret_pct']:>+.3f}  {row['win_rate']:>5.1f}  {row['sharpe']:>6.2f}  {row['oos_sharpe']:>6.2f}  {row['wf_profitable']}/6")
    
    # Lưu
    results_df.to_parquet(os.path.join(EDA_DIR, "combo_scan_results.parquet"))
    print(f"\n💾 Đã lưu {len(results_df)} tổ hợp vào combo_scan_results.parquet")
else:
    print("\n⚠️ Không tìm thấy tổ hợp nào đạt yêu cầu.")

print(f"\n🎯 Hoàn thành quét tổ hợp!")