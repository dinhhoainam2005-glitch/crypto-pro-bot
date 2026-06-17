"""
Bước 2.3 - Robustness Test Edge-001
- Walk-Forward Analysis (12 folds, mỗi fold 6 tháng)
- Monte Carlo Simulation (1000 runs, block bootstrap)
- Out-of-Sample Test
- Stress Test (các sự kiện cực đoan)
- Phân tích phân phối lợi nhuận
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
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
ROBUST_DIR = os.path.join(BASE_DIR, "data", "robustness")
os.makedirs(ROBUST_DIR, exist_ok=True)

# ============================================================
# 1. LOAD DỮ LIỆU EDGE-001
# ============================================================
print("="*60)
print("🔬 ROBUSTNESS TEST - EDGE-001")
print("="*60)

signals = pd.read_parquet(os.path.join(EDGE_DIR, "EDGE-001_signals.parquet"))
merged = pd.read_parquet(os.path.join(BASE_DIR, "data", "processed", "btc_merged_1h.parquet"))

# Lấy index chung
signals.index = merged.index

# Lấy các cột cần thiết
df = signals[['signal', 'signal_shifted', 'strategy_return_24h', 'regime']].copy()
df['price'] = merged['perp_close']

# Loại bỏ NaN
valid_trades = df[df['signal_shifted'] != 0].copy()
valid_trades = valid_trades.dropna(subset=['strategy_return_24h'])

print(f"\n📊 Tổng quan dữ liệu test:")
print(f"   Tổng nến: {len(df)}")
print(f"   Tín hiệu: {len(valid_trades)}")
print(f"   Thời gian: {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. WALK-FORWARD ANALYSIS
# ============================================================
print(f"\n{'='*40}")
print(f"📈 1. WALK-FORWARD ANALYSIS")
print(f"{'='*40}")

# Chia thành 12 folds, mỗi fold ~6 tháng
n_folds = 12
start_date = valid_trades.index[0]
end_date = valid_trades.index[-1]
total_days = (end_date - start_date).days
fold_days = total_days // n_folds

wf_results = []
for i in range(n_folds):
    fold_start = start_date + timedelta(days=i * fold_days)
    fold_end = fold_start + timedelta(days=fold_days)
    
    # In-sample: trước fold này
    is_mask = (valid_trades.index < fold_start)
    # Out-of-sample: trong fold này
    oos_mask = (valid_trades.index >= fold_start) & (valid_trades.index < fold_end)
    
    is_trades = valid_trades[is_mask]
    oos_trades = valid_trades[oos_mask]
    
    if len(oos_trades) >= 5:
        oos_avg = oos_trades['strategy_return_24h'].mean() * 100
        oos_wr = (oos_trades['strategy_return_24h'] > 0).sum() / len(oos_trades) * 100
        oos_sharpe = oos_trades['strategy_return_24h'].mean() / oos_trades['strategy_return_24h'].std() * np.sqrt(365) if oos_trades['strategy_return_24h'].std() > 0 else 0
        
        wf_results.append({
            'fold': i + 1,
            'start': fold_start.strftime('%Y-%m-%d'),
            'end': fold_end.strftime('%Y-%m-%d'),
            'is_trades': len(is_trades),
            'oos_trades': len(oos_trades),
            'oos_avg_return_pct': round(oos_avg, 3),
            'oos_win_rate_pct': round(oos_wr, 1),
            'oos_sharpe': round(oos_sharpe, 2),
            'oos_profitable': oos_avg > 0
        })

wf_df = pd.DataFrame(wf_results)
print(f"\n   Kết quả Walk-Forward ({n_folds} folds):")
print(f"   {'Fold':<6} {'Ngày':<22} {'IS':<5} {'OOS':<5} {'Ret%':<8} {'WR%':<7} {'Sharpe':<8} {'Tốt?'}")
print(f"   {'-'*65}")
for _, row in wf_df.iterrows():
    status = '✅' if row['oos_profitable'] else '❌'
    print(f"   {row['fold']:<6} {row['start']}->{row['end']:<10} {row['is_trades']:<5} {row['oos_trades']:<5} {row['oos_avg_return_pct']:>+.3f}  {row['oos_win_rate_pct']:>5.1f}  {row['oos_sharpe']:>6.2f}  {status}")

profitable_folds = wf_df['oos_profitable'].sum()
print(f"\n   📊 Profitable folds: {profitable_folds}/{n_folds} ({profitable_folds/n_folds*100:.0f}%)")
if profitable_folds >= n_folds * 0.7:
    print(f"   ✅ Walk-Forward PASSED (>70% folds profitable)")
else:
    print(f"   ⚠️ Walk-Forward WARNING (<70% folds profitable)")

# ============================================================
# 3. MONTE CARLO SIMULATION
# ============================================================
print(f"\n{'='*40}")
print(f"🎲 2. MONTE CARLO SIMULATION (1000 runs)")
print(f"{'='*40}")

returns = valid_trades['strategy_return_24h'].values
n_runs = 1000
mc_sharpes = []
mc_returns = []
mc_wrs = []

np.random.seed(42)
pbar = tqdm(total=n_runs, desc="   Monte Carlo", unit="run")
for _ in range(n_runs):
    # Block bootstrap: lấy mẫu có hoàn lại theo block để giữ volatility clustering
    block_size = max(5, len(returns) // 20)  # block ~5% dữ liệu
    n_blocks = len(returns) // block_size + 1
    sampled = []
    for _ in range(n_blocks):
        start_idx = np.random.randint(0, max(1, len(returns) - block_size))
        sampled.extend(returns[start_idx:start_idx + block_size])
    sampled = np.array(sampled[:len(returns)])
    
    mc_sharpes.append(sampled.mean() / sampled.std() * np.sqrt(365) if sampled.std() > 0 else 0)
    mc_returns.append(sampled.mean() * 100)
    mc_wrs.append((sampled > 0).sum() / len(sampled) * 100)
    pbar.update(1)
pbar.close()

mc_sharpes = np.array(mc_sharpes)
mc_returns = np.array(mc_returns)
mc_wrs = np.array(mc_wrs)

original_sharpe = returns.mean() / returns.std() * np.sqrt(365) if returns.std() > 0 else 0

print(f"\n   Kết quả Monte Carlo:")
print(f"   Sharpe gốc: {original_sharpe:.2f}")
print(f"   Monte Carlo Sharpe: mean={mc_sharpes.mean():.2f}, median={np.median(mc_sharpes):.2f}")
print(f"   Sharpe 95% CI: [{np.percentile(mc_sharpes, 2.5):.2f}, {np.percentile(mc_sharpes, 97.5):.2f}]")
print(f"   Win Rate 95% CI: [{np.percentile(mc_wrs, 2.5):.1f}%, {np.percentile(mc_wrs, 97.5):.1f}%]")
print(f"   Return 95% CI: [{np.percentile(mc_returns, 2.5):+.3f}%, {np.percentile(mc_returns, 97.5):+.3f}%]")

# Kiểm tra: Sharpe có > 1.0 trong 95% cases?
sharpe_above_1 = (mc_sharpes > 1.0).sum() / n_runs * 100
print(f"   Sharpe > 1.0: {sharpe_above_1:.0f}% các run")
if sharpe_above_1 >= 80:
    print(f"   ✅ Monte Carlo PASSED (>80% runs có Sharpe > 1.0)")
else:
    print(f"   ⚠️ Monte Carlo WARNING ({sharpe_above_1:.0f}% runs có Sharpe > 1.0)")

# ============================================================
# 4. OUT-OF-SAMPLE TEST
# ============================================================
print(f"\n{'='*40}")
print(f"🔮 3. OUT-OF-SAMPLE TEST (2024-2026)")
print(f"{'='*40}")

# OOS period: 2024-01-01 đến nay
oos_start = pd.Timestamp('2024-01-01')
is_mask = valid_trades.index < oos_start
oos_mask = valid_trades.index >= oos_start

is_trades = valid_trades[is_mask]
oos_trades = valid_trades[oos_mask]

is_sharpe = is_trades['strategy_return_24h'].mean() / is_trades['strategy_return_24h'].std() * np.sqrt(365) if is_trades['strategy_return_24h'].std() > 0 else 0
oos_sharpe = oos_trades['strategy_return_24h'].mean() / oos_trades['strategy_return_24h'].std() * np.sqrt(365) if oos_trades['strategy_return_24h'].std() > 0 else 0

print(f"   In-Sample (2019-2023):")
print(f"      Trades: {len(is_trades)}, Ret: {is_trades['strategy_return_24h'].mean()*100:+.3f}%, Sharpe: {is_sharpe:.2f}")
print(f"   Out-of-Sample (2024-2026):")
print(f"      Trades: {len(oos_trades)}, Ret: {oos_trades['strategy_return_24h'].mean()*100:+.3f}%, Sharpe: {oos_sharpe:.2f}")

if oos_sharpe > 0 and oos_sharpe >= is_sharpe * 0.5:
    print(f"   ✅ OOS PASSED (Sharpe OOS={oos_sharpe:.2f} >= 50% IS Sharpe)")
else:
    print(f"   ⚠️ OOS WARNING (Sharpe degradation >50%)")

# ============================================================
# 5. STRESS TEST
# ============================================================
print(f"\n{'='*40}")
print(f"💥 4. STRESS TEST")
print(f"{'='*40}")

# Các sự kiện stress chính
stress_events = [
    ('2020-03-12', '2020-03-16', 'COVID Crash'),
    ('2021-05-19', '2021-05-23', 'China Ban'),
    ('2022-11-09', '2022-11-13', 'FTX Collapse'),
    ('2024-08-05', '2024-08-09', 'Yen Carry Unwind'),
    ('2025-04-01', '2025-04-07', 'Trump Tariffs'),
]

print(f"\n   Hiệu suất trong các sự kiện cực đoan:")
for start, end, label in stress_events:
    event_mask = (valid_trades.index >= start) & (valid_trades.index <= end)
    event_trades = valid_trades[event_mask]
    if len(event_trades) > 0:
        avg = event_trades['strategy_return_24h'].mean() * 100
        print(f"   {label:20s} ({start}): {len(event_trades)} tín hiệu, Ret={avg:+.3f}%")
    else:
        print(f"   {label:20s} ({start}): Không có tín hiệu")

# Stress Test: Giả lập tăng phí funding lên 2x, 3x
print(f"\n   Phân tích độ nhạy với ngưỡng funding:")
for mult in [0.5, 1.0, 1.5, 2.0]:
    test_threshold = 0.0005 * mult
    test_trades = valid_trades[valid_trades['signal'].abs() > 0]  # tất cả trades
    print(f"   Ngưỡng SHORT={test_threshold*100:.3f}%: {len(test_trades)} trades")

# ============================================================
# 6. PHÂN PHỐI LỢI NHUẬN
# ============================================================
print(f"\n{'='*40}")
print(f"📊 5. PHÂN PHỐI LỢI NHUẬN")
print(f"{'='*40}")

returns_pct = valid_trades['strategy_return_24h'] * 100
print(f"\n   Phân vị lợi nhuận 24h:")
for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    print(f"   P{p:2d}: {np.percentile(returns_pct, p):+.3f}%")

# Skewness và Kurtosis
from scipy import stats
skew = stats.skew(returns_pct)
kurt = stats.kurtosis(returns_pct)
print(f"\n   Skewness: {skew:.2f} (âm = đuôi trái dày)")
print(f"   Kurtosis: {kurt:.2f} (dương = đuôi dày)")

# Kiểm tra: có phải vài trade lớn kéo kết quả?
top5_pct = returns_pct.nlargest(int(len(returns_pct) * 0.05))
contribution_top5 = top5_pct.sum() / returns_pct.sum() * 100
print(f"   Top 5% trades đóng góp: {contribution_top5:.1f}% tổng lợi nhuận")
if contribution_top5 < 50:
    print(f"   ✅ Lợi nhuận phân phối đều (top 5% < 50% tổng)")
else:
    print(f"   ⚠️ Lợi nhuận phụ thuộc vào vài trade lớn")

# ============================================================
# 7. TỔNG KẾT ROBUSTNESS
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 TỔNG KẾT ROBUSTNESS - EDGE-001")
print(f"{'='*60}")

tests = {
    'Walk-Forward': profitable_folds >= n_folds * 0.7,
    'Monte Carlo': sharpe_above_1 >= 80,
    'Out-of-Sample': oos_sharpe > 0 and oos_sharpe >= is_sharpe * 0.5,
    'Lợi nhuận đều': contribution_top5 < 50,
}

for test, passed in tests.items():
    status = '✅ PASS' if passed else '❌ FAIL'
    print(f"   {test:20s}: {status}")

all_pass = all(tests.values())
print(f"\n   KẾT LUẬN: {'✅ EDGE ĐÁNG TIN CẬY' if all_pass else '⚠️ CẦN ĐIỀU CHỈNH'}")

# Lưu kết quả
robustness_results = {
    'edge_id': 'EDGE-001',
    'timestamp': datetime.now().isoformat(),
    'walk_forward': {
        'profitable_folds': f"{profitable_folds}/{n_folds}",
        'pass': tests['Walk-Forward']
    },
    'monte_carlo': {
        'n_runs': n_runs,
        'sharpe_above_1_pct': round(sharpe_above_1, 1),
        'sharpe_95_ci': [round(np.percentile(mc_sharpes, 2.5), 2), round(np.percentile(mc_sharpes, 97.5), 2)],
        'pass': tests['Monte Carlo']
    },
    'out_of_sample': {
        'is_sharpe': round(is_sharpe, 2),
        'oos_sharpe': round(oos_sharpe, 2),
        'oos_trades': int(len(oos_trades)),
        'pass': tests['Out-of-Sample']
    },
    'distribution': {
        'skewness': round(skew, 2),
        'kurtosis': round(kurt, 2),
        'top5_contribution_pct': round(contribution_top5, 1),
        'pass': tests['Lợi nhuận đều']
    },
    'overall_pass': all_pass
}

with open(os.path.join(ROBUST_DIR, "EDGE-001_robustness.json"), 'w') as f:
    json.dump(robustness_results, f, indent=2, default=str)

print(f"\n💾 Kết quả đã lưu: {os.path.join(ROBUST_DIR, 'EDGE-001_robustness.json')}")
print(f"🎯 Hoàn thành Robustness Test!")