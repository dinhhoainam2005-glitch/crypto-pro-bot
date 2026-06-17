"""
RISK MANAGEMENT ENGINE v1.0
- Position Sizing: Kelly Criterion + Volatility Adjusted
- Stop Loss: ATR-based
- Max DD Control: Tự động giảm vị thế khi vượt ngưỡng
- Backtest Ensemble V2 với Risk Management
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
ENSEMBLE_DIR = os.path.join(BASE_DIR, "data", "ensemble")
RISK_DIR = os.path.join(BASE_DIR, "data", "risk")
os.makedirs(ENSEMBLE_DIR, exist_ok=True)
os.makedirs(RISK_DIR, exist_ok=True)

print("="*60)
print("🛡️ RISK MANAGEMENT ENGINE v1.0")
print("="*60)

# ============================================================
# 1. LOAD ENSEMBLE V2
# ============================================================
df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

# Tính indicators cần thiết
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

# ============================================================
# 2. ENSEMBLE V2 SIGNALS
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

# Return thô
df['ret_12h'] = (df['perp_close'].shift(-12) - df['perp_open']) / df['perp_open']
df['strategy_ret'] = df['ret_12h'] * df['sig']

# ============================================================
# 3. RISK MANAGEMENT COMPONENTS
# ============================================================
print("\n🔧 Tính toán Risk Components...")

# 3.1 KELLY CRITERION POSITION SIZING
# f* = (p * b - q) / b
# p = win rate, b = avg_win / avg_loss ratio
# Dùng rolling window 50 trades để tính Kelly động
valid = df[df['sig'] != 0].dropna(subset=['strategy_ret'])

# Tính Kelly Fraction động
df['kelly_fraction'] = 0.25  # Mặc định 25% vốn (Half-Kelly an toàn)

# Tính rolling win rate và payoff ratio
win_streak = (valid['strategy_ret'] > 0).rolling(50, min_periods=10).mean()
avg_win = valid['strategy_ret'][valid['strategy_ret'] > 0].rolling(50, min_periods=10).mean()
avg_loss = abs(valid['strategy_ret'][valid['strategy_ret'] < 0].rolling(50, min_periods=10).mean())

# Kelly: f = p - (1-p)/(avg_win/avg_loss)
kelly_raw = win_streak - (1 - win_streak) / (avg_win / avg_loss.replace(0, 0.01))
kelly_raw = kelly_raw.clip(0, 0.5)  # Giới hạn 0-50%

# Map Kelly fraction về df
df['kelly'] = 0.25
for idx in valid.index:
    if idx in kelly_raw.index:
        df.loc[idx, 'kelly'] = max(0.1, min(0.5, kelly_raw.loc[idx]))

# 3.2 ATR-BASED STOP LOSS
# Stop loss = 2x ATR
df['stop_loss_pct'] = df['atr_pct'] * 2  # 2 ATR
df['stop_loss_pct'] = df['stop_loss_pct'].clip(1, 10)  # Giới hạn 1-10%

# 3.3 MAX DRAWDOWN CONTROL
# Khi drawdown > 20%: giảm position size 50%
# Khi drawdown > 30%: giảm 75%
# Khi drawdown > 40%: dừng giao dịch

# ============================================================
# 4. BACKTEST VỚI RISK MANAGEMENT
# ============================================================
print("📊 Backtest với Risk Management...")

# Parameters
INITIAL_CAPITAL = 10000  # $10,000
MAX_DD_THRESHOLD_1 = 0.20  # Giảm 50% size
MAX_DD_THRESHOLD_2 = 0.30  # Giảm 75% size
MAX_DD_THRESHOLD_3 = 0.40  # Dừng hẳn

capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
equity_curve = []
trades_log = []
position_sizes = []
dd_levels = []

for idx in df.index:
    # Chỉ vào lệnh khi có tín hiệu
    if df.loc[idx, 'sig'] != 0:
        # Tính drawdown hiện tại
        current_dd = (peak_capital - capital) / peak_capital
        
        # DD Control: giảm size
        if current_dd > MAX_DD_THRESHOLD_3:
            size_multiplier = 0  # Dừng
        elif current_dd > MAX_DD_THRESHOLD_2:
            size_multiplier = 0.25
        elif current_dd > MAX_DD_THRESHOLD_1:
            size_multiplier = 0.5
        else:
            size_multiplier = 1.0
        
        if size_multiplier > 0:
            # Kelly-adjusted position size
            kelly = df.loc[idx, 'kelly']
            position_pct = kelly * size_multiplier
            
            # Stop loss
            stop_loss = df.loc[idx, 'stop_loss_pct'] / 100
            entry_price = df.loc[idx, 'perp_open']
            stop_price = entry_price * (1 - stop_loss)
            
            # Return của lệnh này
            future_idx = df.index.get_loc(idx) + 12
            if future_idx < len(df):
                exit_price = df.iloc[future_idx]['perp_close']
                raw_return = (exit_price - entry_price) / entry_price
                
                # Kiểm tra stop loss
                # Trong thực tế cần tick data, ở đây dùng low của 12 nến
                lowest = df.iloc[df.index.get_loc(idx):future_idx+1]['perp_low'].min()
                stopped_out = lowest <= stop_price
                
                if stopped_out:
                    trade_return = -stop_loss
                    exit_reason = 'STOP_LOSS'
                else:
                    trade_return = raw_return
                    exit_reason = 'TP/Time'
                
                # Cập nhật capital
                trade_pnl = capital * position_pct * trade_return
                capital += trade_pnl
                
                # Cập nhật peak
                if capital > peak_capital:
                    peak_capital = capital
                
                trades_log.append({
                    'time': idx,
                    'entry': entry_price,
                    'exit': exit_price,
                    'return_pct': trade_return * 100,
                    'pnl': trade_pnl,
                    'capital': capital,
                    'position_pct': position_pct * 100,
                    'kelly': kelly * 100,
                    'dd_multiplier': size_multiplier,
                    'exit_reason': exit_reason
                })
        else:
            # Dừng giao dịch do DD quá cao
            trades_log.append({
                'time': idx,
                'entry': 0,
                'exit': 0,
                'return_pct': 0,
                'pnl': 0,
                'capital': capital,
                'position_pct': 0,
                'kelly': 0,
                'dd_multiplier': 0,
                'exit_reason': 'DD_STOP'
            })
    
    equity_curve.append(capital)

# ============================================================
# 5. PHÂN TÍCH KẾT QUẢ
# ============================================================
trades_df = pd.DataFrame(trades_log)

if len(trades_df) > 0:
    actual_trades = trades_df[trades_df['entry'] > 0]
    
    print(f"\n📊 KẾT QUẢ RISK MANAGEMENT:")
    print(f"   Capital ban đầu: ${INITIAL_CAPITAL:,.0f}")
    print(f"   Capital cuối:    ${capital:,.0f}")
    print(f"   Tổng return:     {(capital/INITIAL_CAPITAL - 1)*100:+.2f}%")
    
    total_trades = len(actual_trades)
    winning_trades = (actual_trades['return_pct'] > 0).sum()
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
    
    print(f"\n📈 THỐNG KÊ GIAO DỊCH:")
    print(f"   Tổng lệnh:       {total_trades}")
    print(f"   Thắng:           {winning_trades} ({win_rate:.1f}%)")
    print(f"   Stop Loss hit:   {(actual_trades['exit_reason']=='STOP_LOSS').sum()}")
    print(f"   DD Stops:        {(trades_df['exit_reason']=='DD_STOP').sum()}")
    
    rets = actual_trades['return_pct']
    if len(rets) > 0:
        avg_ret = rets.mean()
        avg_win = rets[rets > 0].mean() if (rets > 0).sum() > 0 else 0
        avg_loss = rets[rets < 0].mean() if (rets < 0).sum() > 0 else 0
        
        print(f"\n📊 HIỆU SUẤT:")
        print(f"   Return TB/lệnh:  {avg_ret:+.2f}%")
        print(f"   Win TB:          {avg_win:+.2f}%")
        print(f"   Loss TB:         {avg_loss:+.2f}%")
        print(f"   Profit Factor:   {abs(avg_win/avg_loss) if avg_loss != 0 else 999:.2f}")
        
        # Sharpe
        sh = rets.mean() / rets.std() * np.sqrt(365*2) if rets.std() > 0 else 0
        print(f"   Sharpe (12h):    {sh:.2f}")
    
    # Equity curve stats
    equity = pd.Series(equity_curve, index=df.index)
    max_eq = equity.cummax()
    dd = (equity - max_eq) / max_eq * 100
    max_dd = dd.min()
    max_dd_idx = dd.idxmin()
    
    print(f"\n📉 DRAWDOWN:")
    print(f"   Max DD:          {max_dd:.2f}%")
    print(f"   Thời điểm:       {max_dd_idx}")
    
    # So sánh với không Risk Management
    no_risk_ret = df['strategy_ret'].dropna()
    no_risk_eq = (no_risk_ret.cumsum() * INITIAL_CAPITAL * 0.25 + INITIAL_CAPITAL).iloc[-1] if len(no_risk_ret) > 0 else INITIAL_CAPITAL
    
    print(f"\n🔍 SO SÁNH:")
    print(f"   Không Risk Mgmt: ${no_risk_eq:,.0f} ({(no_risk_eq/INITIAL_CAPITAL-1)*100:+.1f}%)")
    print(f"   Có Risk Mgmt:    ${capital:,.0f} ({(capital/INITIAL_CAPITAL-1)*100:+.1f}%)")
    
    # Đếm số lần DD Control kích hoạt
    dd_actions = trades_df[trades_df['dd_multiplier'] < 1.0]
    print(f"\n🛡️ DD CONTROL:")
    print(f"   Số lần giảm size: {len(dd_actions)}")
    print(f"   DD Stop hoàn toàn: {(trades_df['exit_reason']=='DD_STOP').sum()}")

# ============================================================
# 6. LƯU
# ============================================================
if len(trades_df) > 0:
    trades_df.to_parquet(os.path.join(RISK_DIR, "risk_managed_trades.parquet"))
    
    risk_summary = {
        'version': 'v1.0',
        'initial_capital': INITIAL_CAPITAL,
        'final_capital': round(capital, 2),
        'total_return_pct': round((capital/INITIAL_CAPITAL - 1)*100, 2),
        'max_drawdown_pct': round(max_dd, 2),
        'total_trades': int(total_trades),
        'win_rate_pct': round(win_rate, 1),
        'avg_return_per_trade_pct': round(avg_ret, 2),
        'profit_factor': round(abs(avg_win/avg_loss), 2) if avg_loss != 0 else 999,
        'stop_loss_hit': int((actual_trades['exit_reason']=='STOP_LOSS').sum()),
        'dd_stops': int((trades_df['exit_reason']=='DD_STOP').sum()),
        'timestamp': datetime.now().isoformat()
    }
    
    with open(os.path.join(RISK_DIR, "risk_summary.json"), 'w') as f:
        json.dump(risk_summary, f, indent=2, default=str)

print(f"\n💾 Đã lưu Risk Management results")
print(f"🎯 Hoàn thành Risk Management!")