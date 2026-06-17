"""
EDGE-005: FUND_P5 + FUND_POS + CVD_DROP (MM Absorption)
- Logic: Funding thấp vừa phải, còn dương + CVD giảm = MM hấp thụ lực bán
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
print("📂 EDGE-005: MM Absorption (FUND_P5 + FUND_POS + CVD_DROP)")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. ĐỊNH NGHĨA TÍN HIỆU
# ============================================================
print(f"\n🔧 Định nghĩa tín hiệu:")
print(f"   1. Funding < P5 (thấp vừa phải, không cực đoan)")
print(f"   2. Funding > 0 (vẫn còn dương → chưa quá bearish)")
print(f"   3. CVD 24h < 0 (CVD đang giảm → MM hấp thụ)")
print(f"   → LONG (MM sẽ đẩy giá lên sau khi hấp thụ xong)")
print(f"   Hold 24h, 48h, 72h")
print(f"   KHÔNG lookahead")

# Tính các điều kiện
df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=100).apply(
    lambda x: np.percentile(x, 5), raw=True
)
df['cvd_chg_24h'] = df['cvd'].diff(24)

# 3 điều kiện
cond1 = df['funding_rate'] < df['funding_p5']   # Funding < P5
cond2 = df['funding_rate'] > 0                    # Funding > 0
cond3 = df['cvd_chg_24h'] < 0                     # CVD giảm

df['signal'] = 0
df.loc[cond1 & cond2 & cond3, 'signal'] = 1  # LONG

# Shift tránh lookahead
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
valid = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
total = len(valid)

print(f"\n📊 TỔNG QUAN:")
print(f"   Tổng tín hiệu: {total} ({total/len(df)*100:.2f}%)")
print(f"   Tín hiệu/năm: {total/7:.0f}")

print(f"\n📈 Hiệu suất theo horizon:")
best_h, best_sh = 24, -999
for h in [1, 6, 12, 24, 48, 72]:
    col = f'strategy_return_{h}h'
    rets = valid[col].dropna()
    if len(rets) > 0:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / h) if rets.std() > 0 else 0
        print(f"   {h:3d}h: Ret={avg:+.4f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)}")
        if sh > best_sh:
            best_sh = sh
            best_h = h

print(f"\n   ✅ Horizon tốt nhất: {best_h}h (Sharpe={best_sh:.2f})")

# ============================================================
# 5. PHÂN TÍCH THEO REGIME
# ============================================================
print(f"\n📊 THEO REGIME (horizon {best_h}h):")
regime_perf = {}
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = valid['regime'] == regime
    rets = valid.loc[mask, f'strategy_return_{best_h}h'].dropna()
    if len(rets) >= 3:
        avg = rets.mean() * 100
        wr = (rets > 0).sum() / len(rets) * 100
        sh = rets.mean() / rets.std() * np.sqrt(365 * 24 / best_h) if rets.std() > 0 else 0
        regime_perf[regime] = {'count': int(len(rets)), 'avg_ret': round(avg, 3), 'wr': round(wr, 1), 'sharpe': round(sh, 2)}
        s = '✅' if avg > 0.1 else ('⚠️' if avg > 0 else '❌')
        print(f"   {regime:12s}: Ret={avg:+.3f}% | WR={wr:.1f}% | Sharpe={sh:.2f} | n={len(rets)} {s}")

# ============================================================
# 6. ROBUSTNESS TEST ĐẦY ĐỦ
# ============================================================
print(f"\n{'='*40}")
print(f"🔬 ROBUSTNESS TEST ĐẦY ĐỦ")
print(f"{'='*40}")

rets = valid[f'strategy_return_{best_h}h'].dropna()
rets_pct = rets * 100

# 6.1 Out-of-Sample
oos_start = pd.Timestamp('2024-01-01')
is_data = valid[valid.index < oos_start]
oos_data = valid[valid.index >= oos_start]
is_rets = is_data[f'strategy_return_{best_h}h'].dropna()
oos_rets = oos_data[f'strategy_return_{best_h}h'].dropna()

is_sh = is_rets.mean() / is_rets.std() * np.sqrt(365 * 24 / best_h) if len(is_rets) > 5 and is_rets.std() > 0 else 0
oos_sh = oos_rets.mean() / oos_rets.std() * np.sqrt(365 * 24 / best_h) if len(oos_rets) > 5 and oos_rets.std() > 0 else 0

print(f"\n   Out-of-Sample Test:")
print(f"   IS  (2019-2023): Sharpe={is_sh:.2f}, Ret={is_rets.mean()*100:+.3f}%, WR={(is_rets>0).sum()/len(is_rets)*100:.1f}%, n={len(is_rets)}")
print(f"   OOS (2024-2026): Sharpe={oos_sh:.2f}, Ret={oos_rets.mean()*100:+.3f}%, WR={(oos_rets>0).sum()/len(oos_rets)*100:.1f}%, n={len(oos_rets)}")
oos_ok = oos_sh > 1.0

# 6.2 Walk-Forward
n_folds = 6
days = (valid.index[-1] - valid.index[0]).days // n_folds
wf_profitable = 0
wf_details = []
for i in range(n_folds):
    s = valid.index[0] + timedelta(days=i * days)
    e = s + timedelta(days=days)
    fold = valid[(valid.index >= s) & (valid.index < e)]
    fr = fold[f'strategy_return_{best_h}h'].dropna()
    if len(fr) >= 3:
        is_prof = fr.mean() > 0
        if is_prof:
            wf_profitable += 1
        wf_details.append({'fold': i+1, 'start': s.strftime('%Y-%m'), 'trades': len(fr), 
                          'avg_ret': round(fr.mean()*100, 3), 'profitable': is_prof})

print(f"\n   Walk-Forward ({n_folds} folds):")
for w in wf_details:
    print(f"   Fold {w['fold']} ({w['start']}): {w['trades']} trades, Ret={w['avg_ret']:+.3f}% {'✅' if w['profitable'] else '❌'}")
wf_ok = wf_profitable >= 4
print(f"   Profitable: {wf_profitable}/{n_folds} {'✅' if wf_ok else '❌'}")

# 6.3 Monte Carlo (block bootstrap)
print(f"\n   Monte Carlo (1000 runs)...")
np.random.seed(42)
mc_sharpes = []
block_size = max(5, len(rets) // 20)
for _ in range(1000):
    sampled = []
    for _ in range(len(rets) // block_size + 1):
        start = np.random.randint(0, max(1, len(rets) - block_size))
        sampled.extend(rets.values[start:start + block_size])
    sampled = np.array(sampled[:len(rets)])
    sh = sampled.mean() / sampled.std() * np.sqrt(365 * 24 / best_h) if sampled.std() > 0 else 0
    mc_sharpes.append(sh)
mc_sharpes = np.array(mc_sharpes)
sh_above_1 = (mc_sharpes > 1.0).sum() / 1000 * 100
sh_above_2 = (mc_sharpes > 2.0).sum() / 1000 * 100
print(f"   Sharpe 95% CI: [{np.percentile(mc_sharpes, 2.5):.2f}, {np.percentile(mc_sharpes, 97.5):.2f}]")
print(f"   Sharpe > 1.0: {sh_above_1:.0f}% | Sharpe > 2.0: {sh_above_2:.0f}%")
mc_ok = sh_above_1 >= 80

# 6.4 Phân phối lợi nhuận
top5 = rets.nlargest(max(1, int(len(rets) * 0.05)))
top5_c = top5.sum() / rets.sum() * 100 if rets.sum() != 0 else 0
skew = rets_pct.skew()
kurt = rets_pct.kurtosis()
print(f"\n   Phân phối lợi nhuận:")
print(f"   Skew: {skew:.2f} | Kurtosis: {kurt:.2f}")
print(f"   P10={np.percentile(rets_pct, 10):+.3f}% | P50={np.percentile(rets_pct, 50):+.3f}% | P90={np.percentile(rets_pct, 90):+.3f}%")
print(f"   Top 5% đóng góp: {top5_c:.1f}% {'✅' if top5_c < 50 else '❌'}")
dist_ok = top5_c < 50

# 6.5 Stress Test
print(f"\n   Stress Test:")
stress_events = [
    ('2020-03-12', '2020-03-16', 'COVID Crash'),
    ('2021-05-19', '2021-05-23', 'China Ban'),
    ('2022-11-09', '2022-11-13', 'FTX Collapse'),
    ('2024-08-05', '2024-08-09', 'Yen Unwind'),
]
stress_all_pass = True
for start, end, label in stress_events:
    event = valid[(valid.index >= start) & (valid.index <= end)]
    if len(event) > 0:
        ev_ret = event[f'strategy_return_{best_h}h'].mean() * 100
        print(f"   {label:20s}: {len(event)} trades, Ret={ev_ret:+.3f}% {'✅' if ev_ret > 0 else '❌'}")
        if ev_ret < 0:
            stress_all_pass = False
    else:
        print(f"   {label:20s}: Không có tín hiệu (không vào lệnh = an toàn) ✅")

# 6.6 Equity Curve
equity = rets.cumsum()
max_eq = equity.cummax()
dd = equity - max_eq
max_dd_pct = dd.min() * 100
print(f"\n   Equity Curve:")
print(f"   Lợi nhuận tích lũy: {equity.iloc[-1]*100:+.2f}%")
print(f"   Max Drawdown: {max_dd_pct:+.2f}%")

# ============================================================
# 7. KẾT LUẬN
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 KẾT LUẬN EDGE-005")
print(f"{'='*60}")

tests = {
    'OOS Sharpe > 1.0': oos_ok,
    'Walk-Forward >= 4/6': wf_ok,
    'Monte Carlo > 80%': mc_ok,
    'Phân phối đều (top5 < 50%)': dist_ok,
    'Stress Test': stress_all_pass
}

all_pass = True
for name, passed in tests.items():
    status = '✅ PASS' if passed else '❌ FAIL'
    if not passed:
        all_pass = False
    print(f"   {name:35s}: {status}")

print(f"\n   {'✅ EDGE ĐÁNG TIN CẬY - ACTIVE' if all_pass else '⚠️ CẦN ĐIỀU CHỈNH'}")

# ============================================================
# 8. LƯU
# ============================================================
edge = {
    'edge_id': 'EDGE-005',
    'name': 'MM Absorption (FUND_P5 + FUND_POS + CVD_DROP)',
    'logic': 'Funding thấp vừa phải (P5) nhưng vẫn dương + CVD đang giảm = Market Maker đang hấp thụ lực bán, chuẩn bị đẩy giá lên. Vào LONG.',
    'signal_type': 'Market Maker Absorption',
    'direction': 'LONG only',
    'conditions': ['FUND_P5', 'FUND_POS', 'CVD_DROP'],
    'best_horizon_h': best_h,
    'total_signals': int(total),
    'avg_return_pct': round(rets.mean() * 100, 3),
    'win_rate_pct': round((rets > 0).sum() / len(rets) * 100, 1),
    'sharpe': round(rets.mean() / rets.std() * np.sqrt(365 * 24 / best_h), 2) if rets.std() > 0 else 0,
    'oos_sharpe': round(oos_sh, 2),
    'wf_profitable': f"{wf_profitable}/{n_folds}",
    'mc_sharpe_above_1_pct': round(sh_above_1, 1),
    'top5_contrib_pct': round(top5_c, 1),
    'max_drawdown_pct': round(max_dd_pct, 2),
    'cumulative_return_pct': round(equity.iloc[-1] * 100, 2),
    'regime_performance': regime_perf,
    'status': 'ACTIVE' if all_pass else 'UNDER_REVIEW',
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-005_metadata.json"), 'w') as f:
    json.dump(edge, f, indent=2, default=str)

# Lưu tín hiệu
df[['signal', 'signal_shifted', 'funding_rate', 'funding_p5', 'cvd_chg_24h',
    'strategy_return_1h', 'strategy_return_6h', 'strategy_return_12h',
    'strategy_return_24h', 'strategy_return_48h', 'strategy_return_72h',
    'regime']].to_parquet(os.path.join(EDGE_DIR, "EDGE-005_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-005 vào Edge Database")
print(f"🎯 Hoàn thành EDGE-005!")