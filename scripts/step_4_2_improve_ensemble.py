"""
CẢI THIỆN ENSEMBLE - TUYỂN THÊM EDGE F,G,H
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = r"D:\@Nam\crypto_pro_bot"
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
EDA_DIR = os.path.join(BASE_DIR, "data", "eda")
ENSEMBLE_DIR = os.path.join(BASE_DIR, "data", "ensemble")
os.makedirs(ENSEMBLE_DIR, exist_ok=True)

print("="*60)
print("🔍 CẢI THIỆN ENSEMBLE - THÊM EDGE F,G,H")
print("="*60)

# LOAD
df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_merged_1h_v2.parquet"))
regime_df = pd.read_parquet(os.path.join(PROCESSED_DIR, "btc_regime_1h.parquet"))
df['regime'] = regime_df['regime']

# ============================================================
# INDICATORS
# ============================================================
df['funding_p1'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 1), raw=True)
df['funding_p5'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 5), raw=True)
df['funding_p10'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 10), raw=True)
df['funding_p95'] = df['funding_rate'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 95), raw=True)
df['cvd_12h'] = df['cvd'].diff(12)
df['cvd_24h'] = df['cvd'].diff(24)
df['oi_24h'] = df['oi'].pct_change(24)
df['price_ma50'] = df['perp_close'].rolling(50).mean()
df['price_chg_24h'] = df['perp_close'].pct_change(24)
df['delta_24h'] = df['delta_volume'].diff(24)
df['vol_ma24'] = df['perp_volume'].rolling(24).mean()
df['vol_p99'] = df['perp_volume'].rolling(500, min_periods=100).apply(lambda x: np.percentile(x, 99), raw=True)

# ============================================================
# 5 EDGE CŨ (A,B,C,D,E)
# ============================================================
df['eA'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
df['eB'] = ((df['funding_rate'] < df['funding_p10']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0)).astype(int)
df['eC'] = ((df['funding_rate'] < df['funding_p5']) & (df['funding_rate'] > 0) & (df['cvd_24h'] < 0) & (df['oi_24h'] > 0)).astype(int)
df['eD'] = ((df['funding_rate'] < df['funding_p5']) & (df['cvd_12h'] < 0) & (df['perp_close'] < df['price_ma50'])).astype(int)
df['eE'] = ((df['funding_rate'] < df['funding_p1']) & (df['cvd_24h'] < 0)).astype(int)

# 3 EDGE MỚI (F,G,H)
df['eF'] = ((df['funding_rate'] > df['funding_p95']) & (df['price_chg_24h'] > 0.02) & (df['funding_rate'] > 0)).astype(int)
df['eG'] = ((df['delta_24h'] > 0) & (df['cvd_24h'] > 0) & (df['perp_volume'] > df['vol_ma24'])).astype(int)
df['eH'] = ((df['funding_rate'] < 0) & (df['perp_volume'] > df['vol_p99'])).astype(int)

for e in ['A','B','C','D','E','F','G','H']:
    print(f"   Edge {e}: {df[f'e{e}'].sum()} tín hiệu")

# ============================================================
# ENSEMBLE
# ============================================================
# Cũ (5 edge)
df['old_votes'] = df['eA'] + df['eB'] + df['eC'] + df['eD'] + df['eE']
df['old_sig'] = (df['old_votes'] >= 2).astype(int).shift(1)

# Mới (8 edge)
df['votes'] = df['eA'] + df['eB'] + df['eC'] + df['eD'] + df['eE'] + df['eF'] + df['eG'] + df['eH']
df['sig'] = (df['votes'] >= 2).astype(int).shift(1)

# Returns
for h in [6, 12, 24]:
    df[f'r{h}'] = (df['perp_close'].shift(-h) - df['perp_open']) / df['perp_open']
    df[f'old_r{h}'] = df[f'r{h}'] * df['old_sig']
    df[f'new_r{h}'] = df[f'r{h}'] * df['sig']

# ============================================================
# SO SÁNH
# ============================================================
print(f"\n📊 SO SÁNH ENSEMBLE CŨ (5 edge) vs MỚI (8 edge) - 12h:")
print(f"   {'Phiên bản':<20} {'n':<6} {'Ret%':<9} {'WR%':<6} {'Sharpe':<8} {'OOS':<8} {'WF':<6} {'Top5%':<7} {'DD%':<8} {'Eq%'}")

for ver, sig_col, ret_col in [('ENSEMBLE CŨ (5)','old_sig','old_r12'), ('ENSEMBLE MỚI (8)','sig','new_r12')]:
    mask = df[sig_col] != 0
    valid = df.loc[mask, ret_col].dropna()
    if len(valid) < 10: continue
    
    avg = valid.mean() * 100
    wr = (valid > 0).sum() / len(valid) * 100
    sh = valid.mean() / valid.std() * np.sqrt(365*2) if valid.std() > 0 else 0
    
    oos = valid[valid.index >= pd.Timestamp('2024-01-01')]
    oos_sh = oos.mean() / oos.std() * np.sqrt(365*2) if len(oos) >= 5 and oos.std() > 0 else -999
    
    nf = 6; d = (valid.index[-1] - valid.index[0]).days // nf
    wf = sum(1 for i in range(nf) if len(v := valid[(valid.index >= valid.index[0] + timedelta(days=i*d)) & (valid.index < valid.index[0] + timedelta(days=(i+1)*d))]) >= 3 and v.mean() > 0)
    
    top5 = valid.nlargest(max(1, int(len(valid)*0.05))).sum() / valid.sum() * 100 if valid.sum() != 0 else 0
    eq = valid.cumsum().iloc[-1] * 100
    md = (valid.cumsum() - valid.cumsum().cummax()).min() * 100
    
    label = ver + (' 👑' if ver.startswith('ENSEMBLE MỚI') else '')
    print(f"   {label:<20} {len(valid):<6} {avg:>+.3f}%  {wr:>5.1f}% {sh:>7.2f} {oos_sh:>7.2f} {f'{wf}/{nf}':>5}  {top5:>5.1f}% {md:>7.2f}% {eq:>+7.2f}%")

# Regime
print(f"\n📊 ENSEMBLE MỚI THEO REGIME:")
ens = df[df['sig'] != 0].dropna(subset=['new_r12'])
for regime in ['uptrend', 'downtrend', 'sideway', 'high_vol', 'low_vol']:
    r = ens[ens['regime'] == regime]['new_r12']
    if len(r) >= 3:
        print(f"   {regime:12s}: Ret={r.mean()*100:+.3f}% | WR={(r>0).sum()/len(r)*100:.1f}% | n={len(r)} {'✅' if r.mean()>0 else '❌'}")

# Lưu
cols = ['sig','old_sig','votes','old_votes','eA','eB','eC','eD','eE','eF','eG','eH',
        'new_r6','new_r12','new_r24','regime']
df[cols].to_parquet(os.path.join(ENSEMBLE_DIR, "ensemble_v2.parquet"))
print(f"\n💾 Đã lưu Ensemble v2")
print(f"🎯 Hoàn thành!")