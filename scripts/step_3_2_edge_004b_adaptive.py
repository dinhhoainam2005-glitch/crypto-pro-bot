"""
Edge-004b: Funding < P1 với Adaptive Direction
- Uptrend/High Vol/Low Vol → LONG (short squeeze hoạt động)
- Downtrend/Sideway → SHORT (funding thấp = thị trường yếu, tiếp tục giảm)
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
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📂 EDGE-004b: Adaptive Funding P1")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. ĐỊNH NGHĨA TÍN HIỆU ADAPTIVE
# ============================================================
print(f"\n🔧 Adaptive Signal:")
print(f"   Uptrend/High Vol/Low Vol: Funding < P1 → LONG")
print(f"   Downtrend/Sideway:        Funding < P1 → SHORT (đảo chiều)")

# Tính P1 rolling
df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=100).apply(
    lambda x: np.percentile(x, 1), raw=True
)

# Tín hiệu cơ bản: Funding < P1
funding_extreme_low = df['funding_rate'] < df['funding_p1']

# Xác định regime tại thời điểm tín hiệu
is_bull_regime = df['regime'].isin(['uptrend', 'high_vol', 'low_vol'])
is_bear_regime = df['regime'].isin(['downtrend', 'sideway'])

# Adaptive signal
df['signal'] = 0
df.loc[funding_extreme_low & is_bull_regime, 'signal'] = 1   # LONG
df.loc[funding_extreme_low & is_bear_regime, 'signal'] = -1  # SHORT

# Shift tránh lookahead
df['signal_shifted'] = df['signal'].shift(1)

# ============================================================
# 3. TÍNH LỢI NHUẬN
# ============================================================
for horizon in [1, 6, 12, 24, 48, 72]:
    df[f'return_{horizon}h'] = (df['perp_close'].shift(-horizon) - df['perp_open']) / df['perp_open']
    df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']

# ============================================================
# 4. PHÂN TÍCH
# ============================================================
valid = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
total = len(valid)
long_signals = (valid['signal_shifted'] == 1).sum()
short_signals = (valid['signal_shifted'] == -1).sum()

print(f"\n📊 TỔNG QUAN:")
print(f"   Tổng tín hiệu: {total} ({total/len(df)*100:.2f}%)")
print(f"   LONG: {long_signals} | SHORT: {short_signals}")

print(f"\n📈 Hiệu suất:")
for h in [1, 6, 12, 24, 48, 72]:
    col = f'strategy_return_{h}h'
    rets = valid[col].dropna()
    avg = rets.mean() * 100
    wr = (rets > 0).sum() / len(rets) * 100
    sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / h) if rets.std() > 0 else 0
    print(f"   {h:3d}h: Ret={avg:+.4f}% | WR={wr:.1f}% | Sharpe={sh:.2f}")

# Chọn horizon tốt nhất
best_h = 24
best_sh = rets.mean() / rets.std() * np.sqrt(365) if rets.std() > 0 else 0
for h in [1, 6, 12, 24, 48, 72]:
    rets_h = valid[f'strategy_return_{h}h'].dropna()
    sh_h = rets_h.mean() / rets_h.std() * np.sqrt(365 * 24 / h) if rets_h.std() > 0 else 0
    if sh_h > best_sh:
        best_sh = sh_h
        best_h = h

# ============================================================
# 5. THEO REGIME (phân tích từng regime riêng)
# ============================================================
print(f"\n📊 THEO REGIME (horizon {best_h}h):")
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = valid['regime'] == regime
    rets = valid.loc[mask, f'strategy_return_{best_h}h'].dropna()
    if len(rets) >= 5:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / best_h) if rets.std() > 0 else 0
        direction = "LONG" if valid.loc[mask, 'signal_shifted'].iloc[0] > 0 else "SHORT"
        s = '✅' if avg > 0.1 else ('⚠️' if avg > 0 else '❌')
        print(f"   {regime:12s} [{direction:5s}]: Ret={avg:+.3f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)} {s}")

# ============================================================
# 6. ROBUSTNESS
# ============================================================
print(f"\n🔬 ROBUSTNESS:")

rets = valid[f'strategy_return_{best_h}h'].dropna()

# OOS
oos_start = pd.Timestamp('2024-01-01')
is_rets = valid[valid.index < oos_start][f'strategy_return_{best_h}h'].dropna()
oos_rets = valid[valid.index >= oos_start][f'strategy_return_{best_h}h'].dropna()
is_sh = is_rets.mean() / is_rets.std() * np.sqrt(365 * 24 / best_h) if is_rets.std() > 0 else 0
oos_sh = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24 / best_h) if oos_rets.std() > 0 else 0
print(f"   IS Sharpe: {is_sh:.2f} (n={len(is_rets)}) | OOS Sharpe: {oos_sh:.2f} (n={len(oos_rets)})")

# Walk-Forward
n_folds = 6
days = (valid.index[-1] - valid.index[0]).days // n_folds
wf_ok = 0
for i in range(n_folds):
    s = valid.index[0] + timedelta(days=i * days)
    e = s + timedelta(days=days)
    fold = valid[(valid.index >= s) & (valid.index < e)]
    fr = fold[f'strategy_return_{best_h}h'].dropna()
    if len(fr) >= 3 and fr.mean() > 0:
        wf_ok += 1
print(f"   Walk-Forward: {wf_ok}/{n_folds} folds profitable {'✅' if wf_ok >= 4 else '❌'}")

# Monte Carlo
np.random.seed(42)
mc_sh = []
for _ in range(1000):
    s = np.random.choice(rets.values, len(rets), replace=True)
    sh = s.mean() / s.std() * np.sqrt(365 * 24 / best_h) if s.std() > 0 else 0
    mc_sh.append(sh)
mc_sh = np.array(mc_sh)
sh_ok = (mc_sh > 1.0).sum() / 1000 * 100
print(f"   Monte Carlo Sharpe > 1.0: {sh_ok:.0f}% | 95% CI: [{np.percentile(mc_sh, 2.5):.2f}, {np.percentile(mc_sh, 97.5):.2f}]")

# Phân phối
top5_c = rets.nlargest(max(1, int(len(rets)*0.05))).sum() / rets.sum() * 100 if rets.sum() != 0 else 0
print(f"   Top 5% contribution: {top5_c:.1f}% {'✅' if top5_c < 50 else '❌'}")

# ============================================================
# 7. KẾT LUẬN
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 KẾT LUẬN EDGE-004b")
print(f"{'='*60}")

all_pass = all([
    oos_sh > 0,
    wf_ok >= 4,
    sh_ok >= 80,
    top5_c < 50
])

print(f"   OOS dương:       {'✅' if oos_sh > 0 else '❌'}")
print(f"   Walk-Forward:    {'✅' if wf_ok >= 4 else '❌'} ({wf_ok}/6)")
print(f"   Monte Carlo:     {'✅' if sh_ok >= 80 else '❌'} ({sh_ok:.0f}%)")
print(f"   Phân phối đều:   {'✅' if top5_c < 50 else '❌'} ({top5_c:.0f}%)")
print(f"\n   {'✅ EDGE ĐÁNG TIN CẬY' if all_pass else '⚠️ CẦN ĐIỀU CHỈNH'}")

# Lưu
edge = {
    'edge_id': 'EDGE-004b',
    'name': 'Adaptive Funding P1',
    'logic': 'Funding < P1 → LONG trong uptrend/high_vol/low_vol, SHORT trong downtrend/sideway. Tự thích nghi theo regime.',
    'status': 'ACTIVE' if all_pass else 'UNDER_REVIEW',
    'total_signals': int(total),
    'sharpe': round(rets.mean() / rets.std() * np.sqrt(365 * 24 / best_h), 2),
    'oos_sharpe': round(oos_sh, 2),
    'wf_profitable': f"{wf_ok}/{n_folds}",
    'mc_sharpe_above_1_pct': round(sh_ok, 1),
    'top5_contrib_pct': round(top5_c, 1),
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-004b_metadata.json"), 'w') as f:
    json.dump(edge, f, indent=2, default=str)

df[['signal', 'signal_shifted', 'funding_rate', 'funding_p1', 'regime',
    'strategy_return_1h', 'strategy_return_6h', 'strategy_return_12h',
    'strategy_return_24h', 'strategy_return_48h', 'strategy_return_72h']].to_parquet(
    os.path.join(EDGE_DIR, "EDGE-004b_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-004b")
print(f"🎯 Hoàn thành!")