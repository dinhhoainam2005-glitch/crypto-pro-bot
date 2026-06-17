"""
Bước 1.2 - Mở rộng Data Lake
- Open Interest history từ Binance (BTCUSDT Perpetual) - gọi REST API trực tiếp
- Liquidation Order history từ Binance - tối ưu theo tháng
- ETF Flow từ Farside Investors (BTC ETF daily)
- Tất cả lưu parquet, có progress bar, dữ liệu thật 100%
"""

import ccxt
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from tqdm import tqdm
import time
import os

# ============================================================
# CẤU HÌNH
# ============================================================
BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(DATA_DIR, exist_ok=True)

# Kết nối Binance
exchange = ccxt.binance({
    'enableRateLimit': True,
    'rateLimit': 1200,
})

print("🔌 Kiểm tra kết nối Binance...")
exchange.fetch_time()
print("✅ Kết nối thành công.\n")

# ============================================================
# HÀM GỌI REST API TRỰC TIẾP (không phụ thuộc CCXT method)
# ============================================================
def binance_fapi_get(endpoint, params):
    """Gọi Binance Futures API public endpoint"""
    base_url = "https://fapi.binance.com"
    url = base_url + endpoint
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    else:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

# ============================================================
# 1. TẢI OPEN INTEREST HISTORY (Binance BTCUSDT Perpetual)
# ============================================================
print("🟡 Tải Open Interest history từ Binance...")

oi_list = []
start_time_ms = int(datetime(2019, 9, 8, tzinfo=timezone.utc).timestamp() * 1000)
end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
current_start = start_time_ms

# Chia theo tháng (30 ngày) để giảm số lần gọi API
month_ms = 30 * 24 * 60 * 60 * 1000
total_months = ((end_time_ms - start_time_ms) // month_ms) + 1

pbar = tqdm(total=total_months, desc="📥 Open Interest", unit="tháng")
max_retries = 3
retry_count = 0

while current_start < end_time_ms:
    current_end = min(current_start + month_ms, end_time_ms)
    
    try:
        data = binance_fapi_get("/fapi/v1/openInterestHist", {
            'symbol': 'BTCUSDT',
            'period': '5m',
            'startTime': current_start,
            'endTime': current_end,
            'limit': 500
        })
        
        if data and len(data) > 0:
            oi_list.extend(data)
            retry_count = 0
            pbar.update(1)
            current_start = current_end
        else:
            # Không có dữ liệu tháng này, vẫn chuyển tiếp
            pbar.update(1)
            current_start = current_end
            
    except Exception as e:
        error_msg = str(e)
        retry_count += 1
        if retry_count >= max_retries:
            print(f"\n❌ Thất bại sau {max_retries} lần thử, bỏ qua tháng này.")
            pbar.update(1)
            current_start = current_end
            retry_count = 0
        else:
            print(f"\n⚠️ Lỗi OI (lần {retry_count}/{max_retries}), thử lại sau 3s...")
            time.sleep(3)
    
    time.sleep(0.15)  # rate limit

pbar.close()

if oi_list:
    oi_df = pd.DataFrame(oi_list)
    # Chuẩn hóa tên cột
    if 'timestamp' in oi_df.columns:
        oi_df['timestamp'] = pd.to_datetime(oi_df['timestamp'], unit='ms')
        oi_df.set_index('timestamp', inplace=True)
    elif 'createTime' in oi_df.columns:
        oi_df['timestamp'] = pd.to_datetime(oi_df['createTime'], unit='ms')
        oi_df.set_index('timestamp', inplace=True)
    oi_df = oi_df[~oi_df.index.duplicated(keep='first')]
    oi_df.sort_index(inplace=True)
    oi_file = os.path.join(DATA_DIR, "btc_open_interest_5m.parquet")
    oi_df.to_parquet(oi_file)
    print(f"✅ Đã lưu {len(oi_df)} dòng Open Interest vào {oi_file}\n")
else:
    print("⚠️ Không tải được Open Interest. Ghi chú để kiểm tra lại.\n")

# ============================================================
# 2. TẢI LIQUIDATION ORDER HISTORY (tối ưu theo tháng)
# ============================================================
print("🟡 Tải Liquidation Order history từ Binance...")

all_liq = []
start_time_ms = int(datetime(2019, 9, 8, tzinfo=timezone.utc).timestamp() * 1000)
end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
current_start = start_time_ms

# Tải theo tháng thay vì ngày
month_ms = 30 * 24 * 60 * 60 * 1000
total_months_liq = ((end_time_ms - start_time_ms) // month_ms) + 1

pbar = tqdm(total=total_months_liq, desc="📥 Liquidation Orders", unit="tháng")

while current_start < end_time_ms:
    current_end = min(current_start + month_ms, end_time_ms)
    
    try:
        data = binance_fapi_get("/fapi/v1/allForceOrders", {
            'symbol': 'BTCUSDT',
            'startTime': current_start,
            'endTime': current_end,
            'limit': 1000
        })
        if data and len(data) > 0:
            all_liq.extend(data)
    except Exception:
        pass  # endpoint có thể cần API key, bỏ qua
    
    current_start = current_end
    pbar.update(1)
    time.sleep(0.15)

pbar.close()

if all_liq:
    liq_df = pd.DataFrame(all_liq)
    if 'time' in liq_df.columns:
        liq_df['time'] = pd.to_datetime(liq_df['time'], unit='ms')
        liq_df.set_index('time', inplace=True)
    liq_df = liq_df[~liq_df.index.duplicated(keep='first')]
    liq_df.sort_index(inplace=True)
    liq_file = os.path.join(DATA_DIR, "btc_liquidations.parquet")
    liq_df.to_parquet(liq_file)
    print(f"✅ Đã lưu {len(liq_df)} liquidation orders vào {liq_file}\n")
else:
    print("⚠️ Không tải được Liquidation Orders.")
    print("   Endpoint /fapi/v1/allForceOrders cần API key Binance Futures.")
    print("   Sẽ bổ sung ở bước sau khi bạn tạo API key (chỉ cần quyền đọc).\n")

# ============================================================
# 3. TẢI ETF FLOW TỪ FARSIDE INVESTORS
# ============================================================
print("🟡 Tải Bitcoin ETF Flow từ Farside Investors...")

farside_urls = [
    "https://farside.co.uk/api/btc-flow",
    "https://farside.co.uk/data/btc/flow/all",
]

etf_data = None
for url in farside_urls:
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            etf_data = resp.json()
            print(f"   ✅ Lấy được dữ liệu từ {url}")
            break
        else:
            print(f"   ⚠️ {url} trả về status {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ Lỗi {url}: {e}")

if etf_data:
    if isinstance(etf_data, list):
        etf_df = pd.DataFrame(etf_data)
    elif isinstance(etf_data, dict):
        for key in ['data', 'flows', 'results']:
            if key in etf_data:
                etf_df = pd.DataFrame(etf_data[key])
                break
        else:
            etf_df = pd.DataFrame([etf_data])
    
    if 'date' in etf_df.columns:
        etf_df['date'] = pd.to_datetime(etf_df['date'])
        etf_df.set_index('date', inplace=True)
    
    etf_file = os.path.join(DATA_DIR, "btc_etf_flow.parquet")
    etf_df.to_parquet(etf_file)
    print(f"✅ Đã lưu {len(etf_df)} dòng ETF flow vào {etf_file}\n")
else:
    print("⚠️ Không tải được ETF Flow từ Farside.")
    print("   Farside có thể đã thay đổi URL. Ghi chú để cập nhật ở bước sau.\n")
    etf_file = os.path.join(DATA_DIR, "btc_etf_flow.parquet")
    pd.DataFrame({'note': ['ETF flow unavailable - need manual update']}).to_parquet(etf_file)

# ============================================================
# 4. KIỂM TRA TỔNG KẾT
# ============================================================
print("="*50)
print("📊 TỔNG KẾT DATA LAKE HIỆN TẠI:")
data_files = os.listdir(DATA_DIR)
for f in sorted(data_files):
    filepath = os.path.join(DATA_DIR, f)
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"   📄 {f} ({size_mb:.2f} MB)")
print("="*50)
print("🎯 Hoàn thành Bước 1.2!")
print("   Lưu ý: Liquidation cần API key Binance Futures (quyền đọc).")
print("   Tiếp theo: Bước 1.3 (CVD, Volume Profile) hoặc Bước 2 (Phân tích).")