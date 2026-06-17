"""
MULTI-COIN TELEGRAM SIGNAL BOT v2.0
- Tín hiệu 10 coin từ Ensemble Multi-Coin v2
- Gửi LONG/SHORT qua Telegram
- Risk Management đa coin
- Deploy-ready cho Render
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
# LOAD CONFIG
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
    print("❌ Thiếu config")
    sys.exit(1)

CHAT_ID = str(CHAT_ID)

# ============================================================
# CONFIG
# ============================================================
COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

TIMEFRAME = '1h'
HOLD_HOURS = 12
STOP_LOSS_ATR = 2.0

# Risk Management đa coin
INITIAL_CAPITAL = 10000
MAX_POSITIONS = 3          # Tối đa 3 vị thế cùng lúc
MAX_SIZE_PER_COIN = 0.15   # Tối đa 15% vốn/coin
MAX_TOTAL_SIZE = 0.40      # Tối đa 40% vốn tổng
MAX_DD_1 = 0.20
MAX_DD_2 = 0.30
MAX_DD_3 = 0.40

# ============================================================
# STATE
# ============================================================
capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
positions = {}  # {coin: {entry_price, entry_time, stop_loss, size, direction}}
signals_log = []
trades_log = []
last_signal_times = {}

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ============================================================
# DATA FETCHER
# ============================================================
def fetch_klines(symbol, interval='1h', limit=500):
    url = "https://fapi.binance.com/fapi/v1/klines"
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
    except:
        pass
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

def fetch_oi_bybit(symbol):
    url = "https://api.bybit.com/v5/market/open-interest"
    params = {'category': 'linear', 'symbol': symbol, 'intervalTime': '1h', 'limit': 1}
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('retCode') == 0:
                oi_list = data['result'].get('list', [])
                if oi_list:
                    return float(oi_list[0]['openInterest'])
    except:
        pass
    return 50000

# ============================================================
# INDICATORS + SIGNALS
# ============================================================
def compute_indicators(df, funding_rate, oi_value):
    df = df.copy()
    df['funding_rate'] = funding_rate
    df['oi'] = oi_value
    
    df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 1), raw=True)
    df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 5), raw=True)
    df['funding_p95'] = df['funding_rate'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 95), raw=True)
    df['funding_p99'] = df['funding_rate'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 99), raw=True)
    df['funding_rising'] = (df['funding_rate'].diff(8) > 0).astype(int)
    
    df['cvd'] = np.cumsum(df['volume'] * (df['close'] - df['open']) / (df['high'] - df['low'] + 0.01))
    df['cvd_24h'] = df['cvd'].diff(24)
    df['cvd_up'] = (df['cvd_24h'] > 0).astype(int)
    df['cvd_down'] = (df['cvd_24h'] < 0).astype(int)
    
    df['oi_chg'] = df['oi'].pct_change(24)
    df['oi_up'] = (df['oi_chg'] > 0.01).astype(int)
    df['oi_down'] = (df['oi_chg'] < -0.01).astype(int)
    
    df['vol_p95'] = df['volume'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 95), raw=True)
    df['vol_p99'] = df['volume'].rolling(500, min_periods=50).apply(lambda x: np.percentile(x, 99), raw=True)
    df['vol_high'] = (df['volume'] > df['vol_p95']).astype(int)
    
    df['price_chg'] = df['close'].pct_change(24)
    df['price_up'] = (df['price_chg'] > 0.02).astype(int)
    df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    
    df['ma_50'] = df['close'].rolling(50).mean()
    df['trend_up'] = (df['close'] > df['ma_50']).astype(int)
    df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    
    df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    
    return df

# Edge conditions (rút gọn từ top edges đa coin)
EDGES = {
    'BTCUSDT': [
        ('FUND_P99+PRICE_DOWN+TREND_DOWN', 'LONG'),
        ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'),
        ('FUND_P99+PRICE_DOWN', 'LONG'),
    ],
    'ETHUSDT': [
        ('FUND_P5+VOL_HIGH+PRICE_UP', 'LONG'),
        ('FUND_P99+PRICE_DOWN', 'LONG'),
        ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'),
    ],
    'SOLUSDT': [
        ('FUND_P5+VOL_HIGH+PRICE_DOWN', 'LONG'),
        ('CVD_DOWN+PRICE_UP+TREND_DOWN', 'SHORT'),
        ('FUND_P99+PRICE_UP', 'SHORT'),
    ],
    'BNBUSDT': [
        ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'),
        ('FUND_P99+OI_UP+VOL_HIGH', 'SHORT'),
    ],
    'XRPUSDT': [
        ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'),
        ('FUND_P99+PRICE_DOWN', 'LONG'),
        ('FUND_P5+FUND_RISING+TREND_DOWN', 'LONG'),
    ],
    'ARBUSDT': [
        ('FUND_P5+FUND_POS+FUND_RISING', 'SHORT'),
        ('FUND_P5+OI_DOWN+PRICE_DOWN', 'LONG'),
    ],
    'OPUSDT': [
        ('FUND_P5+FUND_RISING+TREND_UP', 'SHORT'),
        ('FUND_P99+OI_UP+VOL_HIGH', 'SHORT'),
    ],
    'LINKUSDT': [
        ('FUND_P1+OI_DOWN+VOL_HIGH', 'LONG'),
        ('FUND_P99+PRICE_DOWN', 'SHORT'),
    ],
    'AVAXUSDT': [
        ('FUND_P1+FUND_POS+CVD_UP', 'SHORT'),
        ('FUND_P1+FUND_POS+TREND_UP', 'SHORT'),
    ],
    'DOGEUSDT': [
        ('FUND_P5+FUND_POS+FUND_RISING', 'SHORT'),
        ('FUND_P5+VOL_HIGH+PRICE_DOWN', 'LONG'),
    ],
}

COND_MAP = {
    'FUND_P1': lambda d: d['funding_rate'] < d['funding_p1'],
    'FUND_P5': lambda d: d['funding_rate'] < d['funding_p5'],
    'FUND_P95': lambda d: d['funding_rate'] > d['funding_p95'],
    'FUND_P99': lambda d: d['funding_rate'] > d['funding_p99'],
    'FUND_POS': lambda d: d['funding_rate'] > 0,
    'FUND_RISING': lambda d: d['funding_rising'] == 1,
    'CVD_UP': lambda d: d['cvd_up'] == 1,
    'CVD_DOWN': lambda d: d['cvd_down'] == 1,
    'OI_UP': lambda d: d['oi_up'] == 1,
    'OI_DOWN': lambda d: d['oi_down'] == 1,
    'VOL_HIGH': lambda d: d['vol_high'] == 1,
    'VOL_SPIKE': lambda d: d['volume'] > d['vol_p99'],
    'PRICE_UP': lambda d: d['price_up'] == 1,
    'PRICE_DOWN': lambda d: d['price_down'] == 1,
    'TREND_UP': lambda d: d['trend_up'] == 1,
    'TREND_DOWN': lambda d: d['trend_down'] == 1,
}

def get_signal(df, coin):
    if coin not in EDGES:
        return 0, 0
    
    latest = df.iloc[-1]
    long_votes = 0
    short_votes = 0
    
    for cond_str, direction in EDGES[coin]:
        conds = cond_str.split('+')
        match = True
        for c in conds:
            if c in COND_MAP:
                if not COND_MAP[c](latest):
                    match = False
                    break
        
        if match:
            if direction == 'LONG':
                long_votes += 1
            else:
                short_votes += 1
    
    if long_votes > short_votes and long_votes >= 1:
        return 1, long_votes
    elif short_votes > long_votes and short_votes >= 1:
        return -1, short_votes
    return 0, 0

# ============================================================
# RISK MANAGEMENT
# ============================================================
def can_open_position(coin, direction):
    global capital, peak_capital, positions
    
    # DD check
    current_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
    if current_dd > MAX_DD_3:
        return False, 0
    
    # Số vị thế tối đa
    if len(positions) >= MAX_POSITIONS:
        return False, 0
    
    # Đã có vị thế coin này chưa
    if coin in positions:
        return False, 0
    
    # Tổng size hiện tại
    total_size = sum(p['size'] for p in positions.values())
    if total_size >= MAX_TOTAL_SIZE:
        return False, 0
    
    # Size cho coin này
    if current_dd > MAX_DD_2:
        dd_mult = 0.25
    elif current_dd > MAX_DD_1:
        dd_mult = 0.5
    else:
        dd_mult = 1.0
    
    size = min(MAX_SIZE_PER_COIN, MAX_TOTAL_SIZE - total_size) * dd_mult
    size = max(0.05, size)
    
    return True, size

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    global capital, peak_capital, positions
    
    print("="*60)
    print("🚀 MULTI-COIN TELEGRAM SIGNAL BOT v2.0")
    print("="*60)
    print(f"   Coins: {len(COINS)} | Max positions: {MAX_POSITIONS}")
    print(f"   Capital: ${INITIAL_CAPITAL:,.0f}")
    print("="*60)
    
    send_telegram("🚀 <b>Multi-Coin Signal Bot v2.0</b> đã khởi động!\n\n"
                  f"Coins: {len(COINS)} (BTC, ETH, SOL, BNB, XRP, ARB, OP, LINK, AVAX, DOGE)\n"
                  f"Max positions: {MAX_POSITIONS}\n"
                  f"Signal: LONG + SHORT\n\n"
                  "Đang chờ tín hiệu...")
    
    print("✅ Đang chờ tín hiệu...")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # Check exits
            coins_to_remove = []
            for coin, pos in positions.items():
                # Fetch current price
                df = fetch_klines(coin, TIMEFRAME, limit=2)
                if df is None:
                    continue
                
                current_price = df.iloc[-1]['close']
                hours_held = (now - pos['entry_time']).total_seconds() / 3600
                
                # Stop loss (theo hướng)
                if pos['direction'] == 'LONG':
                    stop_hit = current_price <= pos['stop_loss']
                else:
                    stop_hit = current_price >= pos['stop_loss']
                
                if stop_hit or hours_held >= HOLD_HOURS:
                    exit_price = pos['stop_loss'] if stop_hit else current_price
                    
                    if pos['direction'] == 'LONG':
                        trade_return = (exit_price - pos['entry_price']) / pos['entry_price']
                    else:
                        trade_return = (pos['entry_price'] - exit_price) / pos['entry_price']
                    
                    trade_pnl = capital * pos['size'] * trade_return
                    capital += trade_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    
                    exit_reason = '🛑 SL' if stop_hit else '⏰ 12h'
                    emoji = '🔴' if trade_return < 0 else '🟢'
                    
                    msg = f"{emoji} <b>EXIT {coin}</b> ({pos['direction']})\n\n"
                    msg += f"Entry: ${pos['entry_price']:,.4f}\n"
                    msg += f"Exit: ${exit_price:,.4f}\n"
                    msg += f"Return: {trade_return*100:+.2f}%\n"
                    msg += f"PnL: ${trade_pnl:+,.2f}\n"
                    msg += f"Reason: {exit_reason}\n"
                    msg += f"Capital: ${capital:,.0f} ({((capital/INITIAL_CAPITAL)-1)*100:+.2f}%)\n"
                    msg += f"Positions: {len(positions)-1}/{MAX_POSITIONS}"
                    
                    send_telegram(msg)
                    print(f"   EXIT {coin}: {exit_reason} | PnL: ${trade_pnl:+,.2f}")
                    coins_to_remove.append(coin)
            
            for coin in coins_to_remove:
                del positions[coin]
            
            # Check new signals
            for coin in COINS:
                if coin in positions:
                    continue
                
                if coin in last_signal_times:
                    last_time = last_signal_times[coin]
                    if (now - last_time).total_seconds() < 3600:  # Đã check trong 1h qua
                        continue
                
                df = fetch_klines(coin, TIMEFRAME, limit=500)
                if df is None:
                    continue
                
                funding = fetch_funding_rate(coin)
                oi = fetch_oi_bybit(coin)
                df = compute_indicators(df, funding, oi)
                
                signal, votes = get_signal(df, coin)
                last_signal_times[coin] = now
                
                if signal != 0:
                    can_open, size = can_open_position(coin, signal)
                    
                    if can_open:
                        latest = df.iloc[-1]
                        entry_price = latest['close']
                        atr_pct = latest['atr_pct']
                        
                        if signal == 1:  # LONG
                            stop_loss = entry_price * (1 - STOP_LOSS_ATR * atr_pct / 100)
                        else:  # SHORT
                            stop_loss = entry_price * (1 + STOP_LOSS_ATR * atr_pct / 100)
                        
                        positions[coin] = {
                            'entry_price': entry_price,
                            'entry_time': now,
                            'stop_loss': stop_loss,
                            'size': size,
                            'direction': 'LONG' if signal == 1 else 'SHORT'
                        }
                        
                        dir_str = 'LONG 🟢' if signal == 1 else 'SHORT 🔴'
                        sl_pct = abs(1 - stop_loss/entry_price) * 100
                        
                        msg = f"{dir_str} <b>{coin}</b>\n\n"
                        msg += f"💰 Entry: <b>${entry_price:,.4f}</b>\n"
                        msg += f"🛑 SL: ${stop_loss:,.4f} ({sl_pct:.1f}%)\n"
                        msg += f"📏 Size: {size*100:.1f}% (~${capital*size:,.0f})\n"
                        msg += f"⏰ Hold: {HOLD_HOURS}h\n"
                        msg += f"🗳️ Votes: {votes}\n"
                        msg += f"📊 ATR: {atr_pct:.2f}%\n"
                        msg += f"💼 Positions: {len(positions)}/{MAX_POSITIONS}"
                        
                        send_telegram(msg)
                        print(f"   {dir_str} {coin}: ${entry_price:,.4f} | Size: {size*100:.1f}%")
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            send_telegram("🛑 Bot đã dừng.")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()