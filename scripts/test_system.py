"""
TEST TOÀN BỘ HỆ THỐNG - TỪNG THÀNH PHẦN
Chạy 1 lần biết ngay lỗi ở đâu
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

print("="*60)
print("🔍 TEST HỆ THỐNG - TỪNG THÀNH PHẦN")
print("="*60)

errors = []

# ============================================================
# 1. TEST FETCH KLINES
# ============================================================
print("\n📡 1. FETCH KLINES")
for tf, interval in [('15m', '15m'), ('1h', '1h'), ('4h', '4h'), ('1d', '1d')]:
    for coin in ['BTCUSDT', 'ETHUSDT']:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}&interval={interval}&limit=1500"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if isinstance(data, list) and len(data) > 100:
                print(f"   ✅ {coin} {tf}: {len(data)} nến")
            else:
                print(f"   ❌ {coin} {tf}: {len(data) if isinstance(data, list) else type(data)} nến")
                errors.append(f"FETCH: {coin} {tf} - {len(data) if isinstance(data, list) else 'not list'}")
        except Exception as e:
            print(f"   ❌ {coin} {tf}: {e}")
            errors.append(f"FETCH: {coin} {tf} - {e}")

# ============================================================
# 2. TEST FUNDING RATE
# ============================================================
print("\n💰 2. FUNDING RATE")
for coin in ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT']:
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}&limit=1"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            fr = float(data[0]['fundingRate'])
            print(f"   ✅ {coin}: {fr*100:.4f}%")
        else:
            print(f"   ❌ {coin}: {data}")
            errors.append(f"FUNDING: {coin} - {data}")
    except Exception as e:
        print(f"   ❌ {coin}: {e}")
        errors.append(f"FUNDING: {coin} - {e}")

# ============================================================
# 3. TEST OI BYBIT
# ============================================================
print("\n📊 3. OPEN INTEREST (BYBIT)")
for tf, interval in [('15m', '15min'), ('1h', '1h'), ('1d', '1d')]:
    url = f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime={interval}&limit=2"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get('retCode') == 0:
            oi_list = data['result'].get('list', [])
            if oi_list:
                oi_val = float(oi_list[0]['openInterest'])
                print(f"   ✅ BTC {tf}: OI={oi_val:,.0f}")
            else:
                print(f"   ❌ BTC {tf}: list rỗng")
                errors.append(f"OI: BTC {tf} - empty list")
        else:
            print(f"   ❌ BTC {tf}: {data}")
            errors.append(f"OI: BTC {tf} - {data}")
    except Exception as e:
        print(f"   ❌ BTC {tf}: {e}")
        errors.append(f"OI: BTC {tf} - {e}")

# ============================================================
# 4. TEST INDICATORS (BTC 1h)
# ============================================================
print("\n🔧 4. INDICATORS (BTC 1h)")
url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=1500"
resp = requests.get(url, timeout=10)
df = pd.DataFrame(resp.json(), columns=['t','o','h','l','c','v','x','q','n','tb','tq','i'])
for col in ['o','h','l','c','v']:
    df[col] = df[col].astype(float)

# Tính indicators giống bot
df['funding_rate'] = 0.0001
df['oi'] = 50000
n_per_day = 24
fw = max(100, 5 * n_per_day)
min_p = max(20, n_per_day)
cvd_lb = n_per_day

df['funding_p5'] = df['funding_rate'].rolling(fw, min_periods=min_p).apply(lambda x: np.percentile(x, 5), raw=True)
df['funding_p95'] = df['funding_rate'].rolling(fw, min_periods=min_p).apply(lambda x: np.percentile(x, 95), raw=True)
df['funding_p99'] = df['funding_rate'].rolling(fw, min_periods=min_p).apply(lambda x: np.percentile(x, 99), raw=True)
df['funding_rising'] = (df['funding_rate'].diff(max(1, n_per_day//6)) > 0).astype(int)
df['funding_pos'] = (df['funding_rate'] > 0).astype(int)
df['funding_neg'] = (df['funding_rate'] < 0).astype(int)

df['cvd'] = (df['v'] * (df['c'] - df['o']) / (df['h'] - df['l'] + 0.01)).cumsum()
df['cvd_chg'] = df['cvd'].diff(cvd_lb)
df['cvd_up'] = (df['cvd_chg'] > 0).astype(int)
df['cvd_down'] = (df['cvd_chg'] < 0).astype(int)

df['oi_chg'] = df['oi'].pct_change(cvd_lb)
df['oi_up'] = (df['oi_chg'] > 0.01).astype(int)
df['oi_down'] = (df['oi_chg'] < -0.01).astype(int)

df['vol_p95'] = df['v'].rolling(fw, min_periods=min_p).apply(lambda x: np.percentile(x, 95), raw=True)
df['vol_p99'] = df['v'].rolling(fw, min_periods=min_p).apply(lambda x: np.percentile(x, 99), raw=True)
df['vol_high'] = (df['v'] > df['vol_p95']).astype(int)

df['price_chg'] = df['c'].pct_change(cvd_lb)
df['price_up'] = (df['price_chg'] > 0.02).astype(int)
df['price_down'] = (df['price_chg'] < -0.02).astype(int)

df['ma_50'] = df['c'].rolling(fw).mean()
df['trend_up'] = (df['c'] > df['ma_50']).astype(int)
df['trend_down'] = (df['c'] < df['ma_50']).astype(int)

# Check NaN
nan_cols = [c for c in df.columns if df[c].isna().sum() > len(df)*0.5]
if nan_cols:
    print(f"   ❌ Nhiều NaN: {nan_cols}")
    errors.append(f"INDICATORS: NaN in {nan_cols}")
else:
    print(f"   ✅ Indicators OK - {len(df.dropna())}/{len(df)} nến sạch")

# ============================================================
# 5. TEST EDGE KÍCH HOẠT (BTC 1h)
# ============================================================
print("\n🎯 5. EDGE TEST (BTC 1h)")

latest = df.iloc[-1]
edges_test = {
    'BTC_FUND_P99': latest['funding_rate'] > latest['funding_p99'],
    'BTC_CVD_DOWN': latest['cvd_down'] == 1,
    'BTC_PRICE_DOWN': latest['price_down'] == 1,
    'BTC_TREND_DOWN': latest['trend_down'] == 1,
    'BTC_FUND_RISING': latest['funding_rising'] == 1,
    'BTC_VOL_HIGH': latest['vol_high'] == 1,
}

for name, result in edges_test.items():
    status = '✅' if result else '❌'
    print(f"   {status} {name}")

active = sum(edges_test.values())
print(f"   Điều kiện đang active: {active}/6")

# Test edge cụ thể
edge1 = latest['funding_p99'] if not pd.isna(latest['funding_p99']) else 'NaN'
edge2 = latest['funding_p5'] if not pd.isna(latest['funding_p5']) else 'NaN'
print(f"   FUND_P99: {edge1}, FUND_P5: {edge2}")

# ============================================================
# 6. TỔNG KẾT
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 KẾT QUẢ TEST")
print(f"{'='*60}")

if errors:
    print(f"❌ {len(errors)} LỖI TÌM THẤY:")
    for e in errors:
        print(f"   - {e}")
else:
    print(f"✅ TẤT CẢ THÀNH PHẦN HOẠT ĐỘNG TỐT!")

print(f"\n🎯 Hoàn thành!")