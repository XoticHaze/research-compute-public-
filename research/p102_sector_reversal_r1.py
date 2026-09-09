from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
S=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=S+['SPY']; COSTS=(25,50,100); TOPK=3

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def test(q):
 z={'months':len(q),'controls':{'equal_weight':mt(q.matched),'spy':mt(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  net=q.gross-q.turn*bp/10000; cm=mt(net); folds=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; n=a.gross-a.turn*bp/10000; folds.append({'fold':j,'matched':cg(n)-cg(a.matched),'spy':cg(n)-cg(a.spy)})
  z['costs'][str(bp)]={'candidate':cm,'excess_matched':cm['cagr']-z['controls']['equal_weight']['cagr'],'excess_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta':cm['sharpe']-z['controls']['equal_weight']['sharpe'],'dd_delta':cm['maxdd']-z['controls']['equal_weight']['maxdd'],'positive_matched_folds':sum(x['matched']>0 for x in folds),'positive_spy_folds':sum(x['spy']>0 for x in folds),'folds':folds}
 return z
def main():
 raw=yf.download(ALL,start='1999-01-01',auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna().astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.ones(len(S))/len(S)
 for i in range(1,len(m)-1):
  dt=m.index[i]; nxt=m.index[i+1]; prior=(m.loc[dt,S]/m.iloc[i-1][S]-1); chosen=set(prior.nsmallest(TOPK).index); w=np.array([1/TOPK if s in chosen else 0 for s in S]); r=(m.loc[nxt,S]/m.loc[dt,S]-1).to_numpy(float); turn=.5*abs(w-prev).sum(); rows.append({'date':nxt,'gross':float(w@r),'turn':float(turn),'matched':float(r.mean()),'spy':float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1)}); prev=w
 f=pd.DataFrame(rows).set_index('date'); tests={k:test(f.loc[v:]) for k,v in {'full':'2001-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and b['positive_matched_folds']>=3
 out={'schema':'research.p102_sector_reversal_r1','parent':'P102','hypothesis':'A fixed one-month cross-sectional reversal rank across the nine legacy US sector ETFs creates durable after-cost excess beyond same-universe equal weight.','contract':{'signal':'prior calendar-month total-price return ascending','allocation':'top3 worst prior-month sectors equal weight for next month','cost_bps_turnover':list(COSTS),'matched_control':'equal-weight nine sectors','opportunity_control':'SPY','windows':['full','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P102_SECTOR_REVERSAL_SUPPORTED' if ok else 'P102_SECTOR_REVERSAL_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p102_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
