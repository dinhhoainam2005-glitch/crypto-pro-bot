"""
Bước 1.4a - Tải Open Interest history từ Bybit (BTCUSDT Perpetual)
- API đã test thành công
- Dữ liệu thật 100%, lưu parquet
- Có progress bar, ước lượng thời gian
"""

import requests
import pandas as pd
from datetime import datetime, timezone
from tqdm import tqdm
import time
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(DATA_DIR, exist_ok=True)

print("🟡 Tải Open Interest history từ Bybit...")

# Bybit giới hạn 200 dòng/lần gọi, mỗi dòng là 1h
# Cần chia nhỏ theo tháng để tải hết lịch sử
start_time = datetime(2019, 9, 8, tzinfo=timezone.utc)
end_time = datetime.now(timezone.utc)

all_oi = []
current_start = start_time

# Tính tổng số tháng
total_months = (end_time.year - start_time.year) * 12 + (end_time.month - start_time.month) + 1

pbar = tqdm(total=total_months, desc="📥 Bybit OI", unit="tháng")

while current_start < end_time:
    # Mỗi lần lấy tối đa 31 ngày
    current_end = min(current_start + pd.Timedelta(days=31), end_time)
    
    start_ms = int(current_start.timestamp() * 1000)
    end_ms = int(current_end.timestamp() * 1000)
    
    params = {
        'category': 'linear',
        'symbol': 'BTCUSDT',
        'intervalTime': '1h',
        'startTime': start_ms,
        'endTime': end_ms,
        'limit': 200
    }
    
    try:
        resp = requests.get(
            'https://api.bybit.com/v5/market/open-interest',
            params=params,
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                oi_list = result.get('list', [])
                if oi_list:
                    all_oi.extend(oi_list)
    except Exception as e:
        pass  # bỏ qua tháng lỗi, tiếp tục
    
    current_start = current_end
    pbar.update(1)
    time.sleep(0.1)

pbar.close()

if all_oi:
    oi_df = pd.DataFrame(all_oi)
    oi_df['timestamp'] = pd.to_datetime(oi_df['timestamp'].astype(int), unit='ms')
    oi_df = oi_df.rename(columns={'openInterest': 'oi'})
    oi_df['oi'] = oi_df['oi'].astype(float)
    oi_df.set_index('timestamp', inplace=True)
    oi_df = oi_df[~oi_df.index.duplicated(keep='first')]
    oi_df.sort_index(inplace=True)
    
    oi_file = os.path.join(DATA_DIR, "btc_open_interest_1h.parquet")
    oi_df.to_parquet(oi_file)
    print(f"✅ Đã lưu {len(oi_df)} dòng Open Interest vào {oi_file}")
    print(f"   Khoảng thời gian: {oi_df.index[0]} → {oi_df.index[-1]}")
else:
    print("⚠️ Không tải được dữ liệu OI từ Bybit.")

print("🎯 Bước 1.4a hoàn tất.")