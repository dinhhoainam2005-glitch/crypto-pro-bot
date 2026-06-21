"""
TEST BƯỚC 5: OI THẬT TỪ BYBIT
- Kiểm tra OI fetch có hoạt động cho tất cả coin + TF không
- Kiểm tra OI_CHG có thay đổi thật không (không mock 50000)
"""
import requests
import pandas as pd
import numpy as np

print("="*60)
print("🔍 TEST BƯỚC 5: OI THẬT TỪ BYBIT")
print("="*60)

COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
         'ARBUSDT', 'OPUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOGEUSDT']

# ============================================================
# 1. TEST OI FETCH CHO TẤT CẢ COIN
# ============================================================
print("\n📡 1. Fetch OI cho tất cả coin (1h)...")
oi_data = {}
errors = []

for coin in COINS:
    url = f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol={coin}&intervalTime=1h&limit=2"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get('retCode') == 0:
            oi_list = data['result'].get('list', [])
            if oi_list:
                oi_val = float(oi_list[0]['openInterest'])
                oi_data[coin] = oi_val
                print(f"   ✅ {coin}: OI={oi_val:,.0f}")
            else:
                print(f"   ❌ {coin}: list rỗng")
                errors.append(coin)
        else:
            print(f"   ❌ {coin}: retCode={data.get('retCode')}")
            errors.append(coin)
    except Exception as e:
        print(f"   ❌ {coin}: {e}")
        errors.append(coin)

# ============================================================
# 2. TEST OI THAY ĐỔI THẬT (không mock)
# ============================================================
print("\n📡 2. Kiểm tra OI thay đổi thật...")

# Fetch OI history cho BTC
url = "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1h&limit=100"
resp = requests.get(url, timeout=10)
data = resp.json()
oi_list = data['result']['list']

df = pd.DataFrame(oi_list)
df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
df['oi'] = df['openInterest'].astype(float)
df.set_index('timestamp', inplace=True)
df = df.sort_index()

# Tính OI_CHG 24h
df['oi_chg'] = df['oi'].pct_change(24) * 100

print(f"   Số dòng OI: {len(df)}")
print(f"   OI range: {df['oi'].min():,.0f} → {df['oi'].max():,.0f}")
print(f"   OI_CHG mean: {df['oi_chg'].mean():+.2f}%")
print(f"   OI_CHG std: {df['oi_chg'].std():.2f}%")
print(f"   OI_UP (>1%): {(df['oi_chg'] > 1).sum()}/{len(df)} ({(df['oi_chg'] > 1).sum()/len(df)*100:.1f}%)")
print(f"   OI_DOWN (<-1%): {(df['oi_chg'] < -1).sum()}/{len(df)} ({(df['oi_chg'] < -1).sum()/len(df)*100:.1f}%)")

if df['oi_chg'].std() < 0.01:
    print(f"   ❌ OI gần như không đổi! Có thể mock hoặc API lỗi")
    errors.append("OI_NOT_CHANGING")
else:
    print(f"   ✅ OI thay đổi thật, không mock")

# ============================================================
# 3. TEST OI THEO TỪNG TF
# ============================================================
print("\n📡 3. Test OI theo từng TF (BTC)...")
for tf, interval in [('15m', '15min'), ('1h', '1h'), ('4h', '4h'), ('1d', '1d')]:
    url = f"https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime={interval}&limit=2"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get('retCode') == 0:
            oi_list = data['result'].get('list', [])
            if oi_list:
                oi_val = float(oi_list[0]['openInterest'])
                print(f"   ✅ {tf}: OI={oi_val:,.0f}")
            else:
                print(f"   ❌ {tf}: list rỗng")
                errors.append(f"OI_TF_{tf}")
        else:
            print(f"   ❌ {tf}: {data.get('retMsg')}")
            errors.append(f"OI_TF_{tf}")
    except Exception as e:
        print(f"   ❌ {tf}: {e}")
        errors.append(f"OI_TF_{tf}")

# ============================================================
# 4. KẾT LUẬN
# ============================================================
print(f"\n{'='*60}")
print(f"🏆 KẾT QUẢ BƯỚC 5")
print(f"{'='*60}")

if errors:
    print(f"❌ {len(errors)} LỖI:")
    for e in errors:
        print(f"   - {e}")
else:
    print(f"✅ TẤT CẢ OI HOẠT ĐỘNG TỐT!")
    print(f"✅ OI thay đổi thật, không mock")
    print(f"✅ Tất cả TF đều fetch được OI")

print(f"\n🎯 Hoàn thành Bước 5!")