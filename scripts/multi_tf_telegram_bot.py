"""
V4.0 MODULE 3+4: WEIGHT ADJUSTER + REGIME ADAPTER
- Edge thắng gần đây → tăng weight vote
- Edge thua gần đây → giảm weight vote
- Regime hiện tại → ưu tiên edge phù hợp
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import requests
session = requests.Session()
import json
from itertools import combinations

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

def load_edge_log():
    if os.path.exists(EDGE_LOG_FILE):
        with open(EDGE_LOG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_edge_log(log):
    with open(EDGE_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2, default=str)
def save_weights():
    with open(WEIGHT_FILE, 'w') as f:
        json.dump(EDGE_WEIGHTS, f)

def load_weights():
    global EDGE_WEIGHTS
    EDGE_WEIGHTS = {}
    if os.path.exists(WEIGHT_FILE):
        with open(WEIGHT_FILE, 'r') as f:
            EDGE_WEIGHTS = json.load(f)

def update_edge_performance(coin, tf, cond_str, direction, pnl_pct):
    """Cập nhật hiệu suất edge sau mỗi lệnh"""
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    log = load_edge_log()
    
    if edge_id not in log:
        log[edge_id] = {
            'coin': coin, 'tf': tf, 'conditions': cond_str, 'direction': direction,
            'trades': [], 'live_sharpe': 0, 'live_wr': 0, 'status': 'ACTIVE',
            'first_seen': datetime.now(timezone.utc).isoformat()
        }
    
    log[edge_id]['trades'].append({
        'time': datetime.now(timezone.utc).isoformat(),
        'pnl_pct': round(pnl_pct, 4)
    })
    
    # Chỉ giữ 50 trades gần nhất
    if len(log[edge_id]['trades']) > 50:
        log[edge_id]['trades'] = log[edge_id]['trades'][-50:]
    
    # Tính Live Sharpe + WR
    trades = [t['pnl_pct'] for t in log[edge_id]['trades']]
    if len(trades) >= 10:
        avg = sum(trades) / len(trades)
        std = (sum((t - avg)**2 for t in trades) / len(trades)) ** 0.5
        # Dùng số trade/năm thực tế từ dữ liệu
        trades_count = len(trades)
        days_span = 365  # mặc định
        log[edge_id]['live_sharpe'] = round(avg / std * np.sqrt(trades_count), 2) if std > 0 else 0
        log[edge_id]['live_wr'] = round(sum(1 for t in trades if t > 0) / len(trades) * 100, 1)
    
    save_edge_log(log)

def check_edge_health():
    """Kiểm tra sức khỏe, tự DEPRECATED edge chết"""
    log = load_edge_log()
    alerts = []
    now = datetime.now(timezone.utc)
    
    for edge_id, data in log.items():
        if data['status'] == 'DEPRECATED':
            continue
        
        trades = data.get('trades', [])
        if len(trades) >= 30:
            recent = trades[-30:]
            avg_recent = sum(t['pnl_pct'] for t in recent) / len(recent)
            win_count = sum(1 for t in recent if t['pnl_pct'] > 0)
            win_rate_recent = win_count / len(recent)
            
            # Deprecate nếu thắng <30% hoặc lỗ TB >1%
            if win_rate_recent < 0.3 or avg_recent < -0.01:
                data['status'] = 'DEPRECATED'
                data['deprecated_time'] = now.isoformat()
                alerts.append(
                    f"⚠️ <b>EDGE DEPRECATED:</b> {edge_id[:60]}...\n"
                    f"   Live WR: {data['live_wr']}% | Live Sharpe: {data['live_sharpe']}\n"
                    f"   → Tự động loại bỏ"
                )
    
    save_edge_log(log)
    
    # Đếm
    active = sum(1 for v in log.values() if v['status'] == 'ACTIVE')
    deprecated = sum(1 for v in log.values() if v['status'] == 'DEPRECATED')
    
    return alerts, active, deprecated

def weekly_edge_report():
    """Báo cáo hàng tuần"""
    log = load_edge_log()
    active = [v for v in log.values() if v['status'] == 'ACTIVE']
    deprecated = [v for v in log.values() if v['status'] == 'DEPRECATED']
    
    report = f"📊 <b>WEEKLY EDGE REPORT</b>\n\n"
    report += f"✅ Active: {len(active)} edges\n"
    report += f"❌ Deprecated: {len(deprecated)} edges\n"
    
    if deprecated:
        report += f"\n🔻 Vừa loại: {len(deprecated)} edges\n"
    
    # Top 3 edge mạnh nhất
    sorted_active = sorted(active, key=lambda x: x.get('live_sharpe', 0), reverse=True)
    report += f"\n🏆 Top edges:\n"
    for e in sorted_active[:3]:
        report += f"   {e['coin']} {e['tf']} {e['direction']}: Sharpe={e.get('live_sharpe',0):.1f}\n"
    
    return report

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
# STATE FILE (giữ positions khi restart)
# ============================================================
STATE_FILE = os.path.join(BASE_DIR, "data", "state.json")

def save_state():
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
        }, f)
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

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1511598618652442655/iIyTS55FJQGg21zgPYeyZz1Utc_pG2jY9tdGNJ66XZVTfNdJDk_NFdUygYrAUoRS6hpY"
def send_discord(message):
    """Gửi tin nhắn qua Discord webhook"""
    # Discord không hỗ trợ HTML, chuyển sang plain text
    import re
    clean_msg = re.sub(r'<[^>]+>', '', message)  # Xóa HTML tags
    payload = {'content': clean_msg}
    try:
        session.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass
# ============================================================
# TOÀN BỘ CONFIGetch_oi_bybit
# ============================================================
COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

TIMEFRAMES = {
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
        session.post(url, json=payload, timeout=10)
    except:
        pass

# ============================================================
# DATA
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

def fetch_funding_rate(symbol):
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    params = {'symbol': symbol, 'limit': 1}
    try:
        resp = session.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return float(data[0]['fundingRate']) if data else 0.0001
    except:
        pass
    return 0.0001

def fetch_oi(symbol):
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    try:
        resp = session.get(url, timeout=5).json()
        if 'openInterest' in resp:
            return float(resp['openInterest'])
    except:
        pass
    return 50000

# ============================================================
# INDICATORS
# ============================================================
def compute_indicators(df, funding_rate, oi_value, tf_config):
    df = df.copy()
    n_per_day = {'15m': 96, '1h': 24, '4h': 6, '1d': 1}[tf_config['interval']]
    
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
    df['vol_spike'] = (df['volume'] > df['vol_p99']).astype(int)
    
    df['price_chg'] = df['close'].pct_change(cvd_lb)
    df['price_up'] = (df['price_chg'] > 0.02).astype(int)
    df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    
    df['ma_50'] = df['close'].rolling(mw).mean()
    df['trend_up'] = (df['close'] > df['ma_50']).astype(int)
    df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    
    df['tr'] = np.maximum(
    df['high'] - df['low'],
    np.maximum(
        abs(df['high'] - df['close'].shift(1)),
        abs(df['low'] - df['close'].shift(1))
    )
)
    df['atr_14'] = df['tr'].rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close'] * 100
    
    return df

# ============================================================
# TOÀN BỘ EDGES (FINAL)
# ============================================================
ALL_EDGES = {
    '4h': {
        'BTCUSDT': [('FUND_NEG+VOL_HIGH', 'LONG'), ('FUND_NEG+PRICE_DOWN', 'LONG')],
        'ARBUSDT': [('FUND_NEG+VOL_HIGH', 'LONG')],
        'AVAXUSDT': [('VOL_HIGH+PRICE_DOWN', 'LONG'), ('FUND_RISING+VOL_HIGH', 'LONG')],
        'OPUSDT': [('FUND_NEG+VOL_SPIKE', 'LONG'), ('FUND_RISING+VOL_HIGH', 'LONG')],
        'LINKUSDT': [('FUND_RISING+VOL_HIGH', 'LONG')],
        'XRPUSDT': [('VOL_SPIKE+PRICE_DOWN', 'LONG'), ('VOL_HIGH+PRICE_DOWN', 'LONG')],
    },
    '1d': {
        'BTCUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG'), ('FUND_NEG+TREND_UP', 'LONG'), ('FUND_NEG+CVD_DOWN', 'LONG')],
        'ETHUSDT': [('FUND_NEG+VOL_HIGH', 'SHORT')],
        'LINKUSDT': [('FUND_POS+VOL_HIGH', 'LONG'), ('CVD_DOWN+VOL_HIGH', 'LONG'), ('FUND_NEG+FUND_RISING', 'LONG')],
        'XRPUSDT': [('FUND_POS+VOL_HIGH', 'LONG'), ('CVD_DOWN+VOL_HIGH', 'LONG'), ('VOL_HIGH+TREND_UP', 'LONG')],
        'AVAXUSDT': [('PRICE_UP+TREND_DOWN', 'SHORT')],
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
        'VOL_SPIKE': d['vol_spike'] if 'vol_spike' in d else False,
        'PRICE_UP': d['price_up'] == 1,
        'PRICE_DOWN': d['price_down'] == 1,
        'TREND_UP': d['trend_up'] == 1,
        'TREND_DOWN': d['trend_down'] == 1,
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
    # Confidence multiplier: votes 1 → 0.5x, votes 3+ → 1.5x
    conf_mult = min(1.5, max(0.5, votes / 2))
    size *= conf_mult
    size = max(0.03, size)
    
    return True, size
def record_oi():
    # Chỉ lưu nếu cách lần cuối > 3500 giây (~1h)
    if hasattr(record_oi, 'last_time'):
        if (datetime.now(timezone.utc) - record_oi.last_time).total_seconds() < 3500:
            return
    record_oi.last_time = datetime.now(timezone.utc)
    OI_RECORD_DIR = os.path.join(BASE_DIR, "data", "oi_history")
    os.makedirs(OI_RECORD_DIR, exist_ok=True)
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
        except Exception as e:
            print(f"OI record error {coin}: {e}")
def detect_whale_retail():
    """Phát hiện cá voi vs cá con"""
    alerts = []
    
    for coin in WHALE_COINS_BINANCE:
        try:
            # Fetch 1h klines
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}&interval=1h&limit=200"
            resp = session.get(url, timeout=10)
            df = pd.DataFrame(resp.json(), columns=['t','o','h','l','c','v','x','q','n','tb','tq','i'])
            for col in ['o','h','l','c','v']: df[col] = df[col].astype(float)
            
            # CVD
            df['cvd'] = (df['v'] * (df['c'] - df['o']) / (df['h'] - df['l'] + 0.01)).cumsum()
            cvd_24h = df['cvd'].iloc[-1] - df['cvd'].iloc[-25] if len(df) >= 25 else 0
            whale_buying = cvd_24h > 0
            
            
            # Funding
            url_fund = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}&limit=50"
            resp_fund = session.get(url_fund, timeout=5)
            fund_data = resp_fund.json()
            fund_rates = [float(x['fundingRate']) for x in fund_data]
            current_fund = fund_rates[0] if fund_rates else 0
            fund_8h_ago = fund_rates[8] if len(fund_rates) > 8 else current_fund
            retail_buying = current_fund > 0 and current_fund > fund_8h_ago
            
            whale_score = (1 if whale_buying else 0)
            retail_score = 1 if retail_buying else 0
            
            if whale_score >= 1 and retail_score == 0:
                alerts.append(f"🔵 <b>WHALE ALERT: {coin}</b>\n   Cá voi đang GOM (CVD↑), Cá con SỢ (Funding↓)\n   → Khả năng SẮP BƠM")
            elif whale_score == 0 and retail_score == 1:
                alerts.append(f"🔴 <b>WHALE ALERT: {coin}</b>\n   Cá voi đang XẢ, Cá con MUA\n   → Khả năng PHÂN PHỐI - SẮP GIẢM")
        
        except:
            pass
    
    return alerts

# ============================================================
# MAIN
# ============================================================
def main():
    global capital, peak_capital, positions, last_15m_signal_time
    load_state()
    load_weights()

    print("="*60)
    print("🚀 CRYPTO PRO BOT V4.0 - VIP PRO")
    print("="*60)
    print(f"   10 coins × 4 TFs | 15m: 3 edge (max 1/4h)")
    print(f"   Max {MAX_POSITIONS} positions | SL 2 ATR")
    print("="*60)
    
    send_telegram("🚀 <b>Crypto Pro Bot V4.0 - VIP PRO</b>\n\n"
                  "⏱️ 4 TFs: 15m(3) · 1h · 4h · 1d\n"
                  "🪙 10 Coins\n📊 LONG + SHORT\n"
                  "🛡️ SL 2 ATR · Max 5 pos\n\n"
                  "Đang chờ tín hiệu...")
    send_discord("🚀 Crypto Pro Bot V4.0 - VIP PRO\n\n"
                  "⏱️ 4 TFs: 15m(3) · 1h · 4h · 1d\n"
                  "🪙 10 Coins\n📊 LONG + SHORT\n"
                  "🛡️ SL 2 ATR · Max 5 pos\n\n"
                  "Đang chờ tín hiệu...")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.minute % 5 == 0 and now.second < 30:
                print(f"✅ Bot alive - {now.strftime('%H:%M')} - Positions: {len(positions)}")
            
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
                    
                    trade_pnl = pos['entry_capital'] * pos['size'] * trade_return
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
                    send_discord(msg)
                    # Cập nhật edge performance
                    if 'cond_str' in pos:
                        edge_list = pos['cond_str'] if isinstance(pos['cond_str'], list) else [pos['cond_str']]
                        for single_edge in edge_list:
                            update_edge_performance(coin, tf, single_edge,
                                                    pos['direction'], trade_return * 100)
                            update_edge_weight(coin, tf, single_edge,
                                              pos['direction'], trade_return * 100)
                    save_state()
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
                    
                    LIMITS = {'15m': 1500, '1h': 1000, '4h': 1000, '1d': 1000}
                    limit = LIMITS.get(tf_name, 500)
                    df = fetch_klines(coin, tf_config['interval'], limit=limit)
                    if df is None:
                        continue
                    
                    funding = fetch_funding_rate(coin)
                    oi = fetch_oi(coin)
                    df = compute_indicators(df, funding, oi, tf_config)
                    
                    signal, votes, active_edges = get_signal(df, coin, tf_name)
                    last_checks[last_key] = now
                    
                    if signal != 0:
                        can_open, size = can_open_position(coin, tf_name, votes)
                        
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
                                'direction': 'LONG' if signal == 1 else 'SHORT',
                                'entry_capital': capital,
                                'cond_str': active_edges if active_edges else ['unknown'],
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
                            send_discord(msg)
                            save_state()
                            print(f"   {dir_str} [{tf_name}] {coin}: ${entry_price:,.4f}")
                                        
            time.sleep(30)
            
        except KeyboardInterrupt:
            send_telegram("🛑 Bot đã dừng.")
            send_discord("🛑 Bot đã dừng.")
            break
        except Exception as e:
            print(f"⚠️ ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        # === DOMINANCE CHECK (mỗi 1h) ===
        if now.minute < 5 and now.second < 30:
            dom_key = f"dom_{now.hour}"
            if dom_key not in last_checks:
                last_checks[dom_key] = now
                dom_alerts = fetch_dominance()
                for alert in dom_alerts:
                    send_telegram(alert)
                    send_discord(alert)
        
        # === WEEKLY REPORT (Chủ nhật 00:00) ===
        if now.weekday() == 6 and now.hour == 0 and now.minute < 5:
            report_key = f"weekly_{now.date()}"
            if report_key not in last_checks:
                last_checks[report_key] = now
                report = weekly_edge_report()
                send_telegram(report)
                send_discord(report)
        # === EDGE HEALTH CHECK (mỗi ngày 00:00) ===
        if now.hour == 0 and now.minute < 5:
            health_key = f"health_{now.date()}"
            if health_key not in last_checks:
                last_checks[health_key] = now
                health_alerts, active, deprecated = check_edge_health()
                for alert in health_alerts:
                    send_telegram(alert)
                    send_discord(alert)
        
        # === AUTO SCANNER (Ngày 1 hàng tháng) - CHỈ SCAN, KHÔNG TỰ ĐỘNG THÊM ===
        if now.day == 1 and now.hour == 0 and now.minute < 5:
            scan_key = f"scan_{now.month}"
            if scan_key not in last_checks:
                last_checks[scan_key] = now
                new_edges = auto_scan_new_edges()
                if new_edges:
                    send_telegram(f"🔍 AUTO SCANNER: Tìm thấy {len(new_edges)} edges mới, chưa thêm (cần duyệt thủ công)")
                    send_discord(f"🔍 AUTO SCANNER: {len(new_edges)} candidates found")
        # === OI RECORDER (mỗi 1h) ===
        if now.minute < 5:
            oi_key = f"oi_record_{now.hour}"
            if oi_key not in last_checks:
                last_checks[oi_key] = now
                record_oi()
                print(f"✅ OI recorded at {now.strftime('%H:%M')}")            
        
        # === WHALE/RETAIL CHECK (mỗi 4h) ===
        if now.hour % 4 == 0 and now.minute < 5 and now.second < 30:
            whale_key = f"whale_{now.hour}"
            if whale_key not in last_checks:
                last_checks[whale_key] = now
                whale_alerts = detect_whale_retail()
                for alert in whale_alerts:
                    send_telegram(alert)
                    send_discord(alert)
        
        time.sleep(30)
            

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
                        direction = "TANG" if dom_change > 0 else "GIAM"
                        emoji = "🔵" if dom_change > 0 else "🔴"
                        alerts.append(
                            f"{emoji} <b>DOMINANCE: {symbol} {direction} {dom_change:+.1f}%</b>\n"
                            f"   {prev['dominance']:.3f}% → {dom:.3f}%\n"
                            f"   Gia: ${price:,.2f}"
                        )
            DOM_HISTORY[symbol] = {'dominance': dom, 'price': price, 'time': now}
        return alerts
    except Exception as e:
        print(f"Dominance error: {e}")
        return []
    
CONDITIONS_SCAN = {
    'FUND_P5': lambda d: d['funding_rate'] < d['funding_p5'],
    'FUND_P95': lambda d: d['funding_rate'] > d['funding_p95'],
    'FUND_P99': lambda d: d['funding_rate'] > d['funding_p99'],
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
# Edge weights (mặc định 1.0)
EDGE_WEIGHTS = {}

def get_edge_weight(coin, tf, cond_str, direction):
    """Tính weight cho edge dựa trên hiệu suất gần đây + regime"""
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    
    # Base weight
    weight = EDGE_WEIGHTS.get(edge_id, 1.0)
    
    # Điều chỉnh theo live performance
    log = load_edge_log()
    if edge_id in log:
        live_wr = log[edge_id].get('live_wr', 50)
        if live_wr > 70:
            weight *= 1.5
        elif live_wr < 40:
            weight *= 0.5
    
    # Điều chỉnh theo regime (nếu có regime detector)
    # Có thể thêm sau
    
    return max(0.1, min(3.0, weight))  # Clamp 0.1 - 3.0

def update_edge_weight(coin, tf, cond_str, direction, pnl_pct):
    edge_id = f"{coin}_{tf}_{cond_str}_{direction}"
    if edge_id not in EDGE_WEIGHTS:
        EDGE_WEIGHTS[edge_id] = 1.0
    
    alpha = 0.1
    # pnl_pct đang là % (vd: 1.0 = 1%)
    score = 1.5 if pnl_pct > 2.0 else (0.5 if pnl_pct < -2.0 else 1.0)
    EDGE_WEIGHTS[edge_id] = 0.9 * EDGE_WEIGHTS[edge_id] + alpha * score
    EDGE_WEIGHTS[edge_id] = max(0.1, min(3.0, EDGE_WEIGHTS[edge_id]))
    save_weights()    

def auto_scan_new_edges():
    """Quét edge mới từ dữ liệu 1h gần nhất"""
    new_edges = []
    
    try:
        for coin in COINS[:3]:  # Chỉ scan 3 coin chính để nhanh
            df = fetch_klines(coin, '1h', limit=1000)
            if df is None or len(df) < 500:
                continue
            
            funding = fetch_funding_rate(coin)
            oi = fetch_oi(coin)
            tf_config = TIMEFRAMES['1h']
            df = compute_indicators(df, funding, oi if oi else 50000, tf_config)
            df = df.dropna()
            
            if len(df) < 300:
                continue
            
            # Quét tổ hợp 2 điều kiện
            cond_names = list(CONDITIONS_SCAN.keys())
            for c1, c2 in combinations(cond_names, 2):
                for direction in [1, -1]:
                    mask = pd.Series(True, index=df.index)
                    mask = mask & CONDITIONS_SCAN[c1](df) & CONDITIONS_SCAN[c2](df)
                    
                    signal = mask.astype(int) * direction
                    signal_shifted = signal.shift(1)
                    ret = (df['close'].shift(-12) - df['open']) / df['open']
                    strategy = ret * signal_shifted
                    valid = strategy[signal_shifted != 0].dropna()
                    
                    if len(valid) < 30:
                        continue
                    
                    sharpe = valid.mean() / valid.std() * np.sqrt(365*2) if valid.std() > 0 else 0
                    
                    # OOS: 30% cuối
                    split = int(len(valid) * 0.7)
                    oos = valid.iloc[split:]
                    oos_sharpe = oos.mean() / oos.std() * np.sqrt(365*2) if len(oos) > 5 and oos.std() > 0 else 0
                    
                    if sharpe > 2.0 and oos_sharpe > 2.0:
                        dir_str = 'LONG' if direction == 1 else 'SHORT'
                        cond_str = f"{c1}+{c2}"
                        
                        # Kiểm tra trùng với edge hiện có
                        edge_id = f"{coin}_1h_{cond_str}_{dir_str}"
                        if not is_duplicate_edge(coin, '1h', cond_str, dir_str):
                            new_edges.append((coin, cond_str, dir_str, sharpe, oos_sharpe, len(valid)))
    
    except Exception as e:
        print(f"Auto scan error: {e}")
    
    return new_edges

def is_duplicate_edge(coin, tf, cond_str, direction):
    """Kiểm tra edge đã tồn tại chưa"""
    if tf in ALL_EDGES and coin in ALL_EDGES[tf]:
        for existing_cond, existing_dir in ALL_EDGES[tf][coin]:
            if existing_dir == direction:
                # Kiểm tra điều kiện tương đương
                existing_set = set(existing_cond.split('+'))
                new_set = set(cond_str.split('+'))
                if existing_set == new_set:
                    return True
    return False

def add_new_edges(new_edges):
    """Thêm edge mới vào ALL_EDGES"""
    added = 0
    for coin, cond_str, direction, sharpe, oos, n in new_edges:
        tf = '1h'
        if tf not in ALL_EDGES:
            ALL_EDGES[tf] = {}
        if coin not in ALL_EDGES[tf]:
            ALL_EDGES[tf][coin] = []
        
        ALL_EDGES[tf][coin].append((cond_str, direction))
        added += 1
        print(f"   + {coin} {direction} {cond_str} (Sharpe={sharpe:.1f}, OOS={oos:.1f}, n={n})")
    
    return added


if __name__ == "__main__":
    main()