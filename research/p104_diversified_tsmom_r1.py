from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['SPY','TLT','GLD','DBC','UUP','VNQ','EEM']; COSTS=(25,50,100); LB=12; SKIP=1

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 z={'months':len(q),'average_invested_fraction':float(q.inv.mean()),'controls':{'static_equal_weight':mt(q.matched),'spy':mt(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q.gross-q.turn*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a.gross-a.turn*bp/10000; fs.append({'fold':j,'matched':cg(x)-cg(a.matched),'spy':cg(x)-cg(a.spy)})
  z['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-z['controls']['static_equal_weight']['cagr'],'excess_spy':m['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_matched':m['sharpe_rf0']-z['controls']['static_equal_weight']['sharpe_rf0'],'dd_delta_matched':m['maxdd']-z['controls']['static_equal_weight']['maxdd'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return z
def main():
 raw=yf.download(U,start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.zeros(len(U))
 for i in range(LB+SKIP,len(m)-1):
  score=m.iloc[i-SKIP]/m.iloc[i-LB]-1; w=(score>0).astype(float).to_numpy()/len(U); r=(m.iloc[i+1]/m.iloc[i]-1).to_numpy(float); turn=float(.5*np.abs(w-prev).sum()); rows.append({'date':m.index[i+1],'gross':float(w@r),'turn':turn,'matched':float(r.mean()),'spy':float(r[0]),'inv':float(w.sum())}); prev=w
 f=pd.DataFrame(rows).set_index('date'); tests={k:ev(f.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['candidate']['sharpe_rf0']>tests['2020']['controls']['static_equal_weight']['sharpe_rf0']
 out={'schema':'research.p104_diversified_tsmom_r1','parent':'P104','hypothesis':'A fixed lagged 12-month absolute trend rule across diversified liquid asset-class ETFs creates durable after-cost fund alpha and drawdown improvement beyond static equal weight.','contract':{'universe':U,'signal':'12-month absolute return using data ending t-1','allocation':'1/7 long each positive-trend asset; otherwise that sleeve is cash','cost_bps_turnover':list(COSTS),'matched_control':'static equal-weight same universe','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P104_DIVERSIFIED_TSMOM_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P104_DIVERSIFIED_TSMOM_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p104_diversified_tsmom_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
