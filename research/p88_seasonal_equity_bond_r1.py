from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100)
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); dd=float((e/e.cummax()-1).min()); a=float(r.mean()*12); return {'cagr':cagr(r),'sharpe_rf0':a/v if v else None,'max_drawdown':dd}
def main():
 raw=yf.download(['SPY','TLT'],start='2003-01-01',auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna().astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.array([.5,.5])
 for i in range(len(m)-1):
  dt=m.index[i]; nxt=m.index[i+1]; target_month=nxt.month; w=np.array([1.,0.]) if target_month in (11,12,1,2,3,4) else np.array([0.,1.]); r=(m.loc[nxt,['SPY','TLT']]/m.loc[dt,['SPY','TLT']]-1).to_numpy(float); turn=.5*float(abs(w-prev).sum()); rows.append({'date':nxt,'gross':float(w@r),'turnover':turn,'matched':float(.5*r.sum()),'spy':float(r[0])}); prev=w
 f=pd.DataFrame(rows).set_index('date'); out={'schema':'research.p88_seasonal_equity_bond_r1','parent':'P88','hypothesis':'A fixed Nov-Apr SPY / May-Oct TLT seasonal allocation creates durable after-cost excess versus static 50/50 SPY-TLT and SPY.','contract':{'rule':'SPY in Nov-Apr; TLT in May-Oct','costs_bps':list(COSTS),'matched_control':'static 50/50 SPY-TLT','opportunity_control':'SPY','windows':['full','2015_forward','2020_forward'],'folds':5,'no_parameter_search':True},'tests':{}}
 for name,start in [('full',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')]:
  q=f if start is None else f.loc[start:]; z={'months':len(q),'controls':{'matched':met(q.matched),'spy':met(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
  for bp in COSTS:
   net=q.gross-q.turnover*bp/10000; cm=met(net); folds=[]
   for j,x in enumerate(ids,1):
    a=q.iloc[x]; folds.append({'fold':j,'excess_cagr':cagr(a.gross-a.turnover*bp/10000)-cagr(a.matched)})
   z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_matched':cm['cagr']-z['controls']['matched']['cagr'],'excess_cagr_vs_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-z['controls']['matched']['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr']>0 for x in folds),'folds':folds}
  out['tests'][name]=z
 p=out['tests']['2020_forward']['costs']['50']; out['decision']='P88_SEASONAL_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P88_SEASONAL_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p88_seasonal_equity_bond_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
