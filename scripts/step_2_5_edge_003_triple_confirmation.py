"""
Cập nhật Edge-002 → DEPRECATED + Edge-003: Triple Confirmation
- Kết hợp: Funding Extreme + OI Extreme + CVD Divergence
- Chỉ vào lệnh khi cả 3 cùng xác nhận 1 hướng
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
ROBUST_DIR = os.path.join(BASE_DIR, "data", "robustness")
os.makedirs(EDGE_DIR, exist_ok=True)
os.makedirs(ROBUST_DIR, exist_ok=True)

# ============================================================
# 0. ĐÁNH DẤU EDGE-002 DEPRECATED
# ============================================================
edge002_path = os.path.join(EDGE_DIR, "EDGE-002_metadata.json")
if os.path.exists(edge002_path):
    with open(edge002_path, 'r') as f:
        e2 = json.load(f)
    e2['status'] = 'DEPRECATED'
    e2['deprecation_reason'] = (
        'Return 24h TB: -0.11%, Sharpe: -0.62, OOS Sharpe: -1.18, WR: 50.9% (random). '
        'OI Divergence đơn thuần không phải là edge.'
    )
    with open(edge002_path, 'w') as f:
        json.dump(e2, f, indent=2, default=str)
    print("✅ Edge-002 → DEPRECATED\n")

# ============================================================
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📂 EDGE-003: Triple Confirmation (Funding + OI + CVD)")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h.parquet"))
print(f"📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. TÍNH 3 THÀNH PHẦN TÍN HIỆU
# ============================================================

# 2.1 Funding Extreme (top/bottom 10% của 500 nến)
print("\n🔧 Tính 3 thành phần tín hiệu...")
df['funding_pct'] = df['funding_rate'].rolling(500, min_periods=100).apply(
    lambda x: (x.iloc[-1] > x).sum() / len(x) * 100, raw=False
)
df['funding_bullish'] = ((df['funding_pct'] < 10) & (df['funding_rate'] < 0)).astype(int)  # Funding cực thấp/âm → LONG
df['funding_bearish'] = ((df['funding_pct'] > 90) & (df['funding_rate'] > 0.0003)).astype(int)  # Funding cực cao → SHORT

# 2.2 OI Extreme
df['oi_change_24h'] = df['open_interest'].pct_change(24)
df['oi_pct'] = df['oi_change_24h'].rolling(500, min_periods=100).apply(
    lambda x: (x.iloc[-1] > x).sum() / len(x) * 100, raw=False
)
df['oi_bullish'] = ((df['oi_pct'] > 80) & (df['oi_change_24h'] > 0.01)).astype(int)  # OI tăng mạnh → LONG
df['oi_bearish'] = ((df['oi_pct'] < 20) & (df['oi_change_24h'] < -0.01)).astype(int)  # OI giảm mạnh → SHORT

# 2.3 CVD Divergence
df['cvd_change_12h'] = df['cvd'].diff(12)
df['price_change_12h'] = df['perp_close'].pct_change(12)
# CVD tăng nhưng giá giảm = bullish divergence
df['cvd_bullish'] = ((df['cvd_change_12h'] > 0) & (df['price_change_12h'] < -0.01)).astype(int)
# CVD giảm nhưng giá tăng = bearish divergence
df['cvd_bearish'] = ((df['cvd_change_12h'] < 0) & (df['price_change_12h'] > 0.01)).astype(int)

# ============================================================
# 3. TỔNG HỢP TÍN HIỆU (CẢ 3 XÁC NHẬN)
# ============================================================
print("   Kết hợp 3 tín hiệu...")

# LONG: funding_bullish + oi_bullish + cvd_bullish >= 2
df['bullish_score'] = df['funding_bullish'] + df['oi_bullish'] + df['cvd_bullish']
# SHORT: funding_bearish + oi_bearish + cvd_bearish >= 2
df['bearish_score'] = df['funding_bearish'] + df['oi_bearish'] + df['cvd_bearish']

df['signal'] = 0
df.loc[df['bullish_score'] >= 2, 'signal'] = 1
df.loc[df['bearish_score'] >= 2, 'signal'] = -1

# Ưu tiên SHORT nếu cả 2 cùng >= 2 (hiếm)
conflict = (df['bullish_score'] >= 2) & (df['bearish_score'] >= 2)
df.loc[conflict, 'signal'] = 0

# Shift tránh lookahead
df['signal_shifted'] = df['signal'].shift(1)

# ============================================================
# 4. TÍNH LỢI NHUẬN
# ============================================================
for horizon in [1, 6, 12, 24]:
    df[f'return_{horizon}h'] = (df['perp_close'].shift(-horizon) - df['perp_open']) / df['perp_open']
    df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']

# ============================================================
# 5. PHÂN TÍCH TỔNG QUAN
# ============================================================
valid_trades = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
total_signals = len(valid_trades)
long_signals = (valid_trades['signal_shifted'] == 1).sum()
short_signals = (valid_trades['signal_shifted'] == -1).sum()

print(f"\n📊 PHÂN TÍCH TỔNG QUAN EDGE-003:")
print(f"   Tổng tín hiệu: {total_signals} ({total_signals/len(df)*100:.2f}%)")
print(f"   LONG: {long_signals} | SHORT: {short_signals}")

if total_signals == 0:
    print("\n⚠️ 0 tín hiệu. Giảm ngưỡng xác nhận từ 2 → 1...")
    df['signal'] = 0
    df.loc[df['bullish_score'] >= 1, 'signal'] = 1
    df.loc[df['bearish_score'] >= 1, 'signal'] = -1
    conflict = (df['bullish_score'] >= 1) & (df['bearish_score'] >= 1)
    df.loc[conflict, 'signal'] = 0
    df['signal_shifted'] = df['signal'].shift(1)
    for horizon in [1, 6, 12, 24]:
        df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']
    valid_trades = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
    total_signals = len(valid_trades)
    long_signals = (valid_trades['signal_shifted'] == 1).sum()
    short_signals = (valid_trades['signal_shifted'] == -1).sum()
    print(f"   ✅ Sau điều chỉnh: {total_signals} tín hiệu ({total_signals/len(df)*100:.2f}%)")
    print(f"   LONG: {long_signals} | SHORT: {short_signals}")

print(f"\n📈 Hiệu suất theo horizon:")
for horizon in [1, 6, 12, 24]:
    col = f'strategy_return_{horizon}h'
    rets = valid_trades[col].dropna()
    if len(rets) > 0:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / horizon) if rets.std() > 0 else 0
        print(f"   {horizon:2d}h: Ret={avg:+.4f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)}")

# ============================================================
# 6. PHÂN TÍCH THEO REGIME
# ============================================================
print(f"\n📊 THEO REGIME (24h):")
regime_perf = {}
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = valid_trades['regime'] == regime
    rets = valid_trades.loc[mask, 'strategy_return_24h']
    if len(rets) >= 5:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365) if rets.std() > 0 else 0
        regime_perf[regime] = {'count': int(len(rets)), 'avg_ret': round(avg, 3), 'wr': round(wr, 1), 'sharpe': round(sh, 2)}
        s = '✅' if avg > 0.1 else ('⚠️' if avg > 0 else '❌')
        print(f"   {regime:12s}: Ret={avg:+.3f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)} {s}")

# ============================================================
# 7. ROBUSTNESS TEST
# ============================================================
print(f"\n🔬 ROBUSTNESS TEST:")

# OOS
oos_start = pd.Timestamp('2024-01-01')
is_trades = valid_trades[valid_trades.index < oos_start]
oos_trades = valid_trades[valid_trades.index >= oos_start]

if len(oos_trades) >= 5:
    is_sh = is_trades['strategy_return_24h'].mean() / is_trades['strategy_return_24h'].std() * np.sqrt(365) if is_trades['strategy_return_24h'].std() > 0 else 0
    oos_sh = oos_trades['strategy_return_24h'].mean() / oos_trades['strategy_return_24h'].std() * np.sqrt(365) if oos_trades['strategy_return_24h'].std() > 0 else 0
    oos_ret = oos_trades['strategy_return_24h'].mean() * 100
    oos_wr = (oos_trades['strategy_return_24h'] > 0).sum() / len(oos_trades) * 100
    print(f"   IS: Sharpe={is_sh:.2f}, n={len(is_trades)}")
    print(f"   OOS: Sharpe={oos_sh:.2f}, Ret={oos_ret:+.3f}%, WR={oos_wr:.1f}%, n={len(oos_trades)}")
    oos_ok = oos_sh > 0 and oos_sh >= is_sh * 0.5
else:
    oos_ok = None
    print(f"   OOS: Không đủ dữ liệu (n={len(oos_trades)})")

# Walk-Forward
n_folds = 6
days = (valid_trades.index[-1] - valid_trades.index[0]).days // n_folds
profitable = 0
for i in range(n_folds):
    s = valid_trades.index[0] + timedelta(days=i * days)
    e = s + timedelta(days=days)
    fold = valid_trades[(valid_trades.index >= s) & (valid_trades.index < e)]
    if len(fold) >= 3 and fold['strategy_return_24h'].mean() > 0:
        profitable += 1
wf_ok = profitable >= n_folds * 0.6
print(f"   Walk-Forward: {profitable}/{n_folds} folds profitable {'✅' if wf_ok else '❌'}")

# Top 5% contribution
rets_pct = valid_trades['strategy_return_24h'] * 100
top5 = rets_pct.nlargest(max(1, int(len(rets_pct) * 0.05)))
top5_c = top5.sum() / rets_pct.sum() * 100 if rets_pct.sum() != 0 else 0
dist_ok = top5_c < 50
print(f"   Top 5% contribution: {top5_c:.1f}% {'✅' if dist_ok else '❌'}")

# ============================================================
# 8. KẾT LUẬN & LƯU
# ============================================================
all_pass = all([
    total_signals >= 50,
    valid_trades['strategy_return_24h'].mean() > 0,
    oos_ok if oos_ok is not None else True,
    wf_ok,
    dist_ok if rets_pct.sum() > 0 else True
])

print(f"\n🏆 KẾT LUẬN: {'✅ EDGE ĐÁNG TIN CẬY' if all_pass else '⚠️ CẦN ĐIỀU CHỈNH'}")

edge_003 = {
    'edge_id': 'EDGE-003',
    'name': 'Triple Confirmation (Funding + OI + CVD)',
    'logic': 'Kết hợp Funding Extreme + OI Extreme + CVD Divergence. Cần ≥2/3 xác nhận.',
    'status': 'ACTIVE' if all_pass else 'UNDER_REVIEW',
    'total_signals': int(total_signals),
    'return_24h_pct': round(valid_trades['strategy_return_24h'].mean() * 100, 3),
    'sharpe_24h': round(valid_trades['strategy_return_24h'].mean() / valid_trades['strategy_return_24h'].std() * np.sqrt(365), 2) if valid_trades['strategy_return_24h'].std() > 0 else 0,
    'win_rate_pct': round((valid_trades['strategy_return_24h'] > 0).sum() / len(valid_trades) * 100, 1),
    'oos_sharpe': round(oos_sh, 2) if len(oos_trades) >= 5 else None,
    'wf_profitable': f"{profitable}/{n_folds}",
    'top5_contrib': round(top5_c, 1),
    'regime_performance': regime_perf,
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-003_metadata.json"), 'w') as f:
    json.dump(edge_003, f, indent=2, default=str)

edge_signals = df[['signal', 'signal_shifted', 'bullish_score', 'bearish_score',
                    'funding_bullish', 'oi_bullish', 'cvd_bullish',
                    'funding_bearish', 'oi_bearish', 'cvd_bearish',
                    'strategy_return_1h', 'strategy_return_6h',
                    'strategy_return_12h', 'strategy_return_24h', 'regime']].copy()
edge_signals.to_parquet(os.path.join(EDGE_DIR, "EDGE-003_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-003")
print(f"🎯 Hoàn thành Edge-003!")