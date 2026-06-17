"""
RISK MANAGEMENT v3.0 - CÂN BẰNG
- Fixed Stop Loss 2 ATR (giữ từ v1)
- Vol Sizing nhẹ: giảm 25% khi vol > 1.5x median
- Kelly + DD Control (giữ nguyên)
- Mục tiêu: Max DD < 25%, Return > 30%
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
RISK_DIR = os.path.join(BASE_DIR, "data", "risk")
os.makedirs(RISK_DIR, exist_ok=True)

print("="*60)
print("🛡️ RISK MANAGEMENT v3.0 - CÂN BẰNG")
print("="*60)

# ============================================================
# 1. LOAD & CHUẨN BỊ
# ============================================================
df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

# Indicators
df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 1), raw=True)
df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)
df['funding_p10'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 10), raw=True)
df['funding_p95'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)
df['cvd_12h'] = df['cvd'].diff(12)
df['cvd_24h'] = df['cvd'].diff(24)
df['oi_24h'] = df['oi'].pct_change(24)
df['price_ma50'] = df['perp_close'].rolling(50).mean()
df['price_chg_24h'] = df['perp_close'].pct_change(24)
df['delta_24h'] = df['delta_volume'].diff(24)
df['vol_ma24'] = df['perp_volume'].rolling(24).mean()
df['vol_p99'] = df['perp_volume'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 99), raw=True)
df['atr_14'] = (df['perp_high'] - df['perp_low']).rolling(14).mean()
df['atr_pct'] = df['atr_14'] / df['perp_close'] * 100
df['atr_median'] = df['atr_pct'].rolling(500, min_periods=100).median()

# ============================================================
# 2. ENSEMBLE SIGNALS
# ============================================================
df['eA'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
df['eB'] = ((df['funding_rate'] < df['funding_p10']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
df['eC'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0) & (df['oi_24h'] > 0)).astype(int)
df['eD'] = ((df['funding_rate'] < df['funding_p5']) & (df['cvd_12h'] < 0) & (df['perp_close'] < df['price_ma50'])).astype(int)
df['eE'] = ((df['funding_rate'] < df['funding_p1']) & (df['cvd_24h'] < 0)).astype(int)
df['eF'] = ((df['funding_rate'] > df['funding_p95']) & (df['price_chg_24h'] > 0.02) & (df['funding_rate'] > 0)).astype(int)
df['eG'] = ((df['delta_24h'] > 0) & (df['cvd_24h'] > 0) & (df['perp_volume'] > df['vol_ma24'])).astype(int)
df['eH'] = ((df['funding_rate'] < 0) & (df['perp_volume'] > df['vol_p99'])).astype(int)

df['votes'] = df['eA'] + df['eB'] + df['eC'] + df['eD'] + df['eE'] + df['eF'] + df['eG'] + df['eH']
df['sig_raw'] = (df['votes'] >= 2).astype(int)
df['sig'] = df['sig_raw'].shift(1)

# ============================================================
# 3. RISK PARAMETERS V3
# ============================================================
INITIAL_CAPITAL = 10000
STOP_LOSS_ATR = 2.0           # Fixed 2 ATR stop loss
MAX_DD_1 = 0.20               # Giảm 50% size
MAX_DD_2 = 0.30               # Giảm 75% size
MAX_DD_3 = 0.40               # Dừng
BASE_SIZE = 0.25              # 25% base

# ============================================================
# 4. BACKTEST V3
# ============================================================
print("\n📊 Backtest v3 (Cân bằng)...")

capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
trades_log = []

signal_indices = df[df['sig'] == 1].index

pbar = tqdm(total=len(signal_indices), desc="   Backtest", unit="lệnh")
for entry_time in signal_indices:
    entry_idx = df.index.get_loc(entry_time)
    
    # DD Control
    current_dd = (peak_capital - capital) / peak_capital
    if current_dd > MAX_DD_3:
        dd_mult = 0
    elif current_dd > MAX_DD_2:
        dd_mult = 0.25
    elif current_dd > MAX_DD_1:
        dd_mult = 0.5
    else:
        dd_mult = 1.0
    
    if dd_mult == 0:
        trades_log.append({'time': entry_time, 'return_pct': 0, 'pnl': 0, 'capital': capital,
                          'size_pct': 0, 'exit_reason': 'DD_STOP', 'atr_pct': 0, 'vol_mult': 0})
        pbar.update(1)
        continue
    
    # Entry
    entry_price = df.iloc[entry_idx]['perp_open']
    atr_pct = df.iloc[entry_idx]['atr_pct']
    atr_median = df.iloc[entry_idx]['atr_median']
    
    # VOL SIZING NHẸ: chỉ giảm 25% khi vol rất cao
    if atr_pct > atr_median * 2.0:
        vol_mult = 0.75
    elif atr_pct > atr_median * 1.5:
        vol_mult = 0.85
    elif atr_pct < atr_median * 0.5:
        vol_mult = 1.15  # Vol thấp → tăng nhẹ
    else:
        vol_mult = 1.0
    
    position_size = BASE_SIZE * dd_mult * vol_mult
    position_size = max(0.05, min(0.40, position_size))  # 5-40%
    
    # Fixed Stop Loss 2 ATR
    stop_loss = entry_price * (1 - STOP_LOSS_ATR * atr_pct / 100)
    
    # Mô phỏng 12 nến
    exit_idx = min(entry_idx + 12, len(df) - 1)
    exit_price = None
    exit_reason = None
    
    for i in range(entry_idx + 1, exit_idx + 1):
        current_low = df.iloc[i]['perp_low']
        if current_low <= stop_loss:
            exit_price = stop_loss
            exit_reason = 'STOP_LOSS'
            break
    
    if exit_price is None:
        exit_price = df.iloc[exit_idx]['perp_close']
        exit_reason = 'TP'
    
    trade_return = (exit_price - entry_price) / entry_price
    trade_pnl = capital * position_size * trade_return
    capital += trade_pnl
    
    if capital > peak_capital:
        peak_capital = capital
    
    trades_log.append({
        'time': entry_time,
        'entry': entry_price,
        'exit': exit_price,
        'return_pct': trade_return * 100,
        'pnl': trade_pnl,
        'capital': capital,
        'size_pct': position_size * 100,
        'vol_mult': vol_mult,
        'dd_mult': dd_mult,
        'atr_pct': atr_pct,
        'exit_reason': exit_reason
    })
    
    pbar.update(1)
pbar.close()

# ============================================================
# 5. PHÂN TÍCH
# ============================================================
trades_df = pd.DataFrame(trades_log)
actual = trades_df[trades_df['exit_reason'] != 'DD_STOP']

print(f"\n📊 KẾT QUẢ RISK MANAGEMENT v3:")
print(f"   Capital: ${INITIAL_CAPITAL:,.0f} → ${capital:,.0f}")
print(f"   Return:  {(capital/INITIAL_CAPITAL - 1)*100:+.2f}%")

total = len(actual)
wins = (actual['return_pct'] > 0).sum()
wr = wins / total * 100
sl = (actual['exit_reason'] == 'STOP_LOSS').sum()
tp = (actual['exit_reason'] == 'TP').sum()

print(f"\n📈 THỐNG KÊ:")
print(f"   Tổng lệnh:       {total}")
print(f"   Thắng:           {wins} ({wr:.1f}%)")
print(f"   Stop Loss:       {sl} ({sl/total*100:.1f}%)")
print(f"   TP:              {tp} ({tp/total*100:.1f}%)")

rets = actual['return_pct']
avg_ret = rets.mean()
avg_win = rets[rets > 0].mean() if wins > 0 else 0
avg_loss = rets[rets < 0].mean() if (total - wins) > 0 else 0
pf = abs(avg_win / avg_loss) if avg_loss != 0 else 999

print(f"\n📊 HIỆU SUẤT:")
print(f"   Return TB/lệnh:  {avg_ret:+.2f}%")
print(f"   Win TB:          {avg_win:+.2f}%")
print(f"   Loss TB:         {avg_loss:+.2f}%")
print(f"   Profit Factor:   {pf:.2f}")

sh = rets.mean() / rets.std() * np.sqrt(365*2) if rets.std() > 0 else 0
print(f"   Sharpe (12h):    {sh:.2f}")

# Drawdown
cap_series = pd.Series([t['capital'] for t in trades_log], 
                       index=[t['time'] for t in trades_log])
max_cap = cap_series.cummax()
dd = (cap_series - max_cap) / max_cap * 100
max_dd = dd.min()

print(f"\n📉 DRAWDOWN:")
print(f"   Max DD:          {max_dd:.2f}%")

avg_size = actual['size_pct'].mean()
print(f"\n📏 POSITION SIZING:")
print(f"   Size TB:         {avg_size:.1f}%")
print(f"   Size range:      {actual['size_pct'].min():.0f}% - {actual['size_pct'].max():.0f}%")

# Vol sizing activation
vol_reduced = (actual['vol_mult'] < 1.0).sum()
vol_increased = (actual['vol_mult'] > 1.0).sum()
print(f"\n⚡ VOL SIZING:")
print(f"   Giảm size:       {vol_reduced} lần")
print(f"   Tăng size:       {vol_increased} lần")

# ============================================================
# 6. TỔNG KẾT 3 PHIÊN BẢN
# ============================================================
print(f"\n🔍 TỔNG KẾT 3 PHIÊN BẢN:")
print(f"   {'Chỉ số':<20} {'v1 (Fixed)':<15} {'v2 (Trail)':<15} {'v3 (Balance)':<15}")
print(f"   {'-'*65}")
print(f"   {'Return':<20} {'+55.2%':<15} {'+7.6%':<15} {f'{(capital/INITIAL_CAPITAL-1)*100:+.2f}%':<15}")
print(f"   {'Max DD':<20} {'-35.1%':<15} {'-15.9%':<15} {f'{max_dd:.2f}%':<15}")
print(f"   {'Profit Factor':<20} {'1.10':<15} {'1.05':<15} {f'{pf:.2f}':<15}")
print(f"   {'Win Rate':<20} {'51.8%':<15} {'50.3%':<15} {f'{wr:.1f}%':<15}")
print(f"   {'Sharpe':<20} {'1.62':<15} {'0.49':<15} {f'{sh:.2f}':<15}")

# Lưu
trades_df.to_parquet(os.path.join(RISK_DIR, "risk_v3_trades.parquet"))

summary = {
    'version': 'v3.0',
    'features': ['Fixed SL 2 ATR', 'Vol Sizing nhẹ (0.75-1.15)', 'Kelly + DD Control'],
    'initial_capital': INITIAL_CAPITAL,
    'final_capital': round(capital, 2),
    'total_return_pct': round((capital/INITIAL_CAPITAL - 1)*100, 2),
    'max_drawdown_pct': round(max_dd, 2),
    'total_trades': int(total),
    'win_rate_pct': round(wr, 1),
    'profit_factor': round(pf, 2),
    'sharpe': round(sh, 2),
    'avg_size_pct': round(avg_size, 1),
    'stop_loss_hit': int(sl),
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(RISK_DIR, "risk_v3_summary.json"), 'w') as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n💾 Đã lưu Risk Management v3")
print(f"🎯 Hoàn thành!")