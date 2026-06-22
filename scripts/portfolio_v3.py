"""
PORTFOLIO BACKTEST V3 - MARK-TO-MARKET + CORRELATION CONTROL
"""
import pandas as pd
import numpy as np
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
MULTI_DIR = os.path.join(BASE_DIR, "data", "raw", "multi_coin")

ALL_EDGES = {
    '1d': {
        'BTCUSDT': [('FUND_NEG+PRICE_DOWN', 'LONG'), ('FUND_NEG+TREND_UP', 'LONG'), ('FUND_NEG+CVD_DOWN', 'LONG')],
        'ETHUSDT': [('FUND_NEG+VOL_HIGH', 'SHORT')],
        'LINKUSDT': [('FUND_POS+VOL_HIGH', 'LONG'), ('CVD_DOWN+VOL_HIGH', 'LONG'), ('FUND_NEG+FUND_RISING', 'LONG')],
        'XRPUSDT': [('FUND_POS+VOL_HIGH', 'LONG'), ('CVD_DOWN+VOL_HIGH', 'LONG'), ('VOL_HIGH+TREND_UP', 'LONG')],
        'AVAXUSDT': [('PRICE_UP+TREND_DOWN', 'SHORT')],
    },
    '4h': {
        'BTCUSDT': [('FUND_NEG+VOL_HIGH', 'LONG'), ('FUND_NEG+PRICE_DOWN', 'LONG')],
        'ARBUSDT': [('FUND_NEG+VOL_HIGH', 'LONG')],
        'AVAXUSDT': [('VOL_HIGH+PRICE_DOWN', 'LONG'), ('FUND_RISING+VOL_HIGH', 'LONG')],
        'OPUSDT': [('FUND_NEG+VOL_SPIKE', 'LONG'), ('FUND_RISING+VOL_HIGH', 'LONG')],
        'LINKUSDT': [('FUND_RISING+VOL_HIGH', 'LONG')],
        'XRPUSDT': [('VOL_SPIKE+PRICE_DOWN', 'LONG'), ('VOL_HIGH+PRICE_DOWN', 'LONG')],
    },
}

HORIZONS = {'4h': 6, '1d': 3}
TF_FILES = {'4h': 'perp_4h.parquet', '1d': 'perp_1d.parquet'}
N_PER_DAY = {'4h': 6, '1d': 1}
FEE = 0.001
INITIAL_CAPITAL = 10000
MAX_POSITIONS = 3
RISK_PER_TRADE = 0.10
MAX_CORRELATED = 2  # Tối đa 2 lệnh cùng hướng

# Nhóm tương quan
CORRELATED_GROUPS = [
    ['BTCUSDT', 'ETHUSDT', 'LINKUSDT', 'AVAXUSDT', 'XRPUSDT', 'ARBUSDT', 'OPUSDT'],  # Tất cả altcoin
]

def check_cond(name, df):
    m = {
        'FUND_POS': df['funding_rate'] > 0, 'FUND_NEG': df['funding_rate'] < 0,
        'FUND_RISING': df['funding_rising'] == 1,
        'CVD_UP': df['cvd_up'] == 1, 'CVD_DOWN': df['cvd_down'] == 1,
        'VOL_HIGH': df['vol_high'] == 1, 'VOL_SPIKE': df['vol_spike'] == 1,
        'PRICE_UP': df['price_up'] == 1, 'PRICE_DOWN': df['price_down'] == 1,
        'TREND_UP': df['trend_up'] == 1, 'TREND_DOWN': df['trend_down'] == 1,
    }
    return m.get(name, pd.Series(True, index=df.index))

def load_coin_data(coin, tf):
    file_path = os.path.join(MULTI_DIR, coin, f"{coin}_{TF_FILES[tf]}")
    fund_file = os.path.join(MULTI_DIR, coin, f"{coin}_funding.parquet")
    if not os.path.exists(file_path) or not os.path.exists(fund_file):
        return None
    df = pd.read_parquet(file_path)
    fund = pd.read_parquet(fund_file)
    df = df.sort_index()
    fund = fund.sort_index()
    df = pd.merge_asof(df, fund[['funding_rate']], left_index=True, right_index=True, direction='backward')
    
    n = N_PER_DAY[tf]
    fw = max(100, 5 * n)
    df['funding_rising'] = (df['funding_rate'].diff(max(1, n//6)) > 0).astype(int)
    df['cvd'] = np.cumsum(df['volume'] * (df['close'] - df['open']) / (df['high'] - df['low'] + 0.01))
    df['cvd_chg'] = df['cvd'].diff(n)
    df['cvd_up'] = (df['cvd_chg'] > 0).astype(int)
    df['cvd_down'] = (df['cvd_chg'] < 0).astype(int)
    df['vol_p95'] = df['volume'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 95), raw=True)
    df['vol_p99'] = df['volume'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 99), raw=True)
    df['vol_high'] = (df['volume'] > df['vol_p95']).astype(int)
    df['vol_spike'] = (df['volume'] > df['vol_p99']).astype(int)
    df['price_chg'] = df['close'].pct_change(n)
    df['price_up'] = (df['price_chg'] > 0.02).astype(int)
    df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    df['ma_50'] = df['close'].rolling(fw).mean()
    df['trend_up'] = (df['close'] > df['ma_50']).astype(int)
    df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    return df

def get_events(df, coin, tf, horizon, start, end):
    events = []
    if coin not in ALL_EDGES.get(tf, {}):
        return events
    for cond_str, direction in ALL_EDGES[tf][coin]:
        mask = pd.Series(True, index=df.index)
        for c in cond_str.split('+'):
            mask = mask & check_cond(c, df)
        for et in df.index[mask]:
            if et < pd.Timestamp(start) or et > pd.Timestamp(end): continue
            ei = df.index.get_loc(et) + 1
            if ei >= len(df): continue
            xi = ei + horizon
            if xi >= len(df): continue
            ep = df.iloc[ei]['open']
            xp = df.iloc[xi]['close']
            ret = (xp-ep)/ep-FEE if direction=='LONG' else (ep-xp)/ep-FEE
            if abs(ret) > 0.5: continue
            events.append({
                'time': df.index[ei], 'exit_time': df.index[xi],
                'coin': coin, 'tf': tf, 'edge': cond_str, 'direction': direction,
                'return': ret
            })
    return events

def simulate(events, start, end):
    if not events: return 10000, 10000, 0, 0, []
    df = pd.DataFrame(events).sort_values('time')
    cap = INITIAL_CAPITAL; peak = INITIAL_CAPITAL; pos = []; eq = []
    for d in pd.date_range(start, end, freq='D'):
        # === MARK-TO-MARKET ===
        # Đóng lệnh đến hạn
        pnl = 0; pos2 = []
        for p in pos:
            if p['exit_time'].date() <= d.date():
                pnl += p['pnl']
            else:
                pos2.append(p)
        cap += pnl
        if cap > peak: peak = cap
        pos = pos2
        
        # Mở lệnh mới
        today = df[df['time'].dt.date == d.date()]
        for _, e in today.iterrows():
            if len(pos) >= MAX_POSITIONS: break
            
            # === CORRELATION CONTROL ===
            # Đếm số lệnh cùng direction
            same_dir = sum(1 for p in pos if p['direction'] == e['direction'])
            if same_dir >= MAX_CORRELATED:
                continue
            
            # Đếm số lệnh cùng nhóm
            in_group = 0
            for group in CORRELATED_GROUPS:
                if e['coin'] in group:
                    in_group = sum(1 for p in pos if p['coin'] in group)
            if in_group >= MAX_POSITIONS:  # Cả nhóm không vượt quá max
                continue
            
            pos.append({
                'exit_time': e['exit_time'],
                'pnl': cap * RISK_PER_TRADE * e['return'],
                'direction': e['direction'],
                'coin': e['coin']
            })
        
        eq.append(cap)
    
    eqs = pd.Series(eq, index=pd.date_range(start, end, freq='D'))
    ret = (eqs.iloc[-1]/INITIAL_CAPITAL-1)*100
    dd = (eqs/eqs.cummax()-1).min()*100
    dr = eqs.pct_change().dropna()
    sh = dr.mean()/dr.std()*np.sqrt(365) if dr.std()>0 else 0
    return eqs.iloc[-1], peak, dd, sh, eqs

print("="*60)
print("🧪 PORTFOLIO V3 - MARK-TO-MARKET + CORRELATION")
print("="*60)

all_events = []
for tf in ['1d', '4h']:
    for coin in ALL_EDGES[tf]:
        df = load_coin_data(coin, tf)
        if df is None: continue
        all_events += get_events(df, coin, tf, HORIZONS[tf], '2022-01-01', '2026-06-22')

fc, pk, dd, sh, eqs = simulate(all_events, '2022-01-01', '2026-06-22')
print(f"\n📊 KẾT QUẢ:")
print(f"Return: {((fc/INITIAL_CAPITAL)-1)*100:+.1f}%")
print(f"Max DD: {dd:.1f}%")
print(f"Sharpe: {sh:.2f}")
print(f"Events: {len(all_events)}")
print(f"\n🎯 Hoàn thành!")