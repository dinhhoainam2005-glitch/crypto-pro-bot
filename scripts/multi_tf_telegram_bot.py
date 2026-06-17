"""
MULTI-TF TELEGRAM SIGNAL BOT v3.1 - FINAL
- 15m: 3 edge đã test OOS dương, max 1 tín hiệu/4h
- 1h, 4h, 1d: giữ nguyên toàn bộ
- Không cắt bỏ gì khác
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
# CONFIG
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
# TOÀN BỘ CONFIG
# ============================================================
COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

TIMEFRAMES = {
    '15m': {'interval': '15min', 'hold_hours': 4, 'horizon': 16, 'max_per_4h': 1},
    '1h':  {'interval': '1h', 'hold_hours': 12, 'horizon': 12, 'max_per_4h': 99},
    '4h':  {'interval': '4h', 'hold_hours': 24, 'horizon': 6, 'max_per_4h': 99},
    '1d':  {'interval': '1d', 'hold_hours': 72, 'horizon': 3, 'max_per_4h': 99},
}

INITIAL_CAPITAL = 10000
MAX_POSITIONS = 5
MAX_SIZE_PER_COIN = 0.12
MAX_TOTAL_SIZE = 0.50
STOP_LOSS_ATR = 2.0
MAX_DD_1 = 0.20
MAX_DD_2 = 0.30
MAX_DD_3 = 0.40

# ============================================================
# STATE
# ============================================================
capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
positions = {}
last_checks = {}
last_15m_signal_time = None
trades_log = []

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
# DATA
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
# INDICATORS
# ============================================================
def compute_indicators(df, funding_rate, oi_value, tf_config):
    df = df.copy()
    n_per_day = {'15min': 96, '1h': 24, '4h': 6, '1d': 1}[tf_config['interval']]
    
    df['funding_rate'] = funding_rate
    df['oi'] = oi_value
    
    fw = max(50, 20 * n_per_day)
    vw = max(50, 20 * n_per_day)
    mw = max(20, 14 * n_per_day)
    cvd_lb = max(1, n_per_day)
    
    df['funding_p5'] = df['funding_rate'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 5), raw=True)
    df['funding_p95'] = df['funding_rate'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 95), raw=True)
    df['funding_p99'] = df['funding_rate'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 99), raw=True)
    df['funding_chg'] = df['funding_rate'].diff(max(1, n_per_day // 3))
    df['funding_rising'] = (df['funding_chg'] > 0).astype(int)
    df['funding_pos'] = (df['funding_rate'] > 0).astype(int)
    df['funding_neg'] = (df['funding_rate'] < 0).astype(int)
    
    df['cvd'] = np.cumsum(df['volume'] * (df['close'] - df['open']) / (df['high'] - df['low'] + 0.01))
    df['cvd_chg'] = df['cvd'].diff(cvd_lb)
    df['cvd_up'] = (df['cvd_chg'] > 0).astype(int)
    df['cvd_down'] = (df['cvd_chg'] < 0).astype(int)
    
    df['oi_chg'] = df['oi'].pct_change(cvd_lb)
    df['oi_up'] = (df['oi_chg'] > 0.01).astype(int)
    df['oi_down'] = (df['oi_chg'] < -0.01).astype(int)
    
    df['vol_p95'] = df['volume'].rolling(vw, min_periods=20).apply(lambda x: np.percentile(x, 95), raw=True)
    df['vol_p99'] = df['volume'].rolling(vw, min_periods=20).apply(lambda x: np.percentile(x, 99), raw=True)
    df['vol_high'] = (df['volume'] > df['vol_p95']).astype(int)
    
    df['price_chg'] = df['close'].pct_change(cvd_lb)
    df['price_up'] = (df['price_chg'] > 0.02).astype(int)
    df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    
    df['ma_50'] = df['close'].rolling(mw).mean()
    df['trend_up'] = (df['close'] > df['ma_50']).astype(int)
    df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    
    df['atr_14'] = (df['high'] - df['low']).rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    
    return df

# ============================================================
# TOÀN BỘ EDGES (FINAL)
# ============================================================
ALL_EDGES = {
    '15m': {
        'XRPUSDT': [('CVD_UP+OI_UP', 'LONG')],
        'BTCUSDT': [('CVD_DOWN+OI_DOWN', 'LONG')],
        'BNBUSDT': [('CVD_DOWN+OI_UP', 'SHORT')],
    },
    '1h': {
        'BTCUSDT': [('FUND_P99+PRICE_DOWN+TREND_DOWN', 'LONG'), ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'), ('FUND_P99+PRICE_DOWN', 'LONG')],
        'ETHUSDT': [('FUND_P5+VOL_HIGH+PRICE_UP', 'LONG'), ('FUND_P99+PRICE_DOWN', 'LONG'), ('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG')],
        'SOLUSDT': [('FUND_P5+VOL_HIGH+PRICE_DOWN', 'LONG'), ('CVD_DOWN+PRICE_UP+TREND_DOWN', 'SHORT'), ('FUND_P99+PRICE_UP', 'SHORT')],
        'BNBUSDT': [('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'), ('FUND_P99+OI_UP+VOL_HIGH', 'SHORT')],
        'XRPUSDT': [('FUND_P5+FUND_RISING+PRICE_DOWN', 'LONG'), ('FUND_P99+PRICE_DOWN', 'LONG'), ('FUND_P5+FUND_RISING+TREND_DOWN', 'LONG')],
        'ARBUSDT': [('FUND_P5+FUND_POS+FUND_RISING', 'SHORT'), ('FUND_P5+OI_DOWN+PRICE_DOWN', 'LONG')],
        'OPUSDT': [('FUND_P5+FUND_RISING+TREND_UP', 'SHORT'), ('FUND_P99+OI_UP+VOL_HIGH', 'SHORT')],
        'LINKUSDT': [('FUND_P1+OI_DOWN+VOL_HIGH', 'LONG'), ('FUND_P99+PRICE_DOWN', 'SHORT')],
        'AVAXUSDT': [('FUND_P1+FUND_POS+CVD_UP', 'SHORT'), ('FUND_P1+FUND_POS+TREND_UP', 'SHORT')],
        'DOGEUSDT': [('FUND_P5+FUND_POS+FUND_RISING', 'SHORT'), ('FUND_P5+VOL_HIGH+PRICE_DOWN', 'LONG')],
    },
    '4h': {
        'ARBUSDT': [('FUND_P5+FUND_POS', 'SHORT'), ('FUND_P5+VOL_HIGH', 'LONG')],
        'BNBUSDT': [('FUND_P99+TREND_DOWN', 'SHORT')],
        'BTCUSDT': [('FUND_P5+PRICE_DOWN', 'LONG')],
        'ETHUSDT': [('FUND_P95+TREND_DOWN', 'SHORT')],
        'XRPUSDT': [('FUND_P5+FUND_POS', 'SHORT'), ('FUND_P95+VOL_HIGH', 'LONG')],
        'OPUSDT': [('FUND_P5+FUND_RISING', 'SHORT')],
        'LINKUSDT': [('FUND_P5+OI_DOWN', 'SHORT'), ('FUND_NEG+FUND_RISING', 'LONG')],
        'AVAXUSDT': [('FUND_P1+FUND_POS', 'SHORT')],
        'SOLUSDT': [('FUND_P5+FUND_RISING', 'SHORT'), ('FUND_P99+PRICE_DOWN', 'LONG')],
        'DOGEUSDT': [('FUND_P5+PRICE_DOWN', 'LONG'), ('FUND_P95+TREND_UP', 'SHORT')],
    },
    '1d': {
        'BTCUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG')],
        'LINKUSDT': [('FUND_P5+OI_DOWN', 'SHORT'), ('FUND_NEG+FUND_RISING', 'LONG')],
        'SOLUSDT': [('FUND_P5+PRICE_DOWN', 'SHORT')],
        'ETHUSDT': [('FUND_P5+PRICE_DOWN', 'LONG'), ('FUND_P95+TREND_DOWN', 'SHORT')],
        'BNBUSDT': [('FUND_P5+OI_UP', 'SHORT'), ('FUND_NEG+PRICE_DOWN', 'LONG')],
        'XRPUSDT': [('FUND_P5+FUND_POS', 'SHORT'), ('FUND_NEG+VOL_HIGH', 'LONG')],
        'ARBUSDT': [('FUND_P5+FUND_RISING', 'SHORT'), ('FUND_NEG+PRICE_DOWN', 'LONG')],
        'OPUSDT': [('FUND_P5+OI_UP', 'SHORT')],
        'AVAXUSDT': [('FUND_P5+PRICE_DOWN', 'SHORT'), ('FUND_NEG+FUND_RISING', 'LONG')],
        'DOGEUSDT': [('FUND_P5+FUND_POS', 'SHORT'), ('FUND_NEG+PRICE_DOWN', 'LONG')],
    },
}

def eval_cond(name, d):
    mapping = {
        'FUND_P1': d['funding_rate'] < d.get('funding_p1', -99),
        'FUND_P5': d['funding_rate'] < d['funding_p5'],
        'FUND_P95': d['funding_rate'] > d['funding_p95'],
        'FUND_P99': d['funding_rate'] > d['funding_p99'],
        'FUND_POS': d['funding_rate'] > 0,
        'FUND_NEG': d['funding_rate'] < 0,
        'FUND_RISING': d['funding_rising'] == 1,
        'CVD_UP': d['cvd_up'] == 1,
        'CVD_DOWN': d['cvd_down'] == 1,
        'OI_UP': d['oi_up'] == 1,
        'OI_DOWN': d['oi_down'] == 1,
        'VOL_HIGH': d['vol_high'] == 1,
        'VOL_SPIKE': d['vol_spike'] if 'vol_spike' in d else False,
        'PRICE_UP': d['price_up'] == 1,
        'PRICE_DOWN': d['price_down'] == 1,
        'TREND_UP': d['trend_up'] == 1,
        'TREND_DOWN': d['trend_down'] == 1,
    }
    return mapping.get(name, False)

def get_signal(df, coin, tf):
    if tf not in ALL_EDGES or coin not in ALL_EDGES[tf]:
        return 0, 0
    
    latest = df.iloc[-1]
    long_votes = 0
    short_votes = 0
    
    for cond_str, direction in ALL_EDGES[tf][coin]:
        conds = cond_str.split('+')
        match = all(eval_cond(c, latest) for c in conds)
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
def can_open_position(coin, tf):
    global capital, peak_capital, positions
    
    key = f"{coin}_{tf}"
    current_dd = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
    if current_dd > MAX_DD_3:
        return False, 0
    
    if len(positions) >= MAX_POSITIONS:
        return False, 0
    
    if key in positions:
        return False, 0
    
    total_size = sum(p['size'] for p in positions.values())
    if total_size >= MAX_TOTAL_SIZE:
        return False, 0
    
    if current_dd > MAX_DD_2:
        dd_mult = 0.25
    elif current_dd > MAX_DD_1:
        dd_mult = 0.5
    else:
        dd_mult = 1.0
    
    size = min(MAX_SIZE_PER_COIN, MAX_TOTAL_SIZE - total_size) * dd_mult
    size = max(0.03, size)
    
    return True, size

# ============================================================
# MAIN
# ============================================================
def main():
    global capital, peak_capital, positions, last_15m_signal_time
    
    print("="*60)
    print("🚀 MULTI-TF BOT v3.1 - FINAL")
    print("="*60)
    print(f"   10 coins × 4 TFs | 15m: 3 edge (max 1/4h)")
    print(f"   Max {MAX_POSITIONS} positions | SL 2 ATR")
    print("="*60)
    
    send_telegram("🚀 <b>Multi-TF Bot v3.1 - FINAL</b>\n\n"
                  "⏱️ 4 TFs: 15m(3) · 1h · 4h · 1d\n"
                  "🪙 10 Coins\n📊 LONG + SHORT\n"
                  "🛡️ SL 2 ATR · Max 5 pos\n\n"
                  "Đang chờ tín hiệu...")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # === EXIT CHECK ===
            to_remove = []
            for key, pos in positions.items():
                coin = pos['coin']
                tf = pos['tf']
                tf_config = TIMEFRAMES[tf]
                
                df = fetch_klines(coin, tf_config['interval'], limit=2)
                if df is None:
                    continue
                
                current_price = df.iloc[-1]['close']
                hours_held = (now - pos['entry_time']).total_seconds() / 3600
                
                if pos['direction'] == 'LONG':
                    stop_hit = current_price <= pos['stop_loss']
                else:
                    stop_hit = current_price >= pos['stop_loss']
                
                if stop_hit or hours_held >= tf_config['hold_hours']:
                    exit_price = pos['stop_loss'] if stop_hit else current_price
                    
                    if pos['direction'] == 'LONG':
                        trade_return = (exit_price - pos['entry_price']) / pos['entry_price']
                    else:
                        trade_return = (pos['entry_price'] - exit_price) / pos['entry_price']
                    
                    trade_pnl = capital * pos['size'] * trade_return
                    capital += trade_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    
                    reason = '🛑 SL' if stop_hit else f'⏰ {tf_config["hold_hours"]}h'
                    emoji = '🟢' if trade_return > 0 else '🔴'
                    
                    msg = f"{emoji} <b>EXIT [{tf}] {coin}</b> ({pos['direction']})\n"
                    msg += f"Entry: ${pos['entry_price']:,.4f} → Exit: ${exit_price:,.4f}\n"
                    msg += f"Return: {trade_return*100:+.2f}% | PnL: ${trade_pnl:+,.2f}\n"
                    msg += f"Reason: {reason}\n"
                    msg += f"Capital: ${capital:,.0f} ({((capital/INITIAL_CAPITAL)-1)*100:+.2f}%)\n"
                    msg += f"Positions: {len(positions)-1}/{MAX_POSITIONS}"
                    
                    send_telegram(msg)
                    to_remove.append(key)
            
            for key in to_remove:
                del positions[key]
            
            # === SIGNAL CHECK ===
            for coin in COINS:
                for tf_name, tf_config in TIMEFRAMES.items():
                    key = f"{coin}_{tf_name}"
                    
                    if key in positions:
                        continue
                    
                    # 15m rate limit
                    if tf_name == '15m':
                        if last_15m_signal_time and (now - last_15m_signal_time).total_seconds() < 14400:
                            continue
                    
                    last_key = f"{coin}_{tf_name}_check"
                    if last_key in last_checks:
                        if (now - last_checks[last_key]).total_seconds() < 300:
                            continue
                    
                    df = fetch_klines(coin, tf_config['interval'], limit=500)
                    if df is None:
                        continue
                    
                    funding = fetch_funding_rate(coin)
                    oi = fetch_oi_bybit(coin)
                    df = compute_indicators(df, funding, oi, tf_config)
                    
                    signal, votes = get_signal(df, coin, tf_name)
                    last_checks[last_key] = now
                    
                    if signal != 0:
                        can_open, size = can_open_position(coin, tf_name)
                        
                        if can_open:
                            latest = df.iloc[-1]
                            entry_price = latest['close']
                            atr_pct = latest['atr_pct']
                            
                            if signal == 1:
                                stop_loss = entry_price * (1 - STOP_LOSS_ATR * atr_pct / 100)
                                dir_str = 'LONG 🟢'
                            else:
                                stop_loss = entry_price * (1 + STOP_LOSS_ATR * atr_pct / 100)
                                dir_str = 'SHORT 🔴'
                            
                            positions[key] = {
                                'coin': coin, 'tf': tf_name,
                                'entry_price': entry_price, 'entry_time': now,
                                'stop_loss': stop_loss, 'size': size,
                                'direction': 'LONG' if signal == 1 else 'SHORT'
                            }
                            
                            if tf_name == '15m':
                                last_15m_signal_time = now
                            
                            sl_pct = abs(1 - stop_loss/entry_price) * 100
                            
                            msg = f"{dir_str} <b>[{tf_name}] {coin}</b>\n\n"
                            msg += f"💰 Entry: <b>${entry_price:,.4f}</b>\n"
                            msg += f"🛑 SL: ${stop_loss:,.4f} ({sl_pct:.1f}%)\n"
                            msg += f"📏 Size: {size*100:.1f}% (~${capital*size:,.0f})\n"
                            msg += f"⏰ Hold: {tf_config['hold_hours']}h\n"
                            msg += f"🗳️ Votes: {votes}\n"
                            msg += f"💼 Positions: {len(positions)}/{MAX_POSITIONS}"
                            
                            send_telegram(msg)
                            print(f"   {dir_str} [{tf_name}] {coin}: ${entry_price:,.4f}")
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            send_telegram("🛑 Bot đã dừng.")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()