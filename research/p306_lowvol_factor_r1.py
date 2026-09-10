from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
SYMS=['USMV','VTI','SPLV','SPY']; START='2012-01-01'; END='2026-09-10'
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna()
def cagr(s): return float((1+s.dropna()).prod()**(12/len(s.dropna()))-1)
def dd(s): w=(1+s.dropna()).cumprod(); return float((w/w.cummax()-1).min())
def pair(a,b,start):
 z=m[[a,b]].loc[start:].dropna(); ex=cagr(z[a])-cagr(z[b]); folds=[cagr(p[a])-cagr(p[b]) for p in np.array_split(z,5)]; return {'months':len(z),'factor_cagr':cagr(z[a]),'matched_cagr':cagr(z[b]),'matched_excess_cagr':ex,'factor_max_drawdown':dd(z[a]),'matched_max_drawdown':dd(z[b]),'positive_folds':sum(x>0 for x in folds),'folds':folds}
res={};
for name,a,b in [('USMV_VTI','USMV','VTI'),('SPLV_SPY','SPLV','SPY')]: res[name]={k:pair(a,b,v) for k,v in {'2015_plus':'2015-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items()}
# broad standalone alpha requires both representations positive 2015+/2020+, >=3 folds in 2015+, and no worse drawdown than matched in 2015+
ok=all(res[n]['2015_plus']['matched_excess_cagr']>0 and res[n]['2020_plus']['matched_excess_cagr']>0 and res[n]['2015_plus']['positive_folds']>=3 and res[n]['2015_plus']['factor_max_drawdown']<=res[n]['2015_plus']['matched_max_drawdown'] for n in res); decision='P306_LOWVOL_FACTOR_ALPHA_SUPPORTED' if ok else 'P306_LOWVOL_FACTOR_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p306_lowvol_factor_r1','parent':'P306','claim':'Test a materially different low-volatility equity factor family using two fixed investable representations and matched broad-market controls, without timing, leverage, parameter search, or combination with existing survivors.','results':res,'decision_rule':'Broad low-vol alpha support requires both USMV/VTI and SPLV/SPY to show positive matched excess in 2015+ and 2020+, >=3/5 positive 2015+ folds, and no worse 2015+ drawdown. Otherwise reject broad standalone alpha while preserving any risk-shaping evidence.','decision':decision,'limitations':['same adjusted-price provider','ETF inception/history constrained','scientific factor evidence only','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p306_lowvol_factor_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
