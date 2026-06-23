"""
REGIME TEST - 77 EDGES QUA 4 CHU KỲ
"""
import pandas as pd, numpy as np, os

BASE = r'D:\@Nam\crypto_pro_bot'
MULTI = os.path.join(BASE, 'data', 'raw', 'multi_coin')
OI_DIR = os.path.join(BASE, 'data', 'oi_history')
COINS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','ARBUSDT','OPUSDT','LINKUSDT','AVAXUSDT','DOGEUSDT']

HORIZONS = {'15m': 16, '1h': 12, '4h': 6, '1d': 3}
N_PER_DAY = {'15m': 96, '1h': 24, '4h': 6, '1d': 1}
FEE = 0.001
INITIAL_CAPITAL = 10000
MAX_POSITIONS = 3
RISK_PER_TRADE = 0.10

ALL_EDGES = {
    '15m': {
        'BNBUSDT': [('FUND_POS+OI_DOWN','SHORT'),('FUND_NEG+FUND_RISING','SHORT'),('FUND_NEG+PRICE_UP','SHORT'),('FUND_NEG+TREND_UP','SHORT'),('FUND_NEG+OI_UP','SHORT'),('FUND_RISING+TREND_UP','SHORT'),('FUND_RISING+OI_DOWN','SHORT')],
        'BTCUSDT': [('FUND_POS+OI_UP','SHORT'),('FUND_NEG+CVD_UP','SHORT'),('FUND_NEG+PRICE_UP','SHORT'),('FUND_RISING+CVD_UP','SHORT'),('FUND_RISING+PRICE_UP','SHORT'),('FUND_RISING+OI_UP','SHORT'),('CVD_UP+TREND_DOWN','SHORT'),('CVD_UP+OI_UP','SHORT'),('CVD_DOWN+OI_UP','SHORT'),('TREND_DOWN+OI_UP','SHORT')],
        'DOGEUSDT': [('FUND_NEG+PRICE_UP','SHORT')],
        'ETHUSDT': [('FUND_NEG+PRICE_UP','SHORT'),('FUND_RISING+PRICE_UP','SHORT')],
        'LINKUSDT': [('FUND_NEG+CVD_UP','SHORT'),('FUND_NEG+TREND_UP','SHORT')],
        'OPUSDT': [('PRICE_UP+TREND_DOWN','SHORT')],
        'SOLUSDT': [('FUND_NEG+TREND_UP','SHORT'),('PRICE_UP+OI_DOWN','SHORT')],
    },
    '1h': {
        'ARBUSDT': [('CVD_DOWN+PRICE_UP','SHORT')],
        'BTCUSDT': [('FUND_NEG+VOL_HIGH','LONG'),('FUND_NEG+PRICE_DOWN','LONG'),('VOL_SPIKE+PRICE_UP','LONG')],
        'ETHUSDT': [('CVD_UP+VOL_SPIKE','LONG'),('VOL_HIGH+PRICE_UP','LONG'),('VOL_SPIKE+PRICE_UP','LONG')],
        'SOLUSDT': [('VOL_SPIKE+OI_DOWN','LONG')],
    },
    '4h': {
        'ARBUSDT': [('VOL_HIGH+PRICE_DOWN','LONG')],
        'AVAXUSDT': [('FUND_POS+VOL_SPIKE','LONG'),('FUND_NEG+VOL_HIGH','LONG'),('FUND_RISING+VOL_HIGH','LONG'),('CVD_DOWN+VOL_HIGH','LONG'),('VOL_HIGH+PRICE_DOWN','LONG'),('VOL_HIGH+TREND_DOWN','LONG')],
        'BNBUSDT': [('FUND_NEG+PRICE_DOWN','LONG'),('VOL_HIGH+PRICE_DOWN','LONG')],
        'BTCUSDT': [('FUND_NEG+CVD_DOWN','LONG'),('FUND_NEG+VOL_HIGH','LONG'),('FUND_NEG+PRICE_DOWN','LONG')],
        'DOGEUSDT': [('FUND_NEG+VOL_HIGH','LONG'),('FUND_NEG+PRICE_UP','SHORT'),('CVD_DOWN+VOL_HIGH','LONG'),('VOL_HIGH+PRICE_DOWN','LONG'),('VOL_HIGH+TREND_DOWN','LONG'),('VOL_HIGH+OI_DOWN','LONG')],
        'ETHUSDT': [('CVD_UP+VOL_HIGH','LONG'),('VOL_HIGH+PRICE_UP','LONG'),('VOL_HIGH+TREND_UP','LONG'),('VOL_HIGH+OI_DOWN','LONG')],
        'LINKUSDT': [('FUND_NEG+VOL_HIGH','LONG'),('FUND_RISING+VOL_HIGH','LONG'),('CVD_DOWN+VOL_HIGH','LONG'),('VOL_HIGH+PRICE_DOWN','LONG'),('VOL_HIGH+TREND_DOWN','LONG')],
    },
    '1d': {
        'ARBUSDT': [('FUND_RISING+CVD_UP','SHORT'),('FUND_RISING+PRICE_UP','SHORT'),('FUND_RISING+TREND_DOWN','SHORT'),('FUND_RISING+OI_DOWN','SHORT'),('CVD_UP+TREND_DOWN','SHORT'),('CVD_UP+OI_DOWN','SHORT'),('PRICE_DOWN+OI_UP','SHORT')],
        'BNBUSDT': [('FUND_POS+TREND_UP','LONG'),('FUND_NEG+PRICE_DOWN','LONG'),('PRICE_DOWN+TREND_UP','LONG')],
        'BTCUSDT': [('FUND_NEG+CVD_DOWN','LONG'),('PRICE_DOWN+TREND_UP','LONG')],
        'ETHUSDT': [('PRICE_DOWN+TREND_UP','LONG')],
        'LINKUSDT': [('FUND_POS+VOL_HIGH','LONG'),('FUND_NEG+CVD_DOWN','LONG')],
        'XRPUSDT': [('FUND_NEG+PRICE_UP','SHORT')],
    },
}

CONDITIONS = {
    'FUND_POS': lambda d: d['funding_rate'] > 0, 'FUND_NEG': lambda d: d['funding_rate'] < 0,
    'FUND_RISING': lambda d: d['funding_rising'] == 1,
    'CVD_UP': lambda d: d['cvd_up'] == 1, 'CVD_DOWN': lambda d: d['cvd_down'] == 1,
    'VOL_HIGH': lambda d: d['vol_high'] == 1, 'VOL_SPIKE': lambda d: d['vol_spike'] == 1,
    'PRICE_UP': lambda d: d['price_up'] == 1, 'PRICE_DOWN': lambda d: d['price_down'] == 1,
    'TREND_UP': lambda d: d['trend_up'] == 1, 'TREND_DOWN': lambda d: d['trend_down'] == 1,
    'OI_UP': lambda d: d['oi_up'] == 1, 'OI_DOWN': lambda d: d['oi_down'] == 1,
}

def load_coin_data(coin, tf):
    perp = os.path.join(MULTI, coin, f'{coin}_perp_{tf}.parquet')
    fund = os.path.join(MULTI, coin, f'{coin}_funding.parquet')
    if not os.path.exists(perp) or not os.path.exists(fund): return None
    df = pd.read_parquet(perp).sort_index()
    fund_df = pd.read_parquet(fund).sort_index()
    fund_df.index = fund_df.index.astype('datetime64[us]')
    oi_file = os.path.join(OI_DIR, f'{coin}_oi.parquet')
    if os.path.exists(oi_file):
        oi_df = pd.read_parquet(oi_file).sort_index()
        oi_df = oi_df[~oi_df.index.duplicated(keep='last')]
        df.index = df.index.astype('datetime64[us]')
        df = pd.merge_asof(df, oi_df, left_index=True, right_index=True, direction='backward')
        df['oi'] = df['oi'].ffill()
    else: df['oi'] = 50000
    df = pd.merge_asof(df, fund_df[['funding_rate']], left_index=True, right_index=True, direction='backward')
    df['funding_rate'] = df['funding_rate'].ffill()
    n = N_PER_DAY[tf]; fw = max(100, 5*n)
    df['funding_rising'] = (df['funding_rate'].diff(max(1, n//6)) > 0).astype(int)
    df['cvd'] = np.cumsum(df['volume'] * (df['close'] - df['open']) / (df['high'] - df['low'] + 0.01))
    df['cvd_chg'] = df['cvd'].diff(n); df['cvd_up'] = (df['cvd_chg'] > 0).astype(int); df['cvd_down'] = (df['cvd_chg'] < 0).astype(int)
    df['oi_chg'] = df['oi'].pct_change(n); df['oi_up'] = (df['oi_chg'] > 0.01).astype(int); df['oi_down'] = (df['oi_chg'] < -0.01).astype(int)
    df['vol_p95'] = df['volume'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 95), raw=True)
    df['vol_p99'] = df['volume'].rolling(fw, min_periods=20).apply(lambda x: np.percentile(x, 99), raw=True)
    df['vol_high'] = (df['volume'] > df['vol_p95']).astype(int); df['vol_spike'] = (df['volume'] > df['vol_p99']).astype(int)
    df['price_chg'] = df['close'].pct_change(n); df['price_up'] = (df['price_chg'] > 0.02).astype(int); df['price_down'] = (df['price_chg'] < -0.02).astype(int)
    df['ma_50'] = df['close'].rolling(fw).mean(); df['trend_up'] = (df['close'] > df['ma_50']).astype(int); df['trend_down'] = (df['close'] < df['ma_50']).astype(int)
    return df

def get_events(df, coin, tf, horizon, start, end):
    events = []
    if tf not in ALL_EDGES or coin not in ALL_EDGES[tf]: return events
    for cond_str, direction in ALL_EDGES[tf][coin]:
        mask = pd.Series(True, index=df.index)
        for c in cond_str.split('+'): mask = mask & CONDITIONS[c](df)
        d = 1 if direction == 'LONG' else -1
        for et in df.index[mask]:
            if et < pd.Timestamp(start) or et > pd.Timestamp(end): continue
            ei = df.index.get_loc(et) + 1; xi = ei + horizon
            if ei >= len(df) or xi >= len(df): continue
            ep = df.iloc[ei]['open']; xp = df.iloc[xi]['close']
            ret = (xp-ep)/ep-FEE if d==1 else (ep-xp)/ep-FEE
            if abs(ret) > 0.5: continue
            events.append({'time': df.index[ei], 'exit_time': df.index[xi], 'return': ret})
    return events

def simulate(events, start, end):
    if not events: return 10000, 0, 0
    df = pd.DataFrame(events).sort_values('time')
    cap = INITIAL_CAPITAL; peak = INITIAL_CAPITAL; pos = []; eq = []
    for d in pd.date_range(start, end, freq='D'):
        pnl = 0; pos2 = []
        for p in pos:
            if p['exit_time'].date() <= d.date(): pnl += p['pnl']
            else: pos2.append(p)
        cap += pnl
        if cap > peak: peak = cap
        pos = pos2
        for _, e in df[df['time'].dt.date == d.date()].iterrows():
            if len(pos) >= MAX_POSITIONS: break
            pos.append({'exit_time': e['exit_time'], 'pnl': cap*RISK_PER_TRADE*e['return']})
        eq.append(cap)
    eqs = pd.Series(eq, index=pd.date_range(start, end, freq='D'))
    return eqs.iloc[-1], (eqs/eqs.cummax()-1).min()*100, eqs.pct_change().dropna().mean()/eqs.pct_change().dropna().std()*np.sqrt(365) if eqs.pct_change().dropna().std()>0 else 0

REGIMES = [
    ('Bull 2020-2021', '2020-09-01', '2021-11-30'),
    ('Bear 2022', '2022-01-01', '2022-12-31'),
    ('Sideway 2023', '2023-01-01', '2023-12-31'),
    ('Bull 2024-2025', '2024-01-01', '2025-06-30'),
]

print("="*60)
print("🔬 REGIME TEST - 77 EDGES")
print("="*60)
print(f"{'Regime':<20}{'Return':>10}{'DD':>10}{'Sharpe':>10}{'Events':>10}")
print("-"*60)

for name, start, end in REGIMES:
    all_events = []
    for tf in ['15m','1h','4h','1d']:
        for coin in COINS:
            df = load_coin_data(coin, tf)
            if df is None: continue
            all_events += get_events(df, coin, tf, HORIZONS[tf], start, end)
    fc, dd, sh = simulate(all_events, start, end)
    ret = (fc/INITIAL_CAPITAL-1)*100
    print(f"{name:<20}{ret:>+9.1f}%{dd:>9.1f}%{sh:>9.2f}{len(all_events):>10,}")

print(f"\n🎯 Hoàn thành!")