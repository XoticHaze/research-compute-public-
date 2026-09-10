from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
PAIRS={'OMFL_IWB':('OMFL','IWB'),'OMFS_IJR':('OMFS','IJR')}; SYMS=sorted({s for p in PAIRS.values() for s in p}); START='2017-11-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS]
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}
def eval_pair(qsym,bsym):
 p=px[[qsym,bsym]].dropna().resample('ME').last().pct_change().dropna(); q=p[qsym].copy(); q.iloc[0]-=COST_BPS/10000; b=p[bsym]; results={}
 for name,start in {'2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
  z=pd.DataFrame({'q':q,'b':b}).loc[start:].dropna(); qs,bs=stats(z.q),stats(z.b); results[name]={'model':qs,'matched':bs,'matched_excess_cagr':qs['cagr']-bs['cagr']}
 z=pd.DataFrame({'q':q,'b':b}).loc['2018-01-01':].dropna(); folds=[stats(f.q)['cagr']-stats(f.b)['cagr'] for f in np.array_split(z,5)]; passed=all(v['matched_excess_cagr']>0 for v in results.values()) and sum(x>0 for x in folds)>=3
 return {'model':qsym,'matched':bsym,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'passed':passed}
pairs={k:eval_pair(*v) for k,v in PAIRS.items()}; passes=sum(v['passed'] for v in pairs.values()); decision='P323_DYNAMIC_MULTIFACTOR_FAMILY_SUPPORTED' if passes==2 else ('P323_DYNAMIC_MULTIFACTOR_REPRESENTATION_CONDITIONAL' if passes==1 else 'P323_DYNAMIC_MULTIFACTOR_NOT_SUPPORTED')
out={'schema':'research.p323_dynamic_multifactor_r1','parent':'P323','claim':'Test a materially distinct dynamic multifactor/regime-selection architecture in two predeclared size universes using OMFL vs IWB and OMFS vs IJR after 10bp entry friction, fixed 2018+/2020+/2022+ windows, and five chronology folds. No product, factor, regime, or window search.','cost_bps':COST_BPS,'pairs':pairs,'decision_rule':'Broad support requires both representations to have positive matched excess CAGR in every fixed window and >=3/5 positive chronology folds. One pass is representation-conditional only; two failures close this fixed dynamic-multifactor architecture without parameter or product rescue.','decision':decision,'limitations':['ETF methodology proxy, not reconstruction of provider regime model','two representations share a provider family','same adjusted-price provider','no factor/regime/product/window rescue','no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p323_dynamic_multifactor_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))