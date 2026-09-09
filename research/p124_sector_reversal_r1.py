from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=U+['SPY']; COSTS=(25,50,100)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 out={'months':len(q),'controls':{'equal_weight_sectors':mt(q['matched']),'spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; fs.append({'fold':j,'matched':cg(x)-cg(a['matched']),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['equal_weight_sectors']['cagr'],'excess_spy':m['cagr']-out['controls']['spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(ALL,start='1999-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rm=m[U].pct_change(fill_method=None); rows=[]; prev=np.zeros(len(U))
 for i in range(3,len(m)-1):
  sig=rm.iloc[i-1].to_numpy(); low=np.argsort(sig)[:2]; w=np.zeros(len(U)); w[low]=.5; rr=np.array([float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U]); turn=float(.5*np.abs(w-prev).sum()); rows.append({'date':m.index[i+1],'gross':float(w@rr),'turn':turn,'matched':float(rr.mean()),'spy':float(m['SPY'].iloc[i+1]/m['SPY'].iloc[i]-1)}); prev=w
 q=pd.DataFrame(rows).set_index('date'); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['excess_spy']>0
 out={'schema':'research.p124_sector_reversal_r1','parent':'P124','hypothesis':'A fixed one-month cross-sectional reversal across nine long-history US sectors creates durable after-cost excess beyond equal-weight sectors and SPY.','contract':{'universe':U,'signal':'select two worst sector returns from the fully completed prior month, one-month information lag','allocation':'monthly bottom2 equal weight','cost_bps_turnover':list(COSTS),'matched_control':'equal-weight nine-sector basket','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'parameter_search':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P124_SECTOR_REVERSAL_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P124_SECTOR_REVERSAL_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p124_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
