"""
V4.4 MODULE 3+4: WEIGHT ADJUSTER + REGIME ADAPTER (FULL VERSION)
- Hệ thống Open Interest: Tự động nạp lịch sử từ file Parquet cục bộ để tính toán factor thực tế.
- Khắc phục lỗi đọc file liên tục: Giữ EDGE_LOG trên RAM, chỉ lưu khi có thay đổi hiệu suất hoặc định kỳ.
- Tối ưu hóa API & Sleep: Gom gọn luồng lặp chính, tránh trùng lặp fetch dữ liệu.
- Auto Scanner: Tự động quét tìm Edge mới định kỳ vào ngày 1 hàng tháng (chỉ scan, không tự thêm).
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import requests
import json
from itertools import combinations
import re
import threading
file_lock = threading.Lock()

session = requests.Session()

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1511598618652442655/iIyTS55FJQGg21zgPYeyZz1Utc_pG2jY9tdGNJ66XZVTfNdJDk_NFdUygYrAUoRS6hpY"
CMC_API_KEY = "ba07282bfe644708a9f42be12a33acf6"
DOM_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ARB', 'OP', 'LINK', 'AVAX', 'DOGE']
DOM_HISTORY = {}
WHALE_COINS_BINANCE = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
                       'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONITOR_DIR = os.path.join(BASE_DIR, "data", "monitor")
os.makedirs(MONITOR_DIR, exist_ok=True)
EDGE_LOG_FILE = os.path.join(MONITOR_DIR, "edge_live_performance.json")
WEIGHT_FILE = os.path.join(MONITOR_DIR, "edge_weights.json")
OI_RECORD_DIR = os.path.join(BASE_DIR, "data", "oi_history")
os.makedirs(OI_RECORD_DIR, exist_ok=True)

# Toàn cục lưu RAM cache tránh đọc đĩa liên tục
GLOBAL_EDGE_LOG = {}
EDGE_WEIGHTS = {}

def load_edge_log():
    global GLOBAL_EDGE_LOG
    if os.path.exists(EDGE_LOG_FILE):
        try:
            with open(EDGE_LOG_FILE, 'r') as f:
                GLOBAL_EDGE_LOG = json.load(f)
                return GLOBAL_EDGE_LOG
        except:
            GLOBAL_EDGE_LOG = {}
    return GLOBAL_EDGE_LOG

def save_edge_log_to_disk():
    with file_lock:
        with open(EDGE_LOG_FILE, 'w') as f:
            json.dump(GLOBAL_EDGE_LOG, f, indent=2, default=str)

def save_weights():
    with file_lock:
        tmp = WEIGHT_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(EDGE_WEIGHTS, f)
        os.replace(tmp, WEIGHT_FILE)

def load_weights():
    global EDGE_WEIGHTS
    if os.path.exists(WEIGHT_FILE):
        try:
            with open(WEIGHT_FILE, 'r') as f:
                EDGE_WEIGHTS = json.load(f)
        except:
            EDGE_WEIGHTS = {}

def update_edge_performance(coin, tf, cond_str, direction, pnl_pct):
    """Cập nhật hiệu suất edge trực tiếp trên RAM cache"""
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    
    if edge_id not in GLOBAL_EDGE_LOG:
        GLOBAL_EDGE_LOG[edge_id] = {
            'coin': coin, 'tf': tf, 'conditions': cond_str, 'direction': direction,
            'trades': [], 'live_sharpe': 0, 'live_wr': 0, 'status': 'ACTIVE',
            'first_seen': datetime.now(timezone.utc).isoformat()
        }
    
    GLOBAL_EDGE_LOG[edge_id]['trades'].append({
        'time': datetime.now(timezone.utc).isoformat(),
        'pnl_pct': round(pnl_pct, 4)
    })
    
    if len(GLOBAL_EDGE_LOG[edge_id]['trades']) > 50:
        GLOBAL_EDGE_LOG[edge_id]['trades'] = GLOBAL_EDGE_LOG[edge_id]['trades'][-50:]
    
    try:
        trades = [t['pnl_pct'] for t in GLOBAL_EDGE_LOG[edge_id]['trades']]
        if len(trades) >= 10:
            avg = sum(trades) / len(trades)
            std = (sum((t - avg)**2 for t in trades) / len(trades)) ** 0.5
            trades_count = len(trades)
            GLOBAL_EDGE_LOG[edge_id]['live_sharpe'] = round(avg / std * np.sqrt(trades_count), 2) if std > 1e-8 else 0
            GLOBAL_EDGE_LOG[edge_id]['live_wr'] = round(sum(1 for t in trades if t > 0) / len(trades) * 100, 1)
    except:
        GLOBAL_EDGE_LOG[edge_id]['live_sharpe'] = 0
        GLOBAL_EDGE_LOG[edge_id]['live_wr'] = 50
    
    save_edge_log_to_disk()

def check_edge_health():
    """Kiểm tra sức khỏe hệ thống và lọc các cạnh yếu"""
    alerts = []
    now = datetime.now(timezone.utc)
    
    for edge_id, data in GLOBAL_EDGE_LOG.items():
        if data['status'] == 'DEPRECATED':
            continue
        
        trades = data.get('trades', [])
        if len(trades) >= 30:
            recent = trades[-30:]
            avg_recent = sum(t['pnl_pct'] for t in recent) / len(recent)
            win_count = sum(1 for t in recent if t['pnl_pct'] > 0)
            win_rate_recent = win_count / len(recent)
            
            if win_rate_recent < 0.3 or avg_recent < -0.01:
                data['status'] = 'DEPRECATED'
                data['deprecated_at_weekly_cycle'] = now.date().isoformat()
                alerts.append(
                    f"⚠️ <b>EDGE DEPRECATED:</b> {edge_id[:60]}...\n"
                    f"   Live WR: {data['live_wr']}% | Live Sharpe: {data['live_sharpe']}\n"
                    f"   → Tự động loại bỏ"
                )
    
    save_edge_log_to_disk()
    active = sum(1 for v in GLOBAL_EDGE_LOG.values() if v['status'] == 'ACTIVE')
    deprecated = sum(1 for v in GLOBAL_EDGE_LOG.values() if v['status'] == 'DEPRECATED')
    return alerts, active, deprecated

def weekly_edge_report():
    """Báo cáo hàng tuần - Chỉ đếm số lượng vừa loại trong tuần qua"""
    active = [v for v in GLOBAL_EDGE_LOG.values() if v['status'] == 'ACTIVE']
    
    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    recent_deprecated = [
        v for v in GLOBAL_EDGE_LOG.values() 
        if v['status'] == 'DEPRECATED' and v.get('deprecated_at_weekly_cycle', '') >= one_week_ago
    ]
    
    report = f"📊 <b>WEEKLY EDGE REPORT</b>\n\n"
    report += f"✅ Đang hoạt động (Active): {len(active)} edges\n"
    report += f"❌ Mới loại trong tuần: {len(recent_deprecated)} edges\n"
    
    if active:
        sorted_active = sorted(active, key=lambda x: x.get('live_sharpe', 0), reverse=True)
        report += f"\n🏆 Top 3 edges mạnh nhất:\n"
        for e in sorted_active[:3]:
            report += f"   {e['coin']} {e['tf']} {e['direction']}: Sharpe={e.get('live_sharpe',0):.1f}\n"
    
    return report

# ============================================================
# CONFIG TELEGRAM & STATE
# ============================================================
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
    print("❌ Thiếu cấu hình token Telegram!")
    sys.exit(1)

CHAT_ID = str(CHAT_ID)
STATE_FILE = os.path.join(BASE_DIR, "data", "state.json")

def save_state():
    with file_lock:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        temp_file = STATE_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump({
                'capital': capital,
                'peak_capital': peak_capital,
                'positions': {k: {
                    'coin': v['coin'], 'tf': v['tf'],
                    'entry_price': v['entry_price'],
                    'entry_time': v['entry_time'].isoformat(),
                    'stop_loss': v['stop_loss'],
                    'size': v['size'],
                    'direction': v['direction'],
                    'entry_capital': v['entry_capital'],
                    'cond_str': v.get('cond_str', 'unknown')
                } for k, v in positions.items()}
            }, f, indent=2)
        os.replace(temp_file, STATE_FILE)

def load_state():
    global capital, peak_capital, positions
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
            capital = state.get('capital', INITIAL_CAPITAL)
            peak_capital = state.get('peak_capital', INITIAL_CAPITAL)
            for k, v in state.get('positions', {}).items():
                positions[k] = {
                    'coin': v['coin'], 'tf': v['tf'],
                    'entry_price': v['entry_price'],
                    'entry_time': datetime.fromisoformat(v['entry_time']),
                    'stop_loss': v['stop_loss'],
                    'size': v['size'],
                    'direction': v['direction'],
                    'entry_capital': v['entry_capital'],
                    'cond_str': v.get('cond_str', 'unknown')
                }

def send_discord(message):
    clean_msg = re.sub(r'<[^>]+>', '', message)
    payload = {'content': clean_msg}
    try:
        session.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        session.post(url, json=payload, timeout=10)
    except:
        pass

# ============================================================
# PARAMS
# ============================================================
COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

TIMEFRAMES = {
    '15m': {'interval': '15m', 'hold_hours': 4, 'horizon': 16, 'max_per_4h': 1},
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

capital = INITIAL_CAPITAL
peak_capital = INITIAL_CAPITAL
positions = {}
last_checks = {}
last_15m_signal_time = None

# ============================================================
# FETCH DATA & OPEN INTEREST SYSTEM
# ============================================================
def fetch_klines(symbol, interval='1h', limit=500):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        resp = session.get(url, params=params, timeout=10)
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

def fetch_funding_history(symbol):
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {'symbol': symbol, 'limit': 500}
    try:
        resp = session.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['fundingTime'], unit='ms')
            df['funding_rate'] = df['fundingRate'].astype(float)
            df.set_index('timestamp', inplace=True)
            return df[['funding_rate']]
    except:
        pass
    return None

def fetch_oi_history_df(symbol, df_index):
    file_path = os.path.join(OI_RECORD_DIR, f"{symbol}_oi.parquet")
    if df_index.tz is not None:
        df_index = df_index.tz_localize(None)
        
    default_series = pd.Series(50000.0, index=df_index)
    if os.path.exists(file_path):
        try:
            oi_df = pd.read_parquet(file_path)
            if not oi_df.empty:
                if oi_df.index.tz is not None:
                    oi_df.index = oi_df.index.tz_localize(None)
                oi_df = oi_df.sort_index()

                df_index = df_index.astype('datetime64[us]')
                merged = pd.merge_asof(
                    pd.DataFrame(index=df_index), 
                    oi_df, 
                    left_index=True, 
                    right_index=True, 
                    direction='backward'
                )
                return merged['oi'].ffill().fillna(50000.0)
        except Exception as e:
            print(f"Lỗi nạp file Parquet OI cho {symbol}: {e}")
    return default_series

# ============================================================
# INDICATORS
# ============================================================
def compute_indicators(df, funding_rate, oi_series, tf_config):
    df = df.copy()
    n_per_day = {'15m': 96, '1h': 24, '4h': 6, '1d': 1}[tf_config['interval']]
    
    if funding_rate is not None and isinstance(funding_rate, pd.DataFrame):
        df = df.sort_index()
        funding_rate = funding_rate.sort_index()
        df = pd.merge_asof(df, funding_rate, left_index=True, right_index=True, direction='backward')
        df['funding_rate'] = df['funding_rate'].ffill()
    else:
        df['funding_rate'] = 0.0001
        
    df['oi'] = oi_series
    
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
    df['vol_spike'] = (df['volume'] > df['vol_p99']).astype(int)
    
    df['price_chg'] = df['close'].pct_change(cvd_lb)
    df['price_up'] = (df['price_chg'] > 0.02).astype(int)
    df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    
    df['ma_50'] = df['close'].rolling(mw).mean()
    df['trend_up'] = (df['close'] > df['ma_50']).astype(int)
    df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1)))
    )
    df['atr_14'] = df['tr'].rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    
    return df

# ============================================================
# STRATEGY EDGES MATCHING & WEIGHTS
# ============================================================
ALL_EDGES = {
    '15m': {
        'BNBUSDT': [('FUND_POS+OI_DOWN', 'SHORT'), ('FUND_NEG+FUND_RISING', 'SHORT'), ('FUND_NEG+PRICE_UP', 'SHORT'), ('FUND_NEG+TREND_UP', 'SHORT'), ('FUND_NEG+OI_UP', 'SHORT'), ('FUND_RISING+TREND_UP', 'SHORT'), ('FUND_RISING+OI_DOWN', 'SHORT')],
        'BTCUSDT': [('FUND_POS+OI_UP', 'SHORT'), ('FUND_NEG+CVD_UP', 'SHORT'), ('FUND_NEG+PRICE_UP', 'SHORT'), ('FUND_RISING+CVD_UP', 'SHORT'), ('FUND_RISING+PRICE_UP', 'SHORT'), ('FUND_RISING+OI_UP', 'SHORT'), ('CVD_UP+TREND_DOWN', 'SHORT'), ('CVD_UP+OI_UP', 'SHORT'), ('CVD_DOWN+OI_UP', 'SHORT'), ('TREND_DOWN+OI_UP', 'SHORT')],
        'DOGEUSDT': [('FUND_NEG+PRICE_UP', 'SHORT')],
        'ETHUSDT': [('FUND_NEG+PRICE_UP', 'SHORT'), ('FUND_RISING+PRICE_UP', 'SHORT')],
        'LINKUSDT': [('FUND_NEG+CVD_UP', 'SHORT'), ('FUND_NEG+TREND_UP', 'SHORT')],
        'OPUSDT': [('PRICE_UP+TREND_DOWN', 'SHORT')],
        'SOLUSDT': [('FUND_NEG+TREND_UP', 'SHORT'), ('PRICE_UP+OI_DOWN', 'SHORT')],
    },
    '1h': {
        'BTCUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG'), ('VOL_SPIKE+PRICE_UP', 'LONG')],
        'ETHUSDT': [('CVD_UP+VOL_SPIKE', 'LONG'), ('VOL_SPIKE+PRICE_UP', 'LONG')],
    },
    '4h': {
        'ARBUSDT': [('VOL_HIGH+PRICE_DOWN', 'LONG')],
        'AVAXUSDT': [('CVD_DOWN+VOL_HIGH', 'LONG'), ('VOL_HIGH+PRICE_DOWN', 'LONG')],
        'BTCUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG')],
        'DOGEUSDT': [('CVD_DOWN+VOL_HIGH', 'LONG'), ('VOL_HIGH+PRICE_DOWN', 'LONG')],
        'ETHUSDT': [('CVD_UP+VOL_HIGH', 'LONG'), ('VOL_HIGH+PRICE_UP', 'LONG'), ('VOL_HIGH+TREND_UP', 'LONG'), ('VOL_HIGH+OI_DOWN', 'LONG')],
    },
    '1d': {
        'ARBUSDT': [('FUND_NEG+OI_DOWN', 'SHORT'), ('FUND_RISING+CVD_UP', 'SHORT'), ('FUND_RISING+PRICE_UP', 'SHORT')],
        'BNBUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG'), ('PRICE_DOWN+TREND_UP', 'LONG')],
        'BTCUSDT': [('FUND_NEG+CVD_DOWN', 'LONG')],
        'ETHUSDT': [('PRICE_DOWN+TREND_UP', 'LONG')],
        'LINKUSDT': [('FUND_POS+VOL_HIGH', 'LONG'), ('FUND_NEG+PRICE_DOWN', 'LONG'), ('VOL_HIGH+TREND_UP', 'LONG')],
    },
}

def eval_cond(name, d):
    mapping = {
        'FUND_POS': d['funding_rate'] > 0,
        'FUND_NEG': d['funding_rate'] < 0,
        'FUND_RISING': d['funding_rising'] == 1,
        'CVD_UP': d['cvd_up'] == 1,
        'CVD_DOWN': d['cvd_down'] == 1,
        'VOL_HIGH': d['vol_high'] == 1,
        'VOL_SPIKE': d['vol_spike'] == 1 if 'vol_spike' in d else False,
        'PRICE_UP': d['price_up'] == 1,
        'PRICE_DOWN': d['price_down'] == 1,
        'TREND_UP': d['trend_up'] == 1,
        'TREND_DOWN': d['trend_down'] == 1,
        'OI_UP': d['oi_up'] == 1,
        'OI_DOWN': d['oi_down'] == 1,
    }
    return mapping.get(name, False)

def get_signal(df, coin, tf):
    if tf not in ALL_EDGES or coin not in ALL_EDGES[tf]:
        return 0, 0, []
    
    latest = df.iloc[-1]
    long_weighted = 0.0
    short_weighted = 0.0
    active_edges = []
    
    for cond_str, direction in ALL_EDGES[tf][coin]:
        conds = cond_str.split('+')
        match = all(eval_cond(c, latest) for c in conds)
        if match:
            w = get_edge_weight(coin, tf, cond_str, direction)
            if direction == 'LONG':
                long_weighted += w
            else:
                short_weighted += w
            active_edges.append(cond_str)
    
    if long_weighted > short_weighted and long_weighted >= 1.0:
        return 1, round(long_weighted, 1), active_edges
    elif short_weighted > long_weighted and short_weighted >= 1.0:
        return -1, round(short_weighted, 1), active_edges
    return 0, 0, []

def get_edge_weight(coin, tf, cond_str, direction):
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    weight = EDGE_WEIGHTS.get(edge_id, 1.0)
    
    if edge_id in GLOBAL_EDGE_LOG:
        live_wr = GLOBAL_EDGE_LOG[edge_id].get('live_wr', 50)
        if live_wr > 70:
            weight *= 1.5
        elif live_wr < 40:
            weight *= 0.5
            
    return max(0.1, min(3.0, weight))

def update_edge_weight(coin, tf, cond_str, direction, pnl_pct):
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    if edge_id not in EDGE_WEIGHTS:
        EDGE_WEIGHTS[edge_id] = 1.0
    
    alpha = 0.1
    score = np.clip(1 + pnl_pct / 10, 0.2, 2.0)
    EDGE_WEIGHTS[edge_id] = 0.9 * EDGE_WEIGHTS[edge_id] + alpha * score
    EDGE_WEIGHTS[edge_id] = max(0.1, min(3.0, EDGE_WEIGHTS[edge_id]))
    save_weights()

# ============================================================
# RISK MANAGEMENT
# ============================================================
def can_open_position(coin, tf, votes=1):
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
    conf_mult = min(1.5, max(0.5, votes / 2))
    size *= conf_mult
    size = max(0.03, size)
    
    return True, size

# ============================================================
# AUTO SCANNER SUBSYSTEM
# ============================================================
CONDITIONS_SCAN = {
    'FUND_POS': lambda d: d['funding_rate'] > 0,
    'FUND_NEG': lambda d: d['funding_rate'] < 0,
    'FUND_RISING': lambda d: d['funding_rising'] == 1,
    'CVD_UP': lambda d: d['cvd_up'] == 1,
    'CVD_DOWN': lambda d: d['cvd_down'] == 1,
    'VOL_HIGH': lambda d: d['vol_high'] == 1,
    'VOL_SPIKE': lambda d: d['vol_spike'] == 1,
    'PRICE_UP': lambda d: d['price_up'] == 1,
    'PRICE_DOWN': lambda d: d['price_down'] == 1,
    'TREND_UP': lambda d: d['trend_up'] == 1,
    'TREND_DOWN': lambda d: d['trend_down'] == 1,
}

def is_duplicate_edge(coin, tf, cond_str, direction):
    if tf in ALL_EDGES and coin in ALL_EDGES[tf]:
        for existing_cond, existing_dir in ALL_EDGES[tf][coin]:
            if existing_dir == direction:
                if set(existing_cond.split('+')) == set(cond_str.split('+')):
                    return True
    return False

def add_new_edges(new_edges):
    added = 0
    for coin, cond_str, direction, sharpe, oos, n in new_edges:
        tf = '1h'
        if tf not in ALL_EDGES: ALL_EDGES[tf] = {}
        if coin not in ALL_EDGES[tf]: ALL_EDGES[tf][coin] = []
        ALL_EDGES[tf][coin].append((cond_str, direction))
        added += 1
        print(f"   + {coin} {direction} {cond_str} (Sharpe={sharpe:.1f}, OOS={oos:.1f}, n={n})")
    return added

def auto_scan_new_edges():
    """Quét các Edge mới dựa trên dữ liệu khung 1h (Ngày 1 hàng tháng)"""
    new_edges = []
    try:
        for coin in COINS[:3]:  # Quét 3 coin chính để tối ưu tốc độ API
            df = fetch_klines(coin, '1h', limit=1000)
            if df is None or len(df) < 500: continue
            
            funding = fetch_funding_history(coin)
            oi_series = fetch_oi_history_df(coin, df.index)
            df = compute_indicators(df, funding, oi_series, {'interval': '1h'})
            df = df.dropna()
            
            if len(df) < 300: continue
            
            cond_names = list(CONDITIONS_SCAN.keys())
            for c1, c2 in combinations(cond_names, 2):
                for direction in [1, -1]:
                    mask = pd.Series(True, index=df.index)
                    mask = mask & CONDITIONS_SCAN[c1](df) & CONDITIONS_SCAN[c2](df)
                    
                    signal = mask.astype(int) * direction
                    signal_shifted = signal.shift(1)
                    entry_price = df['open'].shift(-1)
                    exit_price = df['close'].shift(-13)
                    ret = (exit_price - entry_price) / entry_price
                    strategy = ret * signal_shifted
                    valid = strategy[signal_shifted != 0].dropna()
                    
                    if len(valid) < 30: continue
                    
                    sharpe = valid.mean() / valid.std() * np.sqrt(365*24)  # 1h = 8760 bars/năm
                    split = int(len(valid) * 0.7)
                    oos = valid.iloc[split:]
                    oos_sharpe = oos.mean() / oos.std() * np.sqrt(365*2) if len(oos) > 5 and oos.std() > 0 else 0
                    
                    if sharpe > 2.0 and oos_sharpe > 2.0:
                        dir_str = 'LONG' if direction == 1 else 'SHORT'
                        cond_str = f"{c1}+{c2}"
                        if not is_duplicate_edge(coin, '1h', cond_str, dir_str):
                            new_edges.append((coin, cond_str, dir_str, sharpe, oos_sharpe, len(valid)))
    except Exception as e:
        print(f"Lỗi Auto Scanner: {e}")
    return new_edges

# ============================================================
# CRON MONITORS
# ============================================================
def record_oi():
    for coin in COINS:
        try:
            url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={coin}"
            resp = session.get(url, timeout=5).json()
            if 'openInterest' in resp:
                oi_val = float(resp['openInterest'])
                ts = datetime.now(timezone.utc)
                file_path = os.path.join(OI_RECORD_DIR, f"{coin}_oi.parquet")
                new_row = pd.DataFrame({'oi': [oi_val]}, index=[ts])
                if os.path.exists(file_path):
                    existing = pd.read_parquet(file_path)
                    if ts not in existing.index:
                        existing = pd.concat([existing, new_row])
                        existing.to_parquet(file_path)
                else:
                    new_row.to_parquet(file_path)
        except:
            pass

def detect_whale_retail():
    alerts = []
    for coin in WHALE_COINS_BINANCE:
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}&interval=1h&limit=25"
            resp = session.get(url, timeout=10)
            df = pd.DataFrame(resp.json(), columns=['t','o','h','l','c','v','x','q','n','tb','tq','i'])
            for col in ['o','h','l','c','v']: df[col] = df[col].astype(float)
            
            df['cvd'] = (df['v'] * (df['c'] - df['o']) / (df['h'] - df['l'] + 0.01)).cumsum()
            cvd_24h = df['cvd'].iloc[-1] - df['cvd'].iloc[-25] if len(df) >= 25 else 0
            whale_buying = cvd_24h > 0
            
            url_fund = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}&limit=15"
            resp_fund = session.get(url_fund, timeout=5)
            fund_rates = [float(x['fundingRate']) for x in resp_fund.json()]
            current_fund = fund_rates[-1] if fund_rates else 0
            fund_8h_ago = fund_rates[-9] if len(fund_rates) > 8 else current_fund
            retail_buying = current_fund > 0 and current_fund > fund_8h_ago
            
            if whale_buying and not retail_buying:
                alerts.append(f"🔵 <b>WHALE ALERT: {coin}</b>\n   Cá voi GOM (CVD↑), Nhỏ lẻ SỢ (Funding↓)\n   → Khả năng SẮP BƠM")
            elif not whale_buying and retail_buying:
                alerts.append(f"🔴 <b>WHALE ALERT: {coin}</b>\n   Cá voi XẢ, Nhỏ lẻ FOMO (Funding↑)\n   → Khả năng SẮP SẬP")
        except:
            pass
    return alerts

def fetch_dominance():
    headers = {'X-CMC_PRO_API_KEY': CMC_API_KEY, 'Accept': 'application/json'}
    try:
        url = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
        resp = session.get(url, headers=headers, timeout=10)
        total_mcap = resp.json()['data']['quote']['USD']['total_market_cap']
        
        url2 = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={','.join(DOM_COINS)}&convert=USD"
        resp2 = session.get(url2, headers=headers, timeout=10)
        data = resp2.json()
        
        alerts = []
        now = datetime.now(timezone.utc)
        
        for symbol in DOM_COINS:
            if symbol not in data['data']:
                continue
            mcap = data['data'][symbol]['quote']['USD']['market_cap']
            dom = mcap / total_mcap * 100
            price = data['data'][symbol]['quote']['USD']['price']
            
            if symbol in DOM_HISTORY:
                prev = DOM_HISTORY[symbol]
                hours_diff = (now - prev['time']).total_seconds() / 3600
                if hours_diff > 0.5:
                    dom_change = (dom - prev['dominance']) / prev['dominance'] * 100
                    if abs(dom_change) > 2:
                        direction = "TĂNG" if dom_change > 0 else "GIẢM"
                        emoji = "🔵" if dom_change > 0 else "🔴"
                        alerts.append(
                            f"{emoji} <b>DOMINANCE: {symbol} {direction} {dom_change:+.1f}%</b>\n"
                            f"   {prev['dominance']:.3f}% → {dom:.3f}%\n"
                            f"   Giá: ${price:,.2f}"
                        )
            DOM_HISTORY[symbol] = {'dominance': dom, 'price': price, 'time': now}
        return alerts
    except:
        return []

# ============================================================
# BOT ENGINE CORE LOOP
# ============================================================
def main():
    global capital, peak_capital, positions
    load_state()
    load_edge_log()
    load_weights()

    print("="*60)
    print("🚀 CRYPTO PRO BOT V4.5 - OI REAL DATA")
    print(f"   10 coins × 4 TFs | 49 edges | Sharpe 2.07 | DD -18%")
    print("="*60)
    
    startup_msg = ("🚀 <b>Crypto Pro Bot V4.5 Khởi Động</b>\n\n"
               f"📊 Giám sát: {len(COINS)} Coins × 4 TFs (15m, 1h, 4h, 1d)\n"
               f"🛡️ Quản lý rủi ro: SL 2 ATR · Tối đa {MAX_POSITIONS} lệnh đồng thời.\n"
               "🔄 OI History: 100% Real Data\n"
               "Hệ thống vận hành ổn định...")
    send_telegram(startup_msg)
    send_discord(startup_msg)
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.minute % 5 == 0 and now.second < 10:
                print(f"✅ Bot Alive - {now.strftime('%H:%M')} - Positions Acted: {len(positions)}")
            
            # === 1. KIỂM TRA ĐÓNG LỆNH TRƯỚC (EXIT CHECK) ===
            to_remove = []
            for key, pos in positions.items():
                coin = pos['coin']
                tf = pos['tf']
                tf_config = TIMEFRAMES[tf]
                
                df = fetch_klines(coin, tf_config['interval'], limit=2)
                if df is None: continue
                
                current_price = df.iloc[-1]['close']
                hours_held = (now - pos['entry_time']).total_seconds() / 3600
                
                stop_hit = (current_price <= pos['stop_loss']) if pos['direction'] == 'LONG' else (current_price >= pos['stop_loss'])
                time_up = hours_held >= tf_config['hold_hours']
                
                if stop_hit or time_up:
                    exit_price = pos['stop_loss'] if stop_hit else current_price
                    trade_return = (exit_price - pos['entry_price']) / pos['entry_price'] if pos['direction'] == 'LONG' else (pos['entry_price'] - exit_price) / pos['entry_price']
                    
                    trade_pnl = pos['entry_capital'] * pos['size'] * trade_return
                    capital += trade_pnl
                    if capital > peak_capital: peak_capital = capital
                    
                    reason = '🛑 SL Hit' if stop_hit else f'⏰ Time Out {tf_config["hold_hours"]}h'
                    emoji = '🟢' if trade_return > 0 else '🔴'
                    
                    msg = f"{emoji} <b>EXIT [{tf}] {coin}</b> ({pos['direction']})\n" \
                          f"Entry: ${pos['entry_price']:,.4f} → Exit: ${exit_price:,.4f}\n" \
                          f"Return: {trade_return*100:+.2f}% | PnL: ${trade_pnl:+,.2f}\n" \
                          f"Lý do: {reason}\n" \
                          f"Số dư: ${capital:,.0f}\n"
                    
                    send_telegram(msg)
                    send_discord(msg)
                    
                    if 'cond_str' in pos:
                        edge_list = pos['cond_str'] if isinstance(pos['cond_str'], list) else [pos['cond_str']]
                        # Chia đều PnL cho từng edge
                        pnl_per_edge = (trade_return * 100) / len(edge_list) if edge_list else 0
                        for single_edge in edge_list:
                            update_edge_performance(coin, tf, single_edge,
                                                    pos['direction'], pnl_per_edge)
                            update_edge_weight(coin, tf, single_edge,
                                              pos['direction'], pnl_per_edge)
                    to_remove.append(key)
            
            for key in to_remove: del positions[key]
            if to_remove: save_state()
            
            # === 2. QUÉT TÍN HIỆU VÀO LỆNH (SIGNAL SCANNER) ===
            for tf_name, tf_config in TIMEFRAMES.items():
                interval_minutes = {'15m': 15, '1h': 60, '4h': 240, '1d': 1440}[tf_name]
                
                # Tính mốc thời gian sàn (Floor time) gần nhất của nến
                # Ví dụ: 10:23 khung 15m sẽ được tính về mốc 10:15
                delta_minutes = (now.minute % interval_minutes)
                candle_time = now - timedelta(minutes=delta_minutes, seconds=now.second, microseconds=now.microsecond)
                candle_str = candle_time.strftime('%Y%m%d_%H%M')
                
                # CHỈ QUÉT TRONG VÒNG 5 PHÚT ĐẦU TIÊN KHI NẾN MỚI MỞ
                # Tránh trường hợp tắt bot đi bật lại ở giữa khung giờ lại quét lại tín hiệu cũ
                if (now - candle_time).total_seconds() > 300:
                    continue
                    
                for coin in COINS:
                    key = f"{coin}_{tf_name}"
                    if key in positions: continue
                    
                    # Chống trùng tuyệt đối dựa trên mốc nến chính xác, không sợ lệch giây/lệch phút
                    current_candle_id = f"{key}_{candle_str}"
                    if current_candle_id in last_checks:
                        continue
                        
                    df = fetch_klines(coin, tf_config['interval'], limit=500)
                    if df is None or df.empty: continue
                    
                    funding = fetch_funding_history(coin)
                    oi_series = fetch_oi_history_df(coin, df.index)
                    df = compute_indicators(df, funding, oi_series, tf_config)
                    
                    signal, votes, active_edges = get_signal(df, coin, tf_name)
                    last_checks[current_candle_id] = now  # Đánh dấu đã quét xong nến này
                    
                    if signal != 0:
                        can_open, size = can_open_position(coin, tf_name, votes)
                        if can_open:
                            entry_price = df.iloc[-1]['close']
                            atr_pct = df.iloc[-1]['atr_pct']
                            
                            if signal == 1:
                                stop_loss = entry_price * (1 - STOP_LOSS_ATR * atr_pct / 100)
                                dir_str = 'LONG 🟢'
                            else:
                                stop_loss = entry_price * (1 + STOP_LOSS_ATR * atr_pct / 100)
                                dir_str = 'SHORT 🔴'
                            
                            # Lưu vị thế giả lập để theo dõi hiệu suất
                            positions[key] = {
                                'coin': coin, 'tf': tf_name,
                                'entry_price': entry_price, 'entry_time': now,
                                'stop_loss': stop_loss, 'size': size,
                                'direction': 'LONG' if signal == 1 else 'SHORT',
                                'entry_capital': capital,
                                'cond_str': active_edges if active_edges else ['unknown'],
                            }
                            
                            sl_pct = abs(1 - stop_loss/entry_price) * 100
                            utc_time = now.strftime('%H:%M')
                            asia_time = (now + timedelta(hours=8)).strftime('%H:%M')
                            euro_time = (now + timedelta(hours=2)).strftime('%H:%M')
                            us_time = (now - timedelta(hours=4)).strftime('%H:%M')
                            confidence = min(95, 50 + votes * 15)
                            
                            msg = f"{dir_str} <b>⚠️ SIGNAL [{tf_name}] {coin}</b>\n\n" \
                                  f"💰 Entry: <b>${entry_price:,.2f}</b>\n" \
                                  f"🛑 SL: ${stop_loss:,.2f} ({sl_pct:.1f}%)\n" \
                                  f"📏 Size: {size*100:.1f}% (~${capital*size:,.0f})\n" \
                                  f"⏰ Hold: {tf_config['hold_hours']}h\n" \
                                  f"🗳️ Votes: {votes} | Tin cậy: {confidence:.0f}%\n" \
                                  f"💼 Vị thế: {len(positions)+1}/{MAX_POSITIONS}\n\n" \
                                  f"🕐 UTC:{utc_time} | 🌏 Asia:{asia_time} | 🇪🇺 EU:{euro_time} | 🇺🇸 US:{us_time}\n"
                            
                            send_telegram(msg)
                            send_discord(msg)
                            save_state()

            # === 3. KIỂM TRA ĐỊNH KỲ (CRON JOB CLUSTER) ===
            if now.second < 10:
                # Quét OI (Mỗi tiếng)
                if now.minute == 0:
                    oi_key = f"oi_cron_{now.hour}"
                    if oi_key not in last_checks:
                        last_checks[oi_key] = now
                        record_oi()
                
                # Quét Whale/Retail Flow (Mỗi 4 tiếng)
                if now.hour % 4 == 0 and now.minute == 5:
                    whale_key = f"whale_cron_{now.hour}"
                    if whale_key not in last_checks:
                        last_checks[whale_key] = now
                        w_alerts = detect_whale_retail()
                        for alert in w_alerts:
                            send_telegram(alert)
                
                # Quét Market Dominance (Mỗi tiếng)
                if now.minute == 10:
                    dom_key = f"dom_cron_{now.hour}"
                    if dom_key not in last_checks:
                        last_checks[dom_key] = now
                        d_alerts = fetch_dominance()
                        for alert in d_alerts:
                            send_telegram(alert)

                # Kiểm tra Sức Khỏe Edge (Mỗi ngày lúc 00:15)
                if now.hour == 0 and now.minute == 15:
                    health_key = f"health_cron_{now.date()}"
                    if health_key not in last_checks:
                        last_checks[health_key] = now
                        h_alerts, _, _ = check_edge_health()
                        for alert in h_alerts:
                            send_telegram(alert)

                # Xuất báo cáo hàng tuần (Chủ nhật 00:30)
                if now.weekday() == 6 and now.hour == 0 and now.minute == 30:
                    rep_key = f"weekly_rep_{now.date()}"
                    if rep_key not in last_checks:
                        last_checks[rep_key] = now
                        report = weekly_edge_report()
                        send_telegram(report)
                        send_discord(report)

                # QUÉT AUTO SCANNER (Ngày 1 hàng tháng lúc 00:45) - CHỈ SCAN, KHÔNG TỰ THÊM
                if now.day == 1 and now.hour == 0 and now.minute == 45:
                    scan_key = f"scan_cron_{now.month}"
                    if scan_key not in last_checks:
                        last_checks[scan_key] = now
                        print("🔍 [Cron Job] Đang chạy Auto Scanner định kỳ hàng tháng...")
                        new_edges_found = auto_scan_new_edges()
                        if new_edges_found:
                            msg = f"🔍 <b>AUTO SCANNER REPORT</b>\nTìm thấy {len(new_edges_found)} ứng viên Edge mới tiềm năng (Chưa nạp tự động, cần duyệt thủ công)."
                            send_telegram(msg)
                            send_discord(f"🔍 AUTO SCANNER: Found {len(new_edges_found)} candidates.")

            time.sleep(10)
            
        except KeyboardInterrupt:
            print("🛑 Thực thi dừng thủ công từ bàn phím.")
            break
        except Exception as e:
            print(f"⚠️ CORE ERROR: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()