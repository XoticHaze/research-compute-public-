from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=['SPMO','SPY','IJS','IJR','IMTM','IEFA']; START='2015-01-01'; END='2026-09-10'; COST_BPS=25
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna()
W={'SPMO':.25,'IJS':.25,'IMTM':.5}; BW={'SPY':.25,'IJR':.25,'IEFA':.5}
def fixed(weights):
 gross=sum(w*m[s] for s,w in weights.items()); drift={s:w*(1+m[s])/(1+gross) for s,w in weights.items()}; turnover=sum((drift[s]-w).abs() for s,w in weights.items()); return gross-turnover*(COST_BPS/10000)
q=fixed(W); b=fixed(BW)
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}
results={}
for name,start in {'2016_plus':'2016-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
 x=q.loc[start:]; y=b.loc[x.index]; xs,ys=stats(x),stats(y); results[name]={'combined':xs,'matched_composite':ys,'matched_excess_cagr':xs['cagr']-ys['cagr']}
z=pd.DataFrame({'q':q,'b':b}).loc['2016-01-01':].dropna(); folds=[stats(p.q)['cagr']-stats(p.b)['cagr'] for p in np.array_split(z,5)]; passed=all(results[k]['matched_excess_cagr']>0 for k in results) and sum(x>0 for x in folds)>=3; decision='P318_SPMO_SMALLVALUE_IMTM_COMBINATION_SUPPORTED' if passed else 'P318_SPMO_SMALLVALUE_IMTM_COMBINATION_NOT_SUPPORTED'
out={'schema':'research.p318_spmo_smallvalue_imtm_combination_r1','parent':'P318','claim':'Frozen scientific combination of two already-supported sleeves: 50% P304 SPMO+IJS sleeve plus 50% P314 IMTM sleeve, equivalent weights 25% SPMO/25% IJS/50% IMTM, monthly rebalanced at 25bp turnover friction, against exact 25% SPY/25% IJR/50% IEFA matched composite. No weight/window/product search and no allocation authority.','weights':W,'matched_weights':BW,'cost_bps':COST_BPS,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support the fixed combination as scientific evidence only if matched excess CAGR is positive in 2016+, 2020+, 2022+ and >=3/5 chronology folds are positive. Failure preserves component survivor evidence and does not authorize weight rescue.','decision':decision,'limitations':['research-only fixed blend, not portfolio allocation/ranking authority','same adjusted-price provider','P314 is single-representation international transport evidence','no weight/product/window tuning','no product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p318_spmo_smallvalue_imtm_combination_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
