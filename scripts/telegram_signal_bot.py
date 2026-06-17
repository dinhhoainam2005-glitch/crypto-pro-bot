"""
TELEGRAM SIGNAL BOT v1.0
- Nhận tín hiệu từ Ensemble Engine
- Gửi qua Telegram: Entry, SL, Exit, Daily Summary
- Hỗ trợ cả Render (env vars) và local (.env)
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import requests
import json

# ============================================================
# LOAD CONFIG: Ưu tiên Render env vars, fallback về file .env
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

if not TOKEN or not CHAT_ID:
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key.strip() == 'TELEGRAM_BOT_TOKEN':
                        TOKEN = value.strip()
                    elif key.strip() == 'TELEGRAM_CHAT_ID':
                        CHAT_ID = value.strip()

if not TOKEN or not CHAT_ID:
    print("❌ Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")
    sys.exit(1)

CHAT_ID = str(CHAT_ID)

LOG_DIR = os.path.join(BASE_DIR, "data", "paper_trading")
os.makedirs(LOG_DIR, exist_ok=True)

# ============================================================
# CONFIG
# ============================================================
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
INITIAL_CAPITAL = 10000
STOP_LOSS_ATR = 2.0
BASE_SIZE = 0.25
MAX_DD_1 = 0.20
MAX_DD_2 = 0.30
MAX_DD_3 = 0.40
HOLD_HOURS = 12

# ============================================================
# STATE
# ============================================================
capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
position = None
signals_log = []
trades_log = []

# ============================================================
# TELEGRAM SENDER
# ============================================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")
        return False

# ============================================================
# DATA FETCHER
# ============================================================
def fetch_klines(symbol, interval='1h', limit=500):
    url = "https://api.binance.com/api/v3/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            df = pd.DataFrame(data, columns=[
                'timestamp','open','high','low','close','volume',
                'close_time','quote_volume','trades','taker_buy_base',
                'taker_buy_quote','ignore'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open','high','low','close','volume']:
                df[col] = df[col].astype(float)
            df.set_index('timestamp', inplace=True)
            return df
    except Exception as e:
        print(f"⚠️ Fetch error: {e}")
    return None

def fetch_funding_rate(symbol):
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {'symbol': symbol, 'limit': 1}
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return float(data[0]['fundingRate']) if data else 0.0001
    except:
        pass
    return 0.0001

# ============================================================
# INDICATORS + SIGNAL GENERATOR
# ============================================================
def compute_indicators(df):
    df = df.copy()
    if 'funding_rate' not in df.columns:
        df['funding_rate'] = 0.0001
    if 'cvd' not in df.columns:
        df['cvd'] = np.cumsum(df['volume'] * (df['close'] - df['open']) / (df['high'] - df['low'] + 0.01))
    
    df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    df['atr_median'] = df['atr_pct'].rolling(500, min_periods=50).median()
    
    for p, col in [(1,'funding_p1'),(5,'funding_p5'),(10,'funding_p10'),(95,'funding_p95')]:
        df[col] = df['funding_rate'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, p), raw=True)
    
    df['cvd_12h'] = df['cvd'].diff(12)
    df['cvd_24h'] = df['cvd'].diff(24)
    df['price_ma50'] = df['close'].rolling(50).mean()
    df['price_chg_24h'] = df['close'].pct_change(24)
    df['vol_ma24'] = df['volume'].rolling(24).mean()
    df['vol_p99'] = df['volume'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 99), raw=True)
    
    return df

def get_signal(df):
    if len(df) < 100:
        return 0, 0, []
    
    latest = df.iloc[-1]
    edges = []
    
    if latest['funding_rate'] < latest['funding_p5'] and latest['funding_rate'] > 0 and latest['cvd_24h'] < 0:
        edges.append('A')
    if latest['funding_rate'] < latest['funding_p10'] and latest['funding_rate'] > 0 and latest['cvd_24h'] < 0:
        edges.append('B')
    if 'A' in edges and latest.get('oi_24h', 0) > 0:
        edges.append('C')
    if latest['funding_rate'] < latest['funding_p5'] and latest['cvd_12h'] < 0 and latest['close'] < latest['price_ma50']:
        edges.append('D')
    if latest['funding_rate'] < latest['funding_p1'] and latest['cvd_24h'] < 0:
        edges.append('E')
    if latest['funding_rate'] > latest['funding_p95'] and latest['price_chg_24h'] > 0.02 and latest['funding_rate'] > 0:
        edges.append('F')
    if latest['cvd_24h'] > 0 and latest['volume'] > latest['vol_ma24']:
        edges.append('G')
    if latest['funding_rate'] < 0 and latest['volume'] > latest['vol_p99']:
        edges.append('H')
    
    votes = len(edges)
    signal = 1 if votes >= 2 else 0
    return signal, votes, edges

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    global capital, peak_capital, position
    
    print("="*60)
    print("📊 TELEGRAM SIGNAL BOT v1.0")
    print("="*60)
    print(f"   Symbol: {SYMBOL} | Timeframe: {TIMEFRAME}")
    print(f"   Capital: ${INITIAL_CAPITAL:,.0f} | Chat: {CHAT_ID}")
    print("="*60)
    
    send_telegram("🚀 <b>Crypto Pro Signal Bot</b> đã khởi động!\n\nSymbol: BTCUSDT | TF: 1h\nRisk: Balanced v3\n\nĐang chờ tín hiệu...")
    
    df = fetch_klines(SYMBOL, TIMEFRAME, limit=500)
    if df is None:
        send_telegram("❌ Không thể kết nối Binance.")
        return
    
    df['funding_rate'] = fetch_funding_rate(SYMBOL)
    print(f"✅ Đã tải {len(df)} nến. Chờ tín hiệu...")
    
    last_signal_time = None
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            new_df = fetch_klines(SYMBOL, TIMEFRAME, limit=500)
            if new_df is not None:
                df = new_df
                df['funding_rate'] = fetch_funding_rate(SYMBOL)
            
            df = compute_indicators(df)
            latest = df.iloc[-1]
            latest_time = df.index[-1]
            
            # Exit check
            if position is not None:
                current_price = latest['close']
                stop_hit = current_price <= position['stop_loss']
                hours_held = (now - position['entry_time']).total_seconds() / 3600
                
                if stop_hit or hours_held >= HOLD_HOURS:
                    exit_price = position['stop_loss'] if stop_hit else current_price
                    trade_return = (exit_price - position['entry_price']) / position['entry_price']
                    trade_pnl = capital * position['size'] * trade_return
                    capital += trade_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    
                    exit_reason = '🛑 STOP LOSS' if stop_hit else '⏰ Hết 12h'
                    emoji = '🔴' if trade_return < 0 else '🟢'
                    
                    msg = f"{emoji} <b>EXIT SIGNAL</b>\n\n"
                    msg += f"Entry: ${position['entry_price']:,.0f}\n"
                    msg += f"Exit: ${exit_price:,.0f}\n"
                    msg += f"Return: {trade_return*100:+.2f}%\n"
                    msg += f"PnL: ${trade_pnl:+,.0f}\n"
                    msg += f"Reason: {exit_reason}\n"
                    msg += f"Capital: ${capital:,.0f} ({(capital/INITIAL_CAPITAL-1)*100:+.2f}%)\n"
                    msg += f"DD: {(peak_capital-capital)/peak_capital*100:.1f}%"
                    
                    send_telegram(msg)
                    print(f"   EXIT: {exit_reason} | PnL: ${trade_pnl:+,.0f}")
                    position = None
            
            # New signal
            if latest_time != last_signal_time:
                last_signal_time = latest_time
                signal, votes, edges = get_signal(df)
                
                if signal == 1 and position is None:
                    atr_pct = latest['atr_pct']
                    atr_median = latest.get('atr_median', atr_pct)
                    entry_price = latest['close']
                    stop_loss = entry_price * (1 - STOP_LOSS_ATR * atr_pct / 100)
                    
                    current_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
                    if current_dd > MAX_DD_3:
                        size = 0
                    elif current_dd > MAX_DD_2:
                        dd_mult = 0.25
                    elif current_dd > MAX_DD_1:
                        dd_mult = 0.5
                    else:
                        dd_mult = 1.0
                    
                    if atr_pct > atr_median * 2.0:
                        vol_mult = 0.75
                    elif atr_pct > atr_median * 1.5:
                        vol_mult = 0.85
                    elif atr_pct < atr_median * 0.5:
                        vol_mult = 1.15
                    else:
                        vol_mult = 1.0
                    
                    size = BASE_SIZE * dd_mult * vol_mult
                    size = max(0.05, min(0.40, size))
                    
                    if size > 0:
                        position = {
                            'entry_price': entry_price,
                            'entry_time': now,
                            'stop_loss': stop_loss,
                            'size': size
                        }
                        
                        sl_pct = (1 - stop_loss/entry_price) * 100
                        
                        msg = f"🟢 <b>LONG SIGNAL</b>\n\n"
                        msg += f"💰 Entry: <b>${entry_price:,.0f}</b>\n"
                        msg += f"🛑 Stop Loss: ${stop_loss:,.0f} ({sl_pct:.1f}%)\n"
                        msg += f"📏 Size: {size*100:.1f}% (~${capital*size:,.0f})\n"
                        msg += f"⏰ Hold: {HOLD_HOURS}h\n\n"
                        msg += f"📊 Indicators:\n"
                        msg += f"   Votes: {votes}/8\n"
                        msg += f"   Edges: {','.join(edges)}\n"
                        msg += f"   ATR: {atr_pct:.2f}%\n"
                        msg += f"   Funding: {latest['funding_rate']*100:.4f}%\n"
                        msg += f"   DD: {current_dd*100:.1f}%"
                        
                        send_telegram(msg)
                        print(f"   🟢 SIGNAL SENT: ${entry_price:,.0f}")
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            send_telegram("🛑 Bot đã dừng.")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()