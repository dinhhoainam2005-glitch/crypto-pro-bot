"""
ENSEMBLE SIGNAL ENGINE v1.0
- Kết hợp 5 edge thành viên (A,B,C,D,E)
- Bỏ phiếu ≥ 2 → LONG
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tqdm import tqdm
import os
import json
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDGE_DIR = os.path.join(BASE_DIR, "data", "edges")
ENSEMBLE_DIR = os.path.join(BASE_DIR, "data", "ensemble")
os.makedirs(EDGE_DIR, exist_ok=True)
os.makedirs(ENSEMBLE_DIR, exist_ok=True)

# ============================================================
# 1. LOAD
# ============================================================
print("="*60)
print("🔧 ENSEMBLE SIGNAL ENGINE v1.0")
print("="*60)

df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']
print(f"📥 {len(df)} nến")

# ============================================================
# 2. INDICATORS
# ============================================================
df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 1), raw=True)
df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)
df['funding_p10'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 10), raw=True)
df['cvd_12h'] = df['cvd'].diff(12)
df['cvd_24h'] = df['cvd'].diff(24)
df['oi_24h'] = df['oi'].pct_change(24)
df['price_ma50'] = df['perp_close'].rolling(50).mean()

# ============================================================
# 3. 5 EDGE THÀNH VIÊN
# ============================================================
# A: FUND_P5 + POS + CVD_24h < 0
df['eA'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
# B: FUND_P10 + POS + CVD_24h < 0
df['eB'] = ((df['funding_rate'] < df['funding_p10']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
# C: FUND_P5 + POS + CVD_24h < 0 + OI > 0
df['eC'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0) & (df['oi_24h'] > 0)).astype(int)
# D: FUND_P5 + CVD_12h < 0 + Price < MA50
df['eD'] = ((df['funding_rate'] < df['funding_p5']) & (df['cvd_12h'] < 0) & (df['perp_close'] < df['price_ma50'])).astype(int)
# E: FUND_P1 + CVD_24h < 0
df['eE'] = ((df['funding_rate'] < df['funding_p1']) & (df['cvd_24h'] < 0)).astype(int)

# In số tín hiệu
for e in ['A','B','C','D','E']:
    print(f"   Edge {e}: {df[f'e{e}'].sum()} tín hiệu")

# ============================================================
# 4. ENSEMBLE VOTING
# ============================================================
df['votes'] = df['eA'] + df['eB'] + df['eC'] + df['eD'] + df['eE']
df['sig_raw'] = (df['votes'] >= 2).astype(int)
df['sig'] = df['sig_raw'].shift(1)

# Từng edge shift
for e in ['A','B','C','D','E']:
    df[f's{e}'] = df[f'e{e}'].shift(1)

# ============================================================
# 5. RETURNS
# ============================================================
for h in [6, 12, 24]:
    df[f'r{h}'] = (df['perp_close'].shift(-h) - df['perp_open']) / df['perp_open']
    df[f'ens_r{h}'] = df[f'r{h}'] * df['sig']
    for e in ['A','B','C','D','E']:
        df[f'{e}_r{h}'] = df[f'r{h}'] * df[f's{e}']

# ============================================================
# 6. SO SÁNH
# ============================================================
print(f"\n📊 SO SÁNH (12h):")
print(f"   {'Edge':<18} {'n':<6} {'Ret%':<9} {'WR%':<6} {'Sharpe':<8} {'OOS':<8} {'WF':<6} {'Top5%':<7} {'DD%':<8} {'Eq%'}")
print(f"   {'-'*85}")

best = None
for label, prefix in [('ENSEMBLE','ens'), ('Edge A','A'), ('Edge B','B'), 
                       ('Edge C','C'), ('Edge D','D'), ('Edge E','E')]:
    col = f'{prefix}_r12'
    valid = df[df[f's{prefix[-1]}' if prefix != 'ens' else 'sig'] != 0][col].dropna() if prefix != 'ens' else df[df['sig'] != 0]['ens_r12'].dropna()
    
    if prefix != 'ens':
        s_col = f's{prefix[-1]}' if len(prefix) == 6 else f's{prefix[-1]}'
        mask = df[s_col] != 0
    else:
        mask = df['sig'] != 0
    valid = df.loc[mask, col].dropna()
    
    if len(valid) < 10:
        continue
    
    avg = valid.mean() * 100
    wr = (valid > 0).sum() / len(valid) * 100
    sh = valid.mean() / valid.std() * np.sqrt(365*2) if valid.std() > 0 else 0
    
    oos = valid[valid.index >= pd.Timestamp('2024-01-01')]
    oos_sh = oos.mean() / oos.std() * np.sqrt(365*2) if len(oos) >= 5 and oos.std() > 0 else -999
    
    nf = 6
    dd = (valid.index[-1] - valid.index[0]).days // nf
    wf = sum(1 for i in range(nf) if len(v := valid[(valid.index >= valid.index[0] + timedelta(days=i*dd)) & (valid.index < valid.index[0] + timedelta(days=(i+1)*dd))]) >= 3 and v.mean() > 0)
    
    top5 = valid.nlargest(max(1, int(len(valid)*0.05))).sum() / valid.sum() * 100 if valid.sum() != 0 else 0
    eq = valid.cumsum().iloc[-1] * 100
    md = (valid.cumsum() - valid.cumsum().cummax()).min() * 100
    
    row = {'name': label, 'n': len(valid), 'avg': round(avg,3), 'wr': round(wr,1), 'sh': round(sh,2), 
           'oos': round(oos_sh,2), 'wf': f'{wf}/{nf}', 'top5': round(top5,1), 'dd': round(md,2), 'eq': round(eq,2)}
    
    if label == 'ENSEMBLE':
        best = row
        label += ' 👑'
    
    print(f"   {label:<18} {row['n']:<6} {row['avg']:>+.3f}%  {row['wr']:>5.1f}% {row['sh']:>7.2f} {row['oos']:>7.2f} {row['wf']:>5}  {row['top5']:>5.1f}% {row['dd']:>7.2f}% {row['eq']:>+7.2f}%")

# ============================================================
# 7. REGIME
# ============================================================
print(f"\n📊 ENSEMBLE THEO REGIME:")
ens = df[df['sig'] != 0].dropna(subset=['ens_r12'])
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    r = ens[ens['regime'] == regime]['ens_r12']
    if len(r) >= 3:
        print(f"   {regime:12s}: Ret={r.mean()*100:+.3f}% | WR={(r>0).sum()/len(r)*100:.1f}% | n={len(r)} {'✅' if r.mean()>0 else '❌'}")

# ============================================================
# 8. KẾT LUẬN
# ============================================================
print(f"\n🏆 KẾT LUẬN:")
if best:
    print(f"   Số tín hiệu: {best['n']}")
    print(f"   Sharpe: {best['sh']:.2f}")
    print(f"   OOS Sharpe: {best['oos']:.2f}")
    print(f"   Walk-Forward: {best['wf']}")
    print(f"   Top 5%: {best['top5']}%")
    print(f"   Max DD: {best['dd']}%")
    print(f"   Equity: {best['eq']}%")

# Lưu
cols = ['sig', 'votes', 'eA', 'eB', 'eC', 'eD', 'eE', 'ens_r6', 'ens_r12', 'ens_r24', 'regime']
df[cols].to_parquet(os.path.join(ENSEMBLE_DIR, "ensemble_v1.parquet"))
print(f"\n💾 Đã lưu Ensemble v1.0")
print(f"🎯 Hoàn thành!")