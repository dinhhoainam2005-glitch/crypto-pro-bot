"""
Cập nhật Edge Database + Chuyển sang Edge-002
"""
import json
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
ROBUST_DIR = os.path.join(BASE_DIR, "data", "robustness")

# Load kết quả robustness
with open(os.path.join(ROBUST_DIR, "EDGE-001_robustness.json"), 'r') as f:
    rob = json.load(f)

# Load metadata cũ
with open(os.path.join(EDGE_DIR, "EDGE-001_metadata.json"), 'r') as f:
    meta = json.load(f)

# Cập nhật trạng thái
meta['status'] = 'DEPRECATED'
meta['deprecation_reason'] = (
    'Walk-Forward: 5/12 folds profitable. '
    'OOS 2024-2026: Sharpe -1.36 (edge chết hoàn toàn ngoài mẫu). '
    'Top 5% trades đóng góp 90% lợi nhuận - phụ thuộc vài trade may mắn. '
    'Stress test thất bại trong COVID (-1.1%) và FTX (-4.2%).'
)
meta['robustness_summary'] = rob

with open(os.path.join(EDGE_DIR, "EDGE-001_metadata.json"), 'w') as f:
    json.dump(meta, f, indent=2, default=str)

print("✅ Edge-001 đã được đánh dấu DEPRECATED.")
print(f"   Lý do: {meta['deprecation_reason'][:100]}...")
print("\n📌 Bài học:")
print("   1. Funding rate đơn thuần không đủ để dự đoán đảo chiều")
print("   2. Cần kết hợp thêm OI, CVD để lọc tín hiệu")
print("   3. Edge phải sống được ngoài mẫu 2024-2026 mới dùng được")
print("\n👉 Sẵn sàng cho Edge-002: OI Divergence")