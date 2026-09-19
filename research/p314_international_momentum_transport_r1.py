from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=['IMTM','IEFA']; START='2015-01-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna(); q=m.IMTM.copy(); q.iloc[0]-=COST_BPS/10000; b=m.IEFA
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}
results={}
for name,start in {'2016_plus':'2016-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
 x=q.loc[start:]; y=b.loc[x.index]; xs,ys=stats(x),stats(y); results[name]={'momentum':xs,'matched':ys,'matched_excess_cagr':xs['cagr']-ys['cagr']}
z=pd.DataFrame({'q':q,'b':b}).loc['2016-01-01':].dropna(); folds=[stats(p.q)['cagr']-stats(p.b)['cagr'] for p in np.array_split(z,5)]; passed=all(results[k]['matched_excess_cagr']>0 for k in results) and sum(x>0 for x in folds)>=3; decision='P314_INTERNATIONAL_MOMENTUM_TRANSPORT_SUPPORTED' if passed else 'P314_INTERNATIONAL_MOMENTUM_TRANSPORT_NOT_SUPPORTED'
out={'schema':'research.p314_international_momentum_transport_r1','parent':'P314','claim':'Orthogonally test geographic transport of the supported US momentum-family thesis using IMTM versus its developed-ex-US IEFA parent after 10bp entry friction, fixed 2016+/2020+/2022+ windows and five chronology folds. No lookback, geography, product, or window search.','cost_bps':COST_BPS,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support geographic transport only if matched excess CAGR is positive in every fixed window and >=3/5 chronology folds are positive. Failure narrows international transport and does not kill supported US momentum survivors.','decision':decision,'limitations':['single international ETF representation','same adjusted-price provider','no parameter/product rescue','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p314_international_momentum_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
