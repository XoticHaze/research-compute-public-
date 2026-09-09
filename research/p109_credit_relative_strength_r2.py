from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['HYG','LQD']; ALL=U+['AGG','SPY']; COSTS=(10,25,50); LB=6; SKIP=1

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 z={'months':len(q),'controls':{'matched_50_50_credit':mt(q['matched']),'agg':mt(q['agg']),'spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; fs.append({'fold':j,'matched':cg(x)-cg(a['matched']),'agg':cg(x)-cg(a['agg'])})
  z['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-z['controls']['matched_50_50_credit']['cagr'],'excess_agg':m['cagr']-z['controls']['agg']['cagr'],'excess_spy':m['cagr']-z['controls']['spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_agg_folds':sum(x['agg']>0 for x in fs),'folds':fs}
 return z
def main():
 raw=yf.download(ALL,start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.zeros(2)
 for i in range(LB+SKIP,len(m)-1):
  score=np.array([float(m[s].iloc[i-SKIP]/m[s].iloc[i-LB]-1) for s in U]); k=int(np.argmax(score)); w=np.zeros(2); w[k]=1.; r=np.array([float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U]); turn=float(.5*np.abs(w-prev).sum()); rows.append({'date':m.index[i+1],'gross':float(w@r),'turn':turn,'matched':float(r.mean()),'agg':float(m['AGG'].iloc[i+1]/m['AGG'].iloc[i]-1),'spy':float(m['SPY'].iloc[i+1]/m['SPY'].iloc[i]-1),'chosen':U[k]}); prev=w
 f=pd.DataFrame(rows).set_index('date'); tests={k:ev(f.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['25']; b=tests['2020']['costs']['25']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['excess_agg']>0
 out={'schema':'research.p109_credit_relative_strength_r2','parent':'P109','hypothesis':'A fixed lagged six-month relative-strength switch between high-yield and investment-grade credit creates durable after-cost excess beyond static credit diversification and aggregate bonds.','contract':{'universe':U,'signal':'six-month relative strength using data ending t-1','allocation':'monthly top1','cost_bps_turnover':list(COSTS),'matched_control':'50/50 HYG/LQD','opportunity_controls':['AGG','SPY'],'windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P109_CREDIT_RELATIVE_STRENGTH_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P109_CREDIT_RELATIVE_STRENGTH_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p109_credit_relative_strength_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
