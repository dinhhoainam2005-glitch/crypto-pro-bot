"""
Bước 2.4 - Edge-002: OI Divergence
- Logic: Giá & OI phân kỳ → tín hiệu đảo chiều
- Giá tăng + OI giảm = SHORT (đà tăng yếu)
- Giá giảm + OI tăng = LONG (đà giảm yếu, MM tích lũy)
- Backtest toàn bộ lịch sử, có robustness test
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import os
import json
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
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📂 EDGE-002: Open Interest Divergence")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h.parquet"))
print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. ĐỊNH NGHĨA TÍN HIỆU
# ============================================================
# OI Divergence:
# - Giá 24h tăng > 2% VÀ OI 24h giảm > 1% → SHORT (giá tăng không bền vững)
# - Giá 24h giảm > 2% VÀ OI 24h tăng > 1% → LONG (giá giảm nhưng tiền vào)

print("\n🔧 Định nghĩa tín hiệu:")
print("   SHORT: Giá 24h > +2% VÀ OI 24h < -1%")
print("   LONG:  Giá 24h < -2% VÀ OI 24h > +1%")
print("   Hold 24h, KHÔNG lookahead")

# Tính thay đổi 24h (dùng shift để tránh lookahead)
df['price_change_24h'] = (df['perp_close'] - df['perp_close'].shift(24)) / df['perp_close'].shift(24)
df['oi_change_24h'] = df['open_interest'].pct_change(24)

# Tín hiệu
df['signal'] = 0

# SHORT: giá tăng mạnh nhưng OI giảm
short_mask = (df['price_change_24h'] > 0.02) & (df['oi_change_24h'] < -0.01)
df.loc[short_mask, 'signal'] = -1

# LONG: giá giảm mạnh nhưng OI tăng
long_mask = (df['price_change_24h'] < -0.02) & (df['oi_change_24h'] > 0.01)
df.loc[long_mask, 'signal'] = 1

# Shift để tránh lookahead
df['signal_shifted'] = df['signal'].shift(1)

# ============================================================
# 3. TÍNH LỢI NHUẬN
# ============================================================
for horizon in [1, 6, 12, 24]:
    df[f'return_{horizon}h'] = (df['perp_close'].shift(-horizon) - df['perp_open']) / df['perp_open']
    df[f'strategy_return_{horizon}h'] = df[f'return_{horizon}h'] * df['signal_shifted']

# ============================================================
# 4. PHÂN TÍCH TỔNG QUAN
# ============================================================
print(f"\n📊 PHÂN TÍCH TỔNG QUAN EDGE-002:")

total_signals = (df['signal'] != 0).sum()
long_signals = (df['signal'] == 1).sum()
short_signals = (df['signal'] == -1).sum()
print(f"   Tổng tín hiệu: {total_signals} ({total_signals/len(df)*100:.2f}% thời gian)")
print(f"   LONG: {long_signals} | SHORT: {short_signals}")

if total_signals == 0:
    print("\n⚠️ KHÔNG CÓ TÍN HIỆU NÀO. Cần điều chỉnh ngưỡng.")
    print("   Đang chẩn đoán phân phối OI change...")
    oi_chg = df['oi_change_24h'].dropna()
    print(f"   OI Change 24h: P1={np.percentile(oi_chg, 1):.4f}, P5={np.percentile(oi_chg, 5):.4f}")
    print(f"   P95={np.percentile(oi_chg, 95):.4f}, P99={np.percentile(oi_chg, 99):.4f}")
    exit()

print(f"\n📈 Hiệu suất trung bình theo horizon:")
for horizon in [1, 6, 12, 24]:
    col = f'strategy_return_{horizon}h'
    valid = df[df['signal_shifted'] != 0][col].dropna()
    if len(valid) > 0:
        avg_ret = valid.mean() * 100
        win_rate = (valid > 0).sum() / len(valid) * 100
        sharpe = valid.mean() / valid.std() * np.sqrt(365 * 24 / horizon) if valid.std() > 0 else 0
        print(f"   {horizon:2d}h: Return={avg_ret:+.4f}% | WR={win_rate:.1f}% | Sharpe={sharpe:.2f} | n={len(valid)}")

# ============================================================
# 5. PHÂN TÍCH THEO REGIME
# ============================================================
print(f"\n📊 THEO REGIME (horizon 24h):")
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = (df['regime'] == regime) & (df['signal_shifted'] != 0)
    valid = df.loc[mask, 'strategy_return_24h'].dropna()
    if len(valid) >= 5:
        avg_ret = valid.mean() * 100
        win_rate = (valid > 0).sum() / len(valid) * 100
        sharpe = valid.mean() / valid.std() * np.sqrt(365) if valid.std() > 0 else 0
        status = '✅' if avg_ret > 0.1 else ('⚠️' if avg_ret > 0 else '❌')
        print(f"   {regime:12s}: Ret={avg_ret:+.3f}% | WR={win_rate:.1f}% | Sharpe={sharpe:.2f} | n={len(valid)} {status}")

# ============================================================
# 6. ROBUSTNESS TEST NHANH
# ============================================================
print(f"\n🔬 ROBUSTNESS TEST:")

# Out-of-Sample
valid_trades = df[df['signal_shifted'] != 0].dropna(subset=['strategy_return_24h'])
oos_start = pd.Timestamp('2024-01-01')
is_trades = valid_trades[valid_trades.index < oos_start]
oos_trades = valid_trades[valid_trades.index >= oos_start]

if len(oos_trades) >= 5:
    is_sharpe = is_trades['strategy_return_24h'].mean() / is_trades['strategy_return_24h'].std() * np.sqrt(365) if is_trades['strategy_return_24h'].std() > 0 else 0
    oos_sharpe = oos_trades['strategy_return_24h'].mean() / oos_trades['strategy_return_24h'].std() * np.sqrt(365) if oos_trades['strategy_return_24h'].std() > 0 else 0
    oos_ret = oos_trades['strategy_return_24h'].mean() * 100
    print(f"   IS Sharpe: {is_sharpe:.2f} | OOS Sharpe: {oos_sharpe:.2f} | OOS Ret: {oos_ret:+.3f}% | OOS n={len(oos_trades)}")

# Top 5% contribution
returns_pct = valid_trades['strategy_return_24h'] * 100
top5 = returns_pct.nlargest(int(len(returns_pct) * 0.05))
top5_contrib = top5.sum() / returns_pct.sum() * 100 if returns_pct.sum() != 0 else 0
print(f"   Top 5% đóng góp: {top5_contrib:.1f}%")

# Walk-Forward nhanh (6 folds, mỗi fold 1 năm)
n_folds = 6
fold_days = (valid_trades.index[-1] - valid_trades.index[0]).days // n_folds
profitable = 0
for i in range(n_folds):
    fold_start = valid_trades.index[0] + timedelta(days=i * fold_days)
    fold_end = fold_start + timedelta(days=fold_days)
    fold = valid_trades[(valid_trades.index >= fold_start) & (valid_trades.index < fold_end)]
    if len(fold) >= 3:
        if fold['strategy_return_24h'].mean() > 0:
            profitable += 1
print(f"   Walk-Forward: {profitable}/{n_folds} folds profitable")

# ============================================================
# 7. LƯU KẾT QUẢ
# ============================================================
edge_002 = {
    'edge_id': 'EDGE-002',
    'name': 'OI Divergence',
    'logic': 'Giá và OI phân kỳ báo hiệu đảo chiều. MM giảm inventory khi giá đi ngược dòng tiền thật.',
    'status': 'ACTIVE' if (oos_sharpe > 0 if len(oos_trades) >= 5 else True) else 'UNDER_REVIEW',
    'total_signals': int(total_signals),
    'oos_sharpe': round(oos_sharpe, 2) if len(oos_trades) >= 5 else None,
    'top5_contrib_pct': round(top5_contrib, 1),
    'wf_profitable': f"{profitable}/{n_folds}",
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-002_metadata.json"), 'w') as f:
    json.dump(edge_002, f, indent=2, default=str)

edge_signals = df[['signal', 'signal_shifted', 'price_change_24h', 'oi_change_24h',
                    'strategy_return_1h', 'strategy_return_6h', 'strategy_return_12h', 
                    'strategy_return_24h', 'regime']].copy()
edge_signals.to_parquet(os.path.join(EDGE_DIR, "EDGE-002_signals.parquet"))

print(f"\n💾 Đã lưu EDGE-002")
print(f"🎯 Hoàn thành Edge-002!")