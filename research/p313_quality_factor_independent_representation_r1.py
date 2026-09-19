from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
PAIRS={'QUAL':'IVV','SPHQ':'SPY'}; SYMS=list(dict.fromkeys([x for p in PAIRS.items() for x in p])); START='2013-07-18'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna()
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}
results={}; all_pass=True
for q,b in PAIRS.items():
 qr=m[q].copy(); qr.iloc[0]-=COST_BPS/10000
 windows={};
 for name,start in {'2015_plus':'2015-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
  x=qr.loc[start:]; y=m[b].loc[x.index]; xs,ys=stats(x),stats(y); windows[name]={'quality':xs,'matched':ys,'matched_excess_cagr':xs['cagr']-ys['cagr']}
 z=pd.DataFrame({'q':qr,'b':m[b]}).loc['2015-01-01':].dropna(); folds=[stats(p.q)['cagr']-stats(p.b)['cagr'] for p in np.array_split(z,5)]; ok=all(windows[k]['matched_excess_cagr']>0 for k in windows) and sum(v>0 for v in folds)>=3; all_pass &= ok; results[q]={'matched':b,'windows':windows,'fold_excess':folds,'positive_folds':sum(v>0 for v in folds),'passes':ok}
decision='P313_QUALITY_FACTOR_INDEPENDENTLY_SUPPORTED' if all_pass else 'P313_QUALITY_FACTOR_NOT_INDEPENDENTLY_SUPPORTED'
out={'schema':'research.p313_quality_factor_independent_representation_r1','parent':'P313','claim':'Test quality as a distinct factor family using two fixed independent ETF representations, QUAL vs IVV and SPHQ vs SPY, after 10bp entry friction, fixed 2015+/2020+/2022+ windows and five chronology folds. No product/window/parameter rescue.','results':results,'decision_rule':'Support the family only if both representations have positive matched excess CAGR in every fixed window and >=3/5 positive chronology folds. One isolated representation failure narrows transport; broad support requires both.','decision':decision,'limitations':['ETF factor proxies','same adjusted-price provider','no factor-definition tuning','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p313_quality_factor_independent_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
