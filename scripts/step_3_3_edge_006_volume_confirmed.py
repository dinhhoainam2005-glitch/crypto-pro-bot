"""
EDGE-006: FUND_P5 + CVD_DROP + VOL_RISING (Volume-Confirmed MM Absorption)
- Logic: Như EDGE-005 + thêm Volume tăng để xác nhận dòng tiền vào
- Backtest toàn bộ lịch sử + Robustness đầy đủ
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import os
import json
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
ROBUST_DIR = os.path.join(BASE_DIR, "data", "robustness")
os.makedirs(EDGE_DIR, exist_ok=True)
os.makedirs(ROBUST_DIR, exist_ok=True)

# ============================================================
# 1. LOAD & CHUẨN BỊ
# ============================================================
print("="*60)
print("📂 EDGE-006: Volume-Confirmed MM Absorption")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']
print(f"\n📥 {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# Tính indicators
df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=100).apply(
    lambda x: np.percentile(x, 5), raw=True)
df['cvd_chg_24h'] = df['cvd'].diff(24)
df['vol_ma_24'] = df['perp_volume'].rolling(24).mean()

# ============================================================
# 2. TÍN HIỆU
# ============================================================
print(f"\n🔧 Tín hiệu:")
print(f"   1. Funding < P5")
print(f"   2. CVD 24h < 0 (MM hấp thụ)")
print(f"   3. Volume > MA24 (dòng tiền xác nhận)")
print(f"   → LONG | Hold 12h (tối ưu từ EDGE-005)")

cond1 = df['funding_rate'] < df['funding_p5']
cond2 = df['cvd_chg_24h'] < 0
cond3 = df['perp_volume'] > df['vol_ma_24']

df['signal'] = 0
df.loc[cond1 & cond2 & cond3, 'signal'] = 1
df['signal_shifted'] = df['signal'].shift(1)

# ============================================================
# 3. LỢI NHUẬN
# ============================================================
for horizon in [1, 6, 12, 24, 48, 72]:
    df[f'return_{horizon}h'] = (df['perp_close'].shift(-horizon) - df['perp_open']) / df['perp_open']
    df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']

valid = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_12h'])
total = len(valid)

# ============================================================
# 4. PHÂN TÍCH NHANH
# ============================================================
print(f"\n📊 Tổng tín hiệu: {total} ({total/len(df)*100:.2f}%)")

best_h, best_sh = 12, -999
for h in [1, 6, 12, 24, 48, 72]:
    rets = valid[f'strategy_return_{h}h'].dropna()
    avg = rets.mean() * 100
    wr = (rets > 0).sum() / len(rets) * 100
    sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / h) if rets.std() > 0 else 0
    if sh > best_sh:
        best_sh = sh
        best_h = h
    print(f"   {h:3d}h: Ret={avg:+.3f}% | WR={wr:.1f}% | Sharpe={sh:.2f}")

print(f"\n   ✅ Horizon tốt nhất: {best_h}h (Sharpe={best_sh:.2f})")

# ============================================================
# 5. ROBUSTNESS
# ============================================================
rets = valid[f'strategy_return_{best_h}h'].dropna()

# OOS
oos_start = pd.Timestamp('2024-01-01')
is_rets = valid[valid.index < oos_start][f'strategy_return_{best_h}h'].dropna()
oos_rets = valid[valid.index >= oos_start][f'strategy_return_{best_h}h'].dropna()
is_sh = is_rets.mean() / is_rets.std() * np.sqrt(365 * 24 / best_h) if len(is_rets) > 5 and is_rets.std() > 0 else 0
oos_sh = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24 / best_h) if len(oos_rets) > 5 and oos_rets.std() > 0 else 0

# Walk-Forward
n_folds = 6
days = (valid.index[-1] - valid.index[0]).days // n_folds
wf_ok = 0
for i in range(n_folds):
    s = valid.index[0] + timedelta(days=i * days)
    e = s + timedelta(days=days)
    fr = valid[(valid.index >= s) & (valid.index < e)][f'strategy_return_{best_h}h'].dropna()
    if len(fr) >= 3 and fr.mean() > 0:
        wf_ok += 1

# Monte Carlo
np.random.seed(42)
mc_sh = []
for _ in range(1000):
    sampled = np.random.choice(rets.values, len(rets), replace=True)
    sh = sampled.mean() / sampled.std() * np.sqrt(365 * 24 / best_h) if sampled.std() > 0 else 0
    mc_sh.append(sh)
mc_sh = np.array(mc_sh)
sh_ok = (mc_sh > 1.0).sum() / 1000 * 100

# Phân phối
top5_c = rets.nlargest(max(1, int(len(rets)*0.05))).sum() / rets.sum() * 100 if rets.sum() != 0 else 0

# Equity
equity = rets.cumsum()
max_dd_pct = (equity - equity.cummax()).min() * 100

# ============================================================
# 6. SO SÁNH VỚI EDGE-005
# ============================================================
print(f"\n{'='*40}")
print(f"📊 SO SÁNH EDGE-005 vs EDGE-006")
print(f"{'='*40}")

# Load EDGE-005
e5_file = os.path.join(EDGE_DIR, "EDGE-005_metadata.json")
if os.path.exists(e5_file):
    with open(e5_file, 'r') as f:
        e5 = json.load(f)
    
    print(f"\n   {'Chỉ số':<25} {'EDGE-005':>12} {'EDGE-006':>12}")
    print(f"   {'-'*50}")
    print(f"   {'Tín hiệu':<25} {e5['total_signals']:>12} {total:>12}")
    print(f"   {'Sharpe':<25} {e5['sharpe']:>12.2f} {best_sh:>12.2f}")
    print(f"   {'OOS Sharpe':<25} {e5['oos_sharpe']:>12.2f} {oos_sh:>12.2f}")
    print(f"   {'Walk-Forward':<25} {e5['wf_profitable']:>12} {f'{wf_ok}/{n_folds}':>12}")
    print(f"   {'Monte Carlo >1.0':<25} {e5['mc_sharpe_above_1_pct']:>11.0f}% {sh_ok:>11.0f}%")
    print(f"   {'Top 5% contrib':<25} {e5['top5_contrib_pct']:>11.1f}% {top5_c:>11.1f}%")
    print(f"   {'Max DD':<25} {e5['max_drawdown_pct']:>11.2f}% {max_dd_pct:>11.2f}%")
    print(f"   {'Equity tích lũy':<25} {e5['cumulative_return_pct']:>11.2f}% {equity.iloc[-1]*100:>11.2f}%")

# ============================================================
# 7. KẾT LUẬN
# ============================================================
print(f"\n🏆 KẾT LUẬN EDGE-006:")
all_pass = all([oos_sh > 1.0, wf_ok >= 4, sh_ok >= 80, top5_c < 50])
print(f"   OOS Sharpe: {oos_sh:.2f} {'✅' if oos_sh > 1.0 else '❌'}")
print(f"   Walk-Forward: {wf_ok}/{n_folds} {'✅' if wf_ok >= 4 else '❌'}")
print(f"   Monte Carlo: {sh_ok:.0f}% {'✅' if sh_ok >= 80 else '❌'}")
print(f"   Top 5%: {top5_c:.1f}% {'✅' if top5_c < 50 else '❌'}")
print(f"\n   {'✅ ACTIVE' if all_pass else '⚠️ CẦN CẢI THIỆN'}")

# Lưu
edge = {
    'edge_id': 'EDGE-006',
    'name': 'Volume-Confirmed MM Absorption',
    'logic': 'FUND_P5 + CVD_DROP + VOL_RISING = MM hấp thụ có dòng tiền xác nhận → LONG',
    'conditions': ['FUND_P5', 'CVD_DROP', 'VOL_RISING'],
    'total_signals': int(total),
    'sharpe': round(best_sh, 2),
    'oos_sharpe': round(oos_sh, 2),
    'wf_profitable': f"{wf_ok}/{n_folds}",
    'mc_sharpe_above_1_pct': round(sh_ok, 1),
    'top5_contrib_pct': round(top5_c, 1),
    'max_drawdown_pct': round(max_dd_pct, 2),
    'cumulative_return_pct': round(equity.iloc[-1] * 100, 2),
    'status': 'ACTIVE' if all_pass else 'UNDER_REVIEW',
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-006_metadata.json"), 'w') as f:
    json.dump(edge, f, indent=2, default=str)

df[['signal', 'signal_shifted', 'funding_rate', 'cvd_chg_24h', 'perp_volume',
    'strategy_return_1h', 'strategy_return_6h', 'strategy_return_12h',
    'strategy_return_24h', 'strategy_return_48h', 'strategy_return_72h',
    'regime']].to_parquet(os.path.join(EDGE_DIR, "EDGE-006_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-006")
print(f"🎯 Hoàn thành!")