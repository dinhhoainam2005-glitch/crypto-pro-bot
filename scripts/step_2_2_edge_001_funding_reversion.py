"""
Bước 2.2 - Edge-001: Funding Rate Extreme Reversion (ĐÃ SỬA)
- Logic: Funding rate vượt ngưỡng tuyệt đối → reversion
- Ngưỡng SHORT: funding > +0.0005 (top ~5% phân phối thực tế)
- Ngưỡng LONG:  funding < -0.0001 (bottom ~5% phân phối thực tế)
- Hold 24h, đo lường return
- KHÔNG lookahead, KHÔNG data leakage
"""

import pandas as pd
import numpy as np
from datetime import datetime
from tqdm import tqdm
import os
import json
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "processed")
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
os.makedirs(EDGE_DIR, exist_ok=True)

# ============================================================
# 1. LOAD DỮ LIỆU
# ============================================================
print("="*60)
print("📂 EDGE-001: Funding Rate Extreme Reversion (v2)")
print("="*60)

df = pd.read_parquet(os.path.join(OUTPUT_DIR, "btc_merged_1h.parquet"))
print(f"\n📥 Dữ liệu: {len(df)} nến | {df.index[0]} → {df.index[-1]}")

# ============================================================
# 2. ĐỊNH NGHĨA TÍN HIỆU (đã sửa)
# ============================================================
# Dựa trên phân phối thực tế:
#   P95 ≈ 0.00046, P99 ≈ 0.00101
#   P5  ≈ -0.000053, P1 ≈ -0.0002
# Chọn ngưỡng:
SHORT_THRESHOLD = 0.0005   # funding > 0.05% → SHORT (quá bullish → reversion giảm)
LONG_THRESHOLD = -0.0001   # funding < -0.01% → LONG (quá bearish → reversion tăng)

print(f"\n🔧 Định nghĩa tín hiệu:")
print(f"   SHORT khi funding_rate > +{SHORT_THRESHOLD:.4f} ({SHORT_THRESHOLD*100:.2f}%)")
print(f"   LONG  khi funding_rate < {LONG_THRESHOLD:.4f} ({LONG_THRESHOLD*100:.2f}%)")
print(f"   Hold 24h, vào lệnh đầu nến tiếp theo (KHÔNG lookahead)")

# Tín hiệu
df['signal'] = 0
short_mask = df['funding_rate'] > SHORT_THRESHOLD
long_mask = df['funding_rate'] < LONG_THRESHOLD
df.loc[short_mask, 'signal'] = -1
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
print(f"\n📊 PHÂN TÍCH TỔNG QUAN EDGE-001:")

total_signals = (df['signal'] != 0).sum()
long_signals = (df['signal'] == 1).sum()
short_signals = (df['signal'] == -1).sum()
print(f"   Tổng tín hiệu: {total_signals} ({total_signals/len(df)*100:.2f}% thời gian)")
print(f"   LONG: {long_signals} | SHORT: {short_signals}")

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
print(f"\n📊 PHÂN TÍCH THEO REGIME (horizon 24h):")

regime_stats = {}
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = (df['regime'] == regime) & (df['signal_shifted'] != 0)
    valid = df.loc[mask, 'strategy_return_24h'].dropna()
    
    if len(valid) >= 5:
        avg_ret = valid.mean() * 100
        win_rate = (valid > 0).sum() / len(valid) * 100
        sharpe = valid.mean() / valid.std() * np.sqrt(365) if valid.std() > 0 else 0
        regime_stats[regime] = {
            'count': int(len(valid)),
            'avg_return_pct': round(avg_ret, 3),
            'win_rate_pct': round(win_rate, 1),
            'sharpe': round(sharpe, 2)
        }
        status = '✅ TỐT' if avg_ret > 0.05 else ('⚠️ YẾU' if avg_ret > 0 else '❌ XẤU')
        print(f"   {regime:12s}: Ret={avg_ret:+.3f}% | WR={win_rate:.1f}% | Sharpe={sharpe:.2f} | n={len(valid)} {status}")
    else:
        regime_stats[regime] = {'count': 0, 'note': 'insufficient data'}
        print(f"   {regime:12s}: Không đủ dữ liệu (n={len(valid)})")

# ============================================================
# 6. PHÂN TÍCH LONG vs SHORT RIÊNG
# ============================================================
print(f"\n📊 LONG vs SHORT (horizon 24h):")
for direction, label in [(1, 'LONG'), (-1, 'SHORT')]:
    mask = (df['signal_shifted'] == direction)
    valid = df.loc[mask, 'strategy_return_24h'].dropna()
    if len(valid) > 0:
        avg_ret = valid.mean() * 100
        win_rate = (valid > 0).sum() / len(valid) * 100
        print(f"   {label:6s}: Ret={avg_ret:+.3f}% | WR={win_rate:.1f}% | n={len(valid)}")

# ============================================================
# 7. EQUITY CURVE TÍCH LŨY
# ============================================================
df['equity_24h'] = df['strategy_return_24h'].fillna(0).cumsum()
final_equity = df['equity_24h'].iloc[-1]
max_equity = df['equity_24h'].cummax()
drawdown = df['equity_24h'] - max_equity
max_dd = drawdown.min()

print(f"\n📈 Equity Curve (24h):")
print(f"   Final: {final_equity:+.3f} ({final_equity*100:+.1f}%)")
print(f"   Max DD: {max_dd:.3f} ({max_dd*100:.1f}%)")

# ============================================================
# 8. LƯU EDGE DATABASE
# ============================================================
print(f"\n💾 Lưu Edge-001...")

edge_001 = {
    'edge_id': 'EDGE-001',
    'version': 'v2',
    'name': 'Funding Rate Extreme Reversion',
    'logic': 'Khi funding rate vượt ngưỡng tuyệt đối (SHORT>0.05%, LONG<-0.01%), giá có xu hướng đảo chiều do áp lực tái cân bằng vị thế',
    'signal_type': 'Mean Reversion',
    'horizon': '24h',
    'short_threshold': SHORT_THRESHOLD,
    'long_threshold': LONG_THRESHOLD,
    'total_signals': int(total_signals),
    'long_signals': int(long_signals),
    'short_signals': int(short_signals),
    'final_equity_pct': round(final_equity * 100, 2),
    'max_drawdown_pct': round(max_dd * 100, 2),
    'regime_performance': regime_stats,
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(EDGE_DIR, "EDGE-001_metadata.json"), 'w') as f:
    json.dump(edge_001, f, indent=2, default=str)
print(f"   ✅ EDGE-001_metadata.json")

edge_signals = df[['signal', 'signal_shifted', 'funding_rate',
                    'strategy_return_1h', 'strategy_return_6h', 
                    'strategy_return_12h', 'strategy_return_24h',
                    'regime']].copy()
edge_signals.to_parquet(os.path.join(EDGE_DIR, "EDGE-001_signals.parquet"))
print(f"   ✅ EDGE-001_signals.parquet")

print("\n" + "="*60)
print("🎯 Hoàn thành Edge-001 v2!")
print("="*60)