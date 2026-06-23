"""
BẢNG CHI TIẾT TỪNG EDGE 77 - ĐÚNG FORMAT
"""
import pandas as pd, numpy as np, os

BASE = r'D:\@Nam\crypto_pro_bot'
MULTI = os.path.join(BASE, 'data', 'raw', 'multi_coin')
OI_DIR = os.path.join(BASE, 'data', 'oi_history')
COINS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','ARBUSDT','OPUSDT','LINKUSDT','AVAXUSDT','DOGEUSDT']

HORIZONS = {'15m': 16, '1h': 12, '4h': 6, '1d': 3}
N_PER_DAY = {'15m': 96, '1h': 24, '4h': 6, '1d': 1}
FEE = 0.001

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

print("=" * 95)
print("📊 CHI TIẾT 77 EDGES - V4.5 OI THẬT")
print("=" * 95)

for tf in ['15m', '1h', '4h', '1d']:
    print(f"\n⏱️ {tf}:")
    print(f"{'Coin':<10}{'Dir':<7}{'Edge':<30}{'n':>6}{'Ret%':>8}{'WR%':>6}{'Sharpe':>8}")
    print("-" * 75)
    for coin in COINS:
        df = load_coin_data(coin, tf)
        if df is None: continue
        if tf not in ALL_EDGES or coin not in ALL_EDGES[tf]: continue
        h = HORIZONS[tf]
        for cond_str, direction in ALL_EDGES[tf][coin]:
            mask = pd.Series(True, index=df.index)
            for c in cond_str.split('+'): mask = mask & CONDITIONS[c](df)
            d = 1 if direction == 'LONG' else -1
            signal = mask.astype(int) * d
            ret = (df['close'].shift(-h) - df['open']) / df['open'] - FEE
            valid = (ret * signal.shift(1))[signal.shift(1) != 0].dropna()
            sh = valid.mean()/valid.std()*np.sqrt(365*24/h) if valid.std()>0 else 0
            print(f"{coin:<10}{direction:<7}{cond_str:<30}{len(valid):>6}{valid.mean()*100:>+7.2f}%{(valid>0).sum()/len(valid)*100:>5.0f}%{sh:>8.1f}")

print(f"\n🎯 Hoàn thành!")