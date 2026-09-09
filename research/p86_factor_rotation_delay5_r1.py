from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("MTUM","QUAL","USMV","VLUE","SIZE"); BP=50

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); dd=float((e/e.cummax()-1).min()); a=float(r.mean()*12); return {'cagr':cagr(r),'sharpe_rf0':a/v if v else None,'max_drawdown':dd}
def main():
 raw=yf.download(list(SYMS)+['SPY'],start='2013-01-01',auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna(how='any').astype(float); m=c.resample('ME').last(); dates=c.index; rows=[]; prev=np.zeros(len(SYMS))
 for i in range(6,len(m)-1):
  sigdt=m.index[i]; nextm=m.index[i+1]; after=dates[dates>sigdt]; aftern=dates[dates>nextm]
  if len(after)<5 or len(aftern)<5: continue
  ent=after[4]; ex=aftern[4]
  if ex>dates.max(): continue
  mom=(m.loc[sigdt,list(SYMS)]/m.iloc[i-6][list(SYMS)]-1).sort_values(ascending=False); chosen=set(mom.index[:2]); w=np.array([.5 if s in chosen else 0 for s in SYMS]); r=(c.loc[ex,list(SYMS)]/c.loc[ent,list(SYMS)]-1).to_numpy(float); turn=.5*float(abs(w-prev).sum()); rows.append({'date':ex,'gross':float(w@r),'turnover':turn,'matched':float(np.mean(r)),'spy':float(c.loc[ex,'SPY']/c.loc[ent,'SPY']-1),'entry':str(pd.Timestamp(ent).date())}); prev=w
 f=pd.DataFrame(rows).set_index('date'); out={'schema':'research.p86_factor_rotation_delay5_r1','parent':'P86','contract':{'model':'unchanged top-two trailing-six-month factor momentum','implementation':'execute five trading days after each month-end signal and hold to five trading days after next month-end','cost_bps':BP,'matched_control':'same-universe static equal weight over identical delayed holding windows','opportunity_control':'SPY','windows':['2020_forward','2022_forward'],'folds':5,'no_parameter_search':True},'tests':{}}
 for name,start in [('2020_forward','2020-01-01'),('2022_forward','2022-01-01')]:
  q=f.loc[start:]; net=q.gross-q.turnover*BP/10000; cm=met(net); mm=met(q.matched); sm=met(q.spy); ids=np.array_split(np.arange(len(q)),5); folds=[]
  for j,x in enumerate(ids,1):
   a=q.iloc[x]; folds.append({'fold':j,'excess_cagr':cagr(a.gross-a.turnover*BP/10000)-cagr(a.matched)})
  out['tests'][name]={'months':len(q),'candidate':cm,'matched':mm,'spy':sm,'excess_cagr_vs_matched':cm['cagr']-mm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-mm['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-mm['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr']>0 for x in folds),'folds':folds}
 p=out['tests']['2020_forward']; out['decision']='P86_DELAY5_IMPLEMENTATION_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 else 'P86_DELAY5_IMPLEMENTATION_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p86_factor_rotation_delay5_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
