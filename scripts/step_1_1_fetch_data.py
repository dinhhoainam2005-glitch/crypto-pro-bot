import ccxt
import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import time
import os

# Tạo thư mục nếu chưa có
BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(DATA_DIR, exist_ok=True)

# Kết nối Binance (không cần API key cho public data)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'rateLimit': 1200,  # giữ an toàn
})

print("🔌 Kiểm tra kết nối Binance...")
exchange.fetch_time()
print("✅ Kết nối thành công.\n")

# =========================================================
# 1. TẢI SPOT OHLCV 1H (BTC/USDT) từ 2017-08-17
# =========================================================
symbol_spot = 'BTC/USDT'
timeframe = '1h'
start_date = datetime(2017, 8, 17)
end_date = datetime.now()

def fetch_ohlcv_range(exchange, symbol, timeframe, start, end):
    all_candles = []
    current = start
    total_seconds = (end - start).total_seconds()
    # Progress bar với mốc thời gian
    pbar = tqdm(total=total_seconds, desc=f"📥 Tải {symbol} {timeframe}", unit="s", unit_scale=True)
    
    while current < end:
        since = exchange.parse8601(current.isoformat() + 'Z')
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"\n⚠️ Lỗi tại {current}, thử lại sau 10s: {e}")
            time.sleep(10)
            continue
        
        if not candles:
            break
        
        last_timestamp = candles[-1][0]
        last_date = datetime.utcfromtimestamp(last_timestamp / 1000)
        if last_date <= current:
            # tránh vòng lặp vô hạn nếu không có dữ liệu mới
            break
        
        all_candles.extend(candles)
        current = last_date + timedelta(hours=1)
        pbar.update((last_date - datetime.utcfromtimestamp(candles[0][0]/1000)).total_seconds())
    
    pbar.close()
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    # loại bỏ trùng lặp
    df = df[~df.index.duplicated(keep='first')]
    return df

print("🟡 Bắt đầu tải SPOT BTC/USDT 1h...")
spot_df = fetch_ohlcv_range(exchange, symbol_spot, timeframe, start_date, end_date)
spot_file = os.path.join(DATA_DIR, "btc_spot_1h.parquet")
spot_df.to_parquet(spot_file)
print(f"✅ Đã lưu {len(spot_df)} nến vào {spot_file}\n")

# =========================================================
# 2. TẢI PERPETUAL OHLCV 1H (BTCUSDT) từ 2019-09 (khi ra mắt)
# =========================================================
symbol_perp = 'BTC/USDT:USDT'  # CCXT notation cho perpetual linear
start_perp = datetime(2019, 9, 8)  # approximate launch

print("🟡 Bắt đầu tải PERP BTC/USDT:USDT 1h...")
perp_df = fetch_ohlcv_range(exchange, symbol_perp, timeframe, start_perp, end_date)
perp_file = os.path.join(DATA_DIR, "btc_perp_1h.parquet")
perp_df.to_parquet(perp_file)
print(f"✅ Đã lưu {len(perp_df)} nến vào {perp_file}\n")

# =========================================================
# 3. TẢI FUNDING RATE HISTORY (PERP)
# =========================================================
print("🟡 Tải Funding Rate history...")
funding_list = []
since_funding = exchange.parse8601(start_perp.isoformat() + 'Z')
pbar = tqdm(desc="📥 Funding Rate", unit="lần")
while True:
    try:
        # CCXT có endpoint riêng cho funding rate history
        funding_data = exchange.fetch_funding_rate_history(symbol_perp, since=since_funding, limit=1000)
    except Exception as e:
        print(f"\n⚠️ Lỗi funding rate, thử lại: {e}")
        time.sleep(10)
        continue
    if not funding_data:
        break
    funding_list.extend(funding_data)
    last_funding_time = funding_data[-1]['timestamp']
    since_funding = last_funding_time + 1  # ms
    pbar.update(len(funding_data))
    if len(funding_data) < 1000:
        break
pbar.close()

funding_df = pd.DataFrame(funding_list)
funding_df['timestamp'] = pd.to_datetime(funding_df['timestamp'], unit='ms')
funding_df.set_index('timestamp', inplace=True)
funding_df = funding_df[~funding_df.index.duplicated(keep='first')]
funding_file = os.path.join(DATA_DIR, "btc_funding_1h.parquet")
funding_df.to_parquet(funding_file)
print(f"✅ Đã lưu {len(funding_df)} dòng funding rate vào {funding_file}\n")

print("🎯 Hoàn thành tất cả! Dữ liệu đã sẵn sàng trong thư mục data/raw")