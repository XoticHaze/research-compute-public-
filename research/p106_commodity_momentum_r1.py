from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['GLD','SLV','USO','UNG','DBA','DBB']; ALL=U+['SPY']; COSTS=(25,50,100); LB=12; SKIP=1; TOPK=2

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 z={'months':len(q),'controls':{'matched_equal_weight':mt(q.matched),'spy':mt(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q.gross-q.turn*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a.gross-a.turn*bp/10000; fs.append({'fold':j,'matched':cg(x)-cg(a.matched),'spy':cg(x)-cg(a.spy)})
  z['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-z['controls']['matched_equal_weight']['cagr'],'excess_spy':m['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_matched':m['sharpe_rf0']-z['controls']['matched_equal_weight']['sharpe_rf0'],'dd_delta_matched':m['maxdd']-z['controls']['matched_equal_weight']['maxdd'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return z
def main():
 raw=yf.download(ALL,start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev={s:0.0 for s in U}
 for i in range(LB+SKIP,len(m)-1):
  scores={s:float(m[s].iloc[i-SKIP]/m[s].iloc[i-LB]-1) for s in U}; chosen=set(sorted(scores,key=lambda s:(-scores[s],s))[:TOPK]); w={s:(1/TOPK if s in chosen else 0.0) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); rets={s:float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U}; rows.append({'date':m.index[i+1],'gross':sum(w[s]*rets[s] for s in chosen),'turn':turn,'matched':float(np.mean(list(rets.values()))),'spy':float(m['SPY'].iloc[i+1]/m['SPY'].iloc[i]-1)}); prev=w
 f=pd.DataFrame(rows).set_index('date'); tests={k:ev(f.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3
 out={'schema':'research.p106_commodity_momentum_r1','parent':'P106','hypothesis':'A fixed lagged 12-to-1 cross-sectional momentum rank across liquid commodity ETFs creates durable after-cost excess beyond the same commodity universe equal weight.','contract':{'universe':U,'signal':'12-to-1 momentum using data ending t-1','allocation':'monthly top2 equal weight','cost_bps_turnover':list(COSTS),'matched_control':'static equal weight same commodity universe','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P106_COMMODITY_MOMENTUM_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P106_COMMODITY_MOMENTUM_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p106_commodity_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
