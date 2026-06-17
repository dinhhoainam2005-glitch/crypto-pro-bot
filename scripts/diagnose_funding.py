"""
Chẩn đoán phân phối funding rate
"""
import pandas as pd
import numpy as np
import os

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
df = pd.read_parquet(os.path.join(BASE_DIR, "data", "processed", "btc_merged_1h.parquet"))

fr = df['funding_rate'].dropna()
print(f"Funding Rate thống kê:")
print(f"  Count: {len(fr)}")
print(f"  Mean:  {fr.mean():.6f}")
print(f"  Std:   {fr.std():.6f}")
print(f"  Min:   {fr.min():.6f}")
print(f"  Max:   {fr.max():.6f}")
print(f"  P1:    {np.percentile(fr, 1):.6f}")
print(f"  P5:    {np.percentile(fr, 5):.6f}")
print(f"  P10:   {np.percentile(fr, 10):.6f}")
print(f"  P90:   {np.percentile(fr, 90):.6f}")
print(f"  P95:   {np.percentile(fr, 95):.6f}")
print(f"  P99:   {np.percentile(fr, 99):.6f}")

# In 10 giá trị funding rate cao nhất
print(f"\n10 funding rate CAO nhất:")
top10 = fr.nlargest(10)
for idx, val in top10.items():
    print(f"  {idx}: {val:.6f}")

print(f"\n10 funding rate THẤP nhất:")
bot10 = fr.nsmallest(10)
for idx, val in bot10.items():
    print(f"  {idx}: {val:.6f}")

# Phân phối theo regime
print(f"\nFunding rate theo regime:")
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    mask = df['regime'] == regime
    fr_regime = df.loc[mask, 'funding_rate'].dropna()
    if len(fr_regime) > 0:
        print(f"  {regime:12s}: mean={fr_regime.mean():.6f}, std={fr_regime.std():.6f}, P95={np.percentile(fr_regime, 95):.6f}")