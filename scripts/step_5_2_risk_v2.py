"""
RISK MANAGEMENT v2.0 - Trailing Stop + Volatility-Adjusted Sizing
- Trailing Stop: 3 ATR, khóa lợi nhuận khi giá chạy
- Vol Sizing: Giảm size khi ATR cao, tăng khi ATR thấp
- Keep: Kelly + DD Control từ v1
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
print("🛡️ RISK MANAGEMENT v2.0")
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
# 3. RISK PARAMETERS
# ============================================================
INITIAL_CAPITAL = 10000
TRAILING_ATR_MULT = 3.0        # Trailing stop = 3 ATR
MAX_DD_1 = 0.20                 # Giảm 50% size
MAX_DD_2 = 0.30                 # Giảm 75% size
MAX_DD_3 = 0.40                 # Dừng hẳn
BASE_SIZE = 0.25                # Base position size 25%

# ============================================================
# 4. BACKTEST V2
# ============================================================
print("\n📊 Backtest v2 (Trailing Stop + Vol Sizing)...")

capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
trades_log = []

# Pre-compute để tăng tốc
signal_indices = df[df['sig'] == 1].index

pbar = tqdm(total=len(signal_indices), desc="   Backtest", unit="lệnh")
for entry_time in signal_indices:
    entry_idx = df.index.get_loc(entry_time)
    
    # DD hiện tại
    current_dd = (peak_capital - capital) / peak_capital
    
    # DD Size Multiplier
    if current_dd > MAX_DD_3:
        size_mult = 0
    elif current_dd > MAX_DD_2:
        size_mult = 0.25
    elif current_dd > MAX_DD_1:
        size_mult = 0.5
    else:
        size_mult = 1.0
    
    if size_mult == 0:
        trades_log.append({'time': entry_time, 'return_pct': 0, 'pnl': 0, 'capital': capital,
                          'size_pct': 0, 'exit_reason': 'DD_STOP'})
        pbar.update(1)
        continue
    
    # Entry
    entry_price = df.iloc[entry_idx]['perp_open']
    atr_pct = df.iloc[entry_idx]['atr_pct']
    atr_median = df.iloc[entry_idx]['atr_median']
    
    # VOL SIZING: giảm size khi ATR cao hơn median
    if atr_pct > atr_median * 1.5:
        vol_mult = 0.5  # Vol cao gấp 1.5x → giảm nửa size
    elif atr_pct > atr_median:
        vol_mult = 0.75
    elif atr_pct < atr_median * 0.5:
        vol_mult = 1.5  # Vol thấp → tăng size
    else:
        vol_mult = 1.0
    
    position_size = BASE_SIZE * size_mult * vol_mult
    position_size = max(0.05, min(0.5, position_size))  # Clamp 5-50%
    
    # Trailing Stop: bắt đầu từ 3 ATR dưới entry
    trailing_stop = entry_price * (1 - TRAILING_ATR_MULT * atr_pct / 100)
    stop_loss = entry_price * (1 - 2 * atr_pct / 100)  # Hard stop = 2 ATR
    
    # Mô phỏng 12 nến tiếp theo
    exit_idx = min(entry_idx + 12, len(df) - 1)
    exit_price = None
    exit_reason = None
    
    highest_price = entry_price
    
    for i in range(entry_idx + 1, exit_idx + 1):
        current_low = df.iloc[i]['perp_low']
        current_high = df.iloc[i]['perp_high']
        current_close = df.iloc[i]['perp_close']
        
        # Cập nhật highest price cho trailing stop
        if current_high > highest_price:
            highest_price = current_high
            # Nâng trailing stop lên (lock profit)
            new_trail = highest_price * (1 - TRAILING_ATR_MULT * atr_pct / 100)
            trailing_stop = max(trailing_stop, new_trail)
        
        # Kiểm tra stop loss (hard stop hoặc trailing)
        if current_low <= stop_loss:
            exit_price = stop_loss
            exit_reason = 'STOP_LOSS'
            break
        elif current_low <= trailing_stop:
            exit_price = trailing_stop
            exit_reason = 'TRAILING_STOP'
            break
    
    # Nếu không bị stop, thoát ở giá đóng cửa
    if exit_price is None:
        exit_price = df.iloc[exit_idx]['perp_close']
        exit_reason = 'TP/Time'
    
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
        'dd_mult': size_mult,
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

if len(actual) > 0:
    print(f"\n📊 KẾT QUẢ RISK MANAGEMENT v2:")
    print(f"   Capital: ${INITIAL_CAPITAL:,.0f} → ${capital:,.0f}")
    print(f"   Return:  {(capital/INITIAL_CAPITAL - 1)*100:+.2f}%")
    
    total = len(actual)
    wins = (actual['return_pct'] > 0).sum()
    wr = wins / total * 100
    
    sl = (actual['exit_reason'] == 'STOP_LOSS').sum()
    trail = (actual['exit_reason'] == 'TRAILING_STOP').sum()
    tp = (actual['exit_reason'] == 'TP/Time').sum()
    
    print(f"\n📈 THỐNG KÊ:")
    print(f"   Tổng lệnh:       {total}")
    print(f"   Thắng:           {wins} ({wr:.1f}%)")
    print(f"   Stop Loss:       {sl}")
    print(f"   Trailing Stop:   {trail}")
    print(f"   TP/Time:         {tp}")
    
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
    
    # Vol sizing stats
    avg_size = actual['size_pct'].mean()
    print(f"\n📏 POSITION SIZING:")
    print(f"   Size TB:         {avg_size:.1f}%")
    print(f"   Size min/max:    {actual['size_pct'].min():.0f}% / {actual['size_pct'].max():.0f}%")
    
    # So sánh v1 vs v2
    print(f"\n🔍 SO SÁNH v1 vs v2:")
    print(f"   {'Chỉ số':<20} {'v1 (Fixed SL)':<15} {'v2 (Trail+Vol)':<15}")
    print(f"   {'-'*50}")
    print(f"   {'Return':<20} {'+55.2%':<15} {f'{(capital/INITIAL_CAPITAL-1)*100:+.2f}%':<15}")
    print(f"   {'Max DD':<20} {'-35.1%':<15} {f'{max_dd:.2f}%':<15}")
    print(f"   {'Profit Factor':<20} {'1.10':<15} {f'{pf:.2f}':<15}")
    print(f"   {'Win Rate':<20} {'51.8%':<15} {f'{wr:.1f}%':<15}")

# ============================================================
# 6. LƯU
# ============================================================
trades_df.to_parquet(os.path.join(RISK_DIR, "risk_v2_trades.parquet"))

summary = {
    'version': 'v2.0',
    'features': ['Trailing Stop (3 ATR)', 'Volatility-Adjusted Sizing', 'Kelly + DD Control'],
    'initial_capital': INITIAL_CAPITAL,
    'final_capital': round(capital, 2),
    'total_return_pct': round((capital/INITIAL_CAPITAL - 1)*100, 2),
    'max_drawdown_pct': round(max_dd, 2),
    'total_trades': int(total),
    'win_rate_pct': round(wr, 1),
    'profit_factor': round(pf, 2),
    'sharpe': round(sh, 2),
    'avg_size_pct': round(avg_size, 1),
    'stop_loss_count': int(sl),
    'trailing_stop_count': int(trail),
    'timestamp': datetime.now().isoformat()
}

with open(os.path.join(RISK_DIR, "risk_v2_summary.json"), 'w') as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\n💾 Đã lưu Risk Management v2")
print(f"🎯 Hoàn thành!")