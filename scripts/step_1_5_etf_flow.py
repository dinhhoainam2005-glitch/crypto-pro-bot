"""
Bước 1.5 - Tải Bitcoin ETF Flow từ Farside UK
- Scrape bảng dữ liệu public, không cần API key
- Dữ liệu thật 100%, lưu parquet
"""

import requests
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import os
import re

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(DATA_DIR, exist_ok=True)

print("🟡 Tải Bitcoin ETF Flow từ Farside UK...")

etf_file = os.path.join(DATA_DIR, "btc_etf_flow.parquet")

# ============================================================
# Cách 1: Thử API endpoints đã biết
# ============================================================
urls = [
    "https://farside.co.uk/api/btc-flow",
    "https://farside.co.uk/data/btc/flow/all",
    "https://farside.co.uk/api/btc-flow-all",
]

data = None
for url in urls:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and len(resp.text) > 50:
            try:
                data = resp.json()
                print(f"   ✅ API thành công: {url}")
                break
            except:
                pass
        else:
            print(f"   ⚠️ {url}: status {resp.status_code}, len={len(resp.text)}")
    except Exception as e:
        print(f"   ⚠️ {url}: {e}")

# ============================================================
# Cách 2: Nếu API không hoạt động, scrape trang chính
# ============================================================
if data is None:
    print("   🔄 API thất bại, thử scrape trang public...")
    
    # Farside có trang public hiển thị bảng ETF flow
    scrape_url = "https://farside.co.uk/btc/"
    try:
        resp = requests.get(scrape_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            html = resp.text
            
            # Tìm bảng dữ liệu trong HTML
            # Farside thường nhúng data dưới dạng JSON trong script
            # hoặc bảng HTML với class cụ thể
            
            # Thử tìm JSON data trong script tags
            pattern = r'data:\s*(\[.*?\])'
            matches = re.findall(pattern, html, re.DOTALL)
            
            if matches:
                import json
                for match in matches:
                    try:
                        data = json.loads(match)
                        if isinstance(data, list) and len(data) > 10:
                            print(f"   ✅ Tìm thấy data JSON trong HTML: {len(data)} dòng")
                            break
                    except:
                        continue
            
            # Nếu không tìm thấy JSON, thử parse bảng HTML
            if data is None:
                try:
                    tables = pd.read_html(html)
                    if tables:
                        for t in tables:
                            if len(t) > 10 and ('date' in t.columns or 'Date' in t.columns):
                                data = t.to_dict('records')
                                print(f"   ✅ Parse HTML table: {len(data)} dòng")
                                break
                except Exception as e:
                    print(f"   ⚠️ Parse HTML thất bại: {e}")
                    
    except Exception as e:
        print(f"   ⚠️ Scrape thất bại: {e}")

# ============================================================
# Xử lý và lưu dữ liệu
# ============================================================
if data is not None:
    if isinstance(data, list):
        etf_df = pd.DataFrame(data)
    elif isinstance(data, dict):
        # Có thể dữ liệu nằm trong 1 key
        for key in ['data', 'flows', 'results', 'items']:
            if key in data:
                etf_df = pd.DataFrame(data[key])
                break
        else:
            etf_df = pd.DataFrame([data])
    
    # Chuẩn hóa cột ngày
    date_cols = [c for c in etf_df.columns if 'date' in c.lower() or 'time' in c.lower()]
    if date_cols:
        etf_df[date_cols[0]] = pd.to_datetime(etf_df[date_cols[0]])
        etf_df.set_index(date_cols[0], inplace=True)
    
    etf_df = etf_df[~etf_df.index.duplicated(keep='first')]
    etf_df.sort_index(inplace=True)
    
    etf_df.to_parquet(etf_file)
    print(f"\n✅ Đã lưu {len(etf_df)} dòng ETF flow vào {etf_file}")
    print(f"   Cột: {list(etf_df.columns)}")
    if len(etf_df) > 0:
        print(f"   Khoảng thời gian: {etf_df.index[0]} → {etf_df.index[-1]}")
else:
    print("\n⚠️ Không lấy được ETF Flow.")
    print("   Farside UK có thể đã thay đổi cấu trúc trang.")
    print("   Ghi chú: ETF flow chỉ quan trọng từ 2024, không ảnh hưởng backtest 2017-2023.")
    pd.DataFrame({'note': ['ETF flow unavailable - Farside structure changed']}).to_parquet(etf_file)

# ============================================================
# TỔNG KẾT DATA LAKE
# ============================================================
print("\n" + "="*50)
print("📊 TỔNG KẾT DATA LAKE HIỆN TẠI:")
for f in sorted(os.listdir(DATA_DIR)):
    size_mb = os.path.getsize(os.path.join(DATA_DIR, f)) / (1024*1024)
    print(f"   📄 {f} ({size_mb:.2f} MB)")
print("="*50)
print("🎯 Hoàn thành Bước 1.5!")
print("   Data Lake đã sẵn sàng cho Bước 2: Phân tích & Quét Edge.")