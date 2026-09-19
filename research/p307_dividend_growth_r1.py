from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
SYMS=['VIG','VTI','DGRO','ITOT']; START='2015-01-01'; END='2026-09-10'
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna()
def cagr(s): return float((1+s.dropna()).prod()**(12/len(s.dropna()))-1)
def dd(s): w=(1+s.dropna()).cumprod(); return float((w/w.cummax()-1).min())
def pair(a,b,start):
 z=m[[a,b]].loc[start:].dropna(); folds=[cagr(p[a])-cagr(p[b]) for p in np.array_split(z,5)]; return {'months':len(z),'factor_cagr':cagr(z[a]),'matched_cagr':cagr(z[b]),'matched_excess_cagr':cagr(z[a])-cagr(z[b]),'factor_max_drawdown':dd(z[a]),'matched_max_drawdown':dd(z[b]),'positive_folds':sum(x>0 for x in folds),'folds':folds}
res={n:{k:pair(a,b,v) for k,v in {'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items()} for n,a,b in [('VIG_VTI','VIG','VTI'),('DGRO_ITOT','DGRO','ITOT')]}; ok=all(res[n]['2017_plus']['matched_excess_cagr']>0 and res[n]['2020_plus']['matched_excess_cagr']>0 and res[n]['2017_plus']['positive_folds']>=3 for n in res); decision='P307_DIVIDEND_GROWTH_ALPHA_SUPPORTED' if ok else 'P307_DIVIDEND_GROWTH_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p307_dividend_growth_r1','parent':'P307','claim':'Test a new dividend-growth/profitability-selection fund family with two fixed investable representations against broad-market matched controls, without timing, leverage, parameter search, or combination with existing survivors.','results':res,'decision_rule':'Broad support requires both VIG/VTI and DGRO/ITOT positive matched excess in 2017+ and 2020+ with >=3/5 positive 2017+ folds.','decision':decision,'limitations':['DGRO history begins 2014','same adjusted-price provider','scientific family evidence only','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p307_dividend_growth_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
