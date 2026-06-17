"""
Edge-004: Funding Rate Extreme Low (P1) - Short Squeeze
- Tín hiệu: Funding < P1 (rolling 500 nến)
- Logic: Thị trường quá bearish → short bị squeeze → giá bật lên
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
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📂 EDGE-004: Funding < P1 (Short Squeeze)")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. ĐỊNH NGHĨA TÍN HIỆU
# ============================================================
print(f"\n🔧 Định nghĩa tín hiệu:")
print(f"   LONG khi Funding Rate < P1 (rolling 500 nến)")
print(f"   Hold 24h, 48h, 72h")
print(f"   KHÔNG lookahead: tín hiệu nến t → vào lệnh đầu nến t+1")

# Tính P1 rolling (chỉ dùng dữ liệu đến thời điểm hiện tại)
df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=100).apply(
    lambda x: np.percentile(x, 1), raw=True
)

# Tín hiệu LONG khi funding < P1
df['signal'] = 0
df.loc[df['funding_rate'] < df['funding_p1'], 'signal'] = 1

# Shift để tránh lookahead
df['signal_shifted'] = df['signal'].shift(1)

# ============================================================
# 3. TÍNH LỢI NHUẬN
# ============================================================
for horizon in [1, 6, 12, 24, 48, 72]:
    df[f'return_{horizon}h'] = (df['perp_close'].shift(-horizon) - df['perp_open']) / df['perp_open']
    df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']

# ============================================================
# 4. PHÂN TÍCH TỔNG QUAN
# ============================================================
valid_trades = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
total_signals = len(valid_trades)

print(f"\n📊 PHÂN TÍCH TỔNG QUAN:")
print(f"   Tổng tín hiệu: {total_signals} ({total_signals/len(df)*100:.2f}%)")
print(f"   Số tín hiệu/năm: {total_signals / 7:.0f}")

if total_signals == 0:
    print("❌ KHÔNG CÓ TÍN HIỆU. Dừng.")
    exit()

print(f"\n📈 Hiệu suất theo horizon:")
best_horizon = 24
best_sharpe = -999
for horizon in [1, 6, 12, 24, 48, 72]:
    col = f'strategy_return_{horizon}h'
    rets = valid_trades[col].dropna()
    if len(rets) > 0:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / horizon) if rets.std() > 0 else 0
        print(f"   {horizon:3d}h: Ret={avg:+.4f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)}")
        if sh > best_sharpe:
            best_sharpe = sh
            best_horizon = horizon

print(f"\n   ✅ Horizon tốt nhất: {best_horizon}h (Sharpe={best_sharpe:.2f})")

# ============================================================
# 5. PHÂN TÍCH THEO REGIME
# ============================================================
print(f"\n📊 THEO REGIME (horizon {best_horizon}h):")
regime_perf = {}
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = (valid_trades['regime'] == regime)
    rets = valid_trades.loc[mask, f'strategy_return_{best_horizon}h'].dropna()
    if len(rets) >= 5:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / best_horizon) if rets.std() > 0 else 0
        regime_perf[regime] = {'count': int(len(rets)), 'avg_ret': round(avg, 3), 'wr': round(wr, 1), 'sharpe': round(sh, 2)}
        s = '✅' if avg > 0.1 else ('⚠️' if avg > 0 else '❌')
        print(f"   {regime:12s}: Ret={avg:+.3f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)} {s}")

# ============================================================
# 6. ROBUSTNESS TEST
# ============================================================
print(f"\n{'='*40}")
print(f"🔬 ROBUSTNESS TEST")
print(f"{'='*40}")

rets = valid_trades[f'strategy_return_{best_horizon}h'].dropna()

# 6.1 Out-of-Sample
oos_start = pd.Timestamp('2024-01-01')
is_trades = valid_trades[valid_trades.index < oos_start]
oos_trades = valid_trades[valid_trades.index >= oos_start]

is_rets = is_trades[f'strategy_return_{best_horizon}h'].dropna()
oos_rets = oos_trades[f'strategy_return_{best_horizon}h'].dropna()

is_sh = is_rets.mean() / is_rets.std() * np.sqrt(365 * 24 / best_horizon) if is_rets.std() > 0 else 0
oos_sh = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24 / best_horizon) if oos_rets.std() > 0 else 0

print(f"\n   Out-of-Sample Test:")
print(f"   IS  (2019-2023): Sharpe={is_sh:.2f}, Ret={is_rets.mean()*100:+.3f}%, n={len(is_rets)}")
print(f"   OOS (2024-2026): Sharpe={oos_sh:.2f}, Ret={oos_rets.mean()*100:+.3f}%, n={len(oos_rets)}")
oos_ok = oos_sh > 0 and len(oos_rets) >= 5

# 6.2 Walk-Forward
n_folds = 6
total_days = (valid_trades.index[-1] - valid_trades.index[0]).days
fold_days = total_days // n_folds
wf_profitable = 0
wf_details = []

for i in range(n_folds):
    fold_start = valid_trades.index[0] + timedelta(days=i * fold_days)
    fold_end = fold_start + timedelta(days=fold_days)
    fold = valid_trades[(valid_trades.index >= fold_start) & (valid_trades.index < fold_end)]
    fold_rets = fold[f'strategy_return_{best_horizon}h'].dropna()
    if len(fold_rets) >= 3:
        is_profitable = fold_rets.mean() > 0
        if is_profitable:
            wf_profitable += 1
        wf_details.append({
            'fold': i+1,
            'start': fold_start.strftime('%Y-%m'),
            'trades': len(fold_rets),
            'avg_ret': round(fold_rets.mean()*100, 3),
            'profitable': is_profitable
        })

print(f"\n   Walk-Forward ({n_folds} folds):")
for w in wf_details:
    s = '✅' if w['profitable'] else '❌'
    print(f"   Fold {w['fold']} ({w['start']}): {w['trades']} trades, Ret={w['avg_ret']:+.3f}% {s}")
wf_ok = wf_profitable >= n_folds * 0.6
print(f"   Profitable: {wf_profitable}/{n_folds} {'✅' if wf_ok else '❌'}")

# 6.3 Monte Carlo
print(f"\n   Monte Carlo (1000 runs)...")
np.random.seed(42)
mc_sharpes = []
n_runs = 1000
rets_arr = rets.values
for _ in tqdm(range(n_runs), desc="   MC", unit="run"):
    sampled = np.random.choice(rets_arr, size=len(rets_arr), replace=True)
    sh = sampled.mean() / sampled.std() * np.sqrt(365 * 24 / best_horizon) if sampled.std() > 0 else 0
    mc_sharpes.append(sh)
mc_sharpes = np.array(mc_sharpes)
sh_above_1 = (mc_sharpes > 1.0).sum() / n_runs * 100
print(f"   Sharpe 95% CI: [{np.percentile(mc_sharpes, 2.5):.2f}, {np.percentile(mc_sharpes, 97.5):.2f}]")
print(f"   Sharpe > 1.0: {sh_above_1:.0f}%")
mc_ok = sh_above_1 >= 80

# 6.4 Phân phối
rets_pct = rets * 100
top5 = rets_pct.nlargest(max(1, int(len(rets_pct) * 0.05)))
top5_c = top5.sum() / rets_pct.sum() * 100 if rets_pct.sum() != 0 else 0
print(f"\n   Phân phối lợi nhuận:")
print(f"   Skew: {rets_pct.skew():.2f} | Kurt: {rets_pct.kurtosis():.2f}")
print(f"   Top 5% đóng góp: {top5_c:.1f}% {'✅' if top5_c < 50 else '❌'}")
dist_ok = top5_c < 50

# 6.5 Stress Test
print(f"\n   Stress Test:")
stress_events = [
    ('2020-03-12', '2020-03-16', 'COVID Crash'),
    ('2022-11-09', '2022-11-13', 'FTX Collapse'),
]
for start, end, label in stress_events:
    event = valid_trades[(valid_trades.index >= start) & (valid_trades.index <= end)]
    if len(event) > 0:
        ev_ret = event[f'strategy_return_{best_horizon}h'].mean() * 100
        print(f"   {label}: {len(event)} trades, Ret={ev_ret:+.3f}%")
    else:
        print(f"   {label}: Không có tín hiệu")

# ============================================================
# 7. KẾT LUẬN
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 KẾT LUẬN EDGE-004")
print(f"{'='*60}")

tests = {
    'OOS dương': oos_ok,
    'Walk-Forward': wf_ok,
    'Monte Carlo': mc_ok,
    'Phân phối đều': dist_ok
}

for name, passed in tests.items():
    print(f"   {name:20s}: {'✅ PASS' if passed else '❌ FAIL'}")

all_pass = all(tests.values())
print(f"\n   {'✅ EDGE ĐÁNG TIN CẬY - ĐƯA VÀO DATABASE' if all_pass else '⚠️ CẦN ĐIỀU CHỈNH'}")

# ============================================================
# 8. LƯU KẾT QUẢ
# ============================================================
edge_004 = {
    'edge_id': 'EDGE-004',
    'name': 'Funding < P1 (Short Squeeze)',
    'logic': 'Khi funding rate xuống dưới P1 (thị trường cực kỳ bearish), short bị squeeze đẩy giá lên. Đây là edge MOMENTUM/CONTINUATION.',
    'signal_type': 'Momentum',
    'direction': 'LONG only',
    'best_horizon_h': best_horizon,
    'total_signals': int(total_signals),
    'avg_return_pct': round(rets.mean() * 100, 3),
    'win_rate_pct': round((rets > 0).sum() / len(rets) * 100, 1),
    'sharpe': round(rets.mean() / rets.std() * np.sqrt(365 * 24 / best_horizon), 2),
    'oos_sharpe': round(oos_sh, 2),
    'wf_profitable': f"{wf_profitable}/{n_folds}",
    'mc_sharpe_above_1_pct': round(sh_above_1, 1),
    'top5_contrib_pct': round(top5_c, 1),
    'regime_performance': regime_perf,
    'status': 'ACTIVE' if all_pass else 'UNDER_REVIEW',
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-004_metadata.json"), 'w') as f:
    json.dump(edge_004, f, indent=2, default=str)

# Lưu tín hiệu
edge_signals = df[['signal', 'signal_shifted', 'funding_rate', 'funding_p1',
                    'strategy_return_1h', 'strategy_return_6h', 'strategy_return_12h',
                    'strategy_return_24h', 'strategy_return_48h', 'strategy_return_72h',
                    'regime']].copy()
edge_signals.to_parquet(os.path.join(EDGE_DIR, "EDGE-004_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-004")
print(f"🎯 Hoàn thành!")