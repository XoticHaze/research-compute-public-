from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100); LOOK=6

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 ex=float(q['exp'].mean()); matched=q['spy']*ex; out={'months':len(q),'avg_exposure':ex,'controls':{'exposure_matched_spy':mt(matched),'full_spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; z=a['spy']*ex; fs.append({'fold':j,'matched':cg(x)-cg(z),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_spy']['cagr'],'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(['SPY','RSP'],start='2003-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; ratio=m['RSP']/m['SPY']; rows=[]; prev=0.
 for i in range(LOOK+1,len(m)-1):
  breadth=float(ratio.iloc[i-1]/ratio.iloc[i-1-LOOK]-1); exp=1.0 if breadth>0 else 0.0; spy=float(m['SPY'].iloc[i+1]/m['SPY'].iloc[i]-1); rows.append({'date':m.index[i+1],'gross':exp*spy,'turn':abs(exp-prev),'spy':spy,'exp':exp}); prev=exp
 q=pd.DataFrame(rows).set_index('date'); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3
 out={'schema':'research.p126_rsp_breadth_gate_r1','parent':'P126','hypothesis':'A fixed equal-weight-versus-cap-weight breadth regime, measured by prior-only six-month RSP/SPY relative strength, identifies SPY months with durable after-cost excess versus identical average exposure.','contract':{'assets':['RSP','SPY'],'signal':'hold SPY next month only when RSP/SPY six-month relative return through prior completed month is positive','cost_bps_turnover':list(COSTS),'matched_control':'continuous SPY scaled to average exposure','opportunity_control':'full SPY','windows':['2010','2015','2020'],'folds':5,'parameter_search':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P126_BREADTH_GATE_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P126_BREADTH_GATE_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p126_rsp_breadth_gate_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
