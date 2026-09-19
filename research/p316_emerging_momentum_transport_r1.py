from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=['PIE','EEM']; START='2008-01-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna(); q=m.PIE.copy(); q.iloc[0]-=COST_BPS/10000; b=m.EEM
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}
results={}
for name,start in {'2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
 x=q.loc[start:]; y=b.loc[x.index]; xs,ys=stats(x),stats(y); results[name]={'momentum':xs,'matched':ys,'matched_excess_cagr':xs['cagr']-ys['cagr']}
z=pd.DataFrame({'q':q,'b':b}).loc['2010-01-01':].dropna(); folds=[stats(p.q)['cagr']-stats(p.b)['cagr'] for p in np.array_split(z,5)]; passed=all(results[k]['matched_excess_cagr']>0 for k in results) and sum(x>0 for x in folds)>=3; decision='P316_EMERGING_MOMENTUM_TRANSPORT_SUPPORTED' if passed else 'P316_EMERGING_MOMENTUM_TRANSPORT_NOT_SUPPORTED'
out={'schema':'research.p316_emerging_momentum_transport_r1','parent':'P316','claim':'Orthogonal geography test after P314/P315: PIE versus EEM as a fixed emerging-markets momentum representation, 10bp entry friction, fixed 2010+/2015+/2020+ windows and five chronology folds. No product/lookback/window tuning.','cost_bps':COST_BPS,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support emerging-market transport only if matched excess is positive in every fixed window and >=3/5 chronology folds. Failure narrows geography and does not kill US or P314 IMTM evidence.','decision':decision,'limitations':['single emerging-market momentum representation','same adjusted-price provider','no parameter/product rescue','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p316_emerging_momentum_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
