from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
MA=200; COSTS=(5,10,25)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 ex=float(q['exp'].mean()); matched=q['gld']*ex; out={'days':len(q),'avg_exposure':ex,'controls':{'exposure_matched_gld':mt(matched),'full_gld':mt(q['gld']),'spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; z=a['gld']*ex; fs.append({'fold':j,'matched':cg(x)-cg(z),'full_gld':cg(x)-cg(a['gld'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_gld']['cagr'],'excess_full_gld':m['cagr']-out['controls']['full_gld']['cagr'],'excess_spy':m['cagr']-out['controls']['spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_full_gld_folds':sum(x['full_gld']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(['GLD','SPY'],start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); g=raw['GLD']; r=g.pct_change(fill_method=None); spy=raw['SPY'].pct_change(fill_method=None); ma=g.rolling(MA).mean(); exp=(g.shift(1)>ma.shift(1)).astype(float); prev=exp.shift(1).fillna(0); q=pd.DataFrame({'gross':exp*r,'turn':(exp-prev).abs(),'gld':r,'spy':spy,'exp':exp}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['10']; b=tests['2020']['costs']['10']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3
 out={'schema':'research.p111_gld_trend_filter_r1','parent':'P111','hypothesis':'A fixed causal 200-session trend filter on GLD creates after-cost risk-timing value beyond static GLD at identical average capital usage.','contract':{'asset':'GLD','trend_rule':'prior close above prior 200-session simple moving average','cost_bps_per_position_change':list(COSTS),'matched_control':'continuous GLD scaled to candidate average exposure','opportunity_controls':['full GLD','SPY'],'windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(raw.index[-1].date()),'panel_sha256':hashlib.sha256(raw.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P111_GLD_TREND_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P111_GLD_TREND_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p111_gld_trend_filter_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
