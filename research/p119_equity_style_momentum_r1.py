from __future__ import annotations
import json, math, hashlib
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
U=['SPY','IWM','IWD','IWF']; COSTS=(25,50,100); LB=12; SKIP=1

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def evaluate(q):
 out={'months':len(q),'controls':{'equal_weight_styles':metrics(q['matched']),'spy':metrics(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  net=q['gross']-q['turn']*bp/10000; cm=metrics(net); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; n=a['gross']-a['turn']*bp/10000; fs.append({'fold':j,'matched':cagr(n)-cagr(a['matched']),'spy':cagr(n)-cagr(a['spy'])})
  out['costs'][str(bp)]={'candidate':cm,'excess_matched':cm['cagr']-out['controls']['equal_weight_styles']['cagr'],'excess_spy':cm['cagr']-out['controls']['spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(U,start='2001-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]; prev=np.zeros(len(U))
 for i in range(LB+SKIP,len(m)-1):
  scores=np.array([float(m[s].iloc[i-SKIP]/m[s].iloc[i-LB]-1) for s in U]); k=int(np.argmax(scores)); w=np.zeros(len(U)); w[k]=1.; rr=np.array([float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U]); turn=float(.5*np.abs(w-prev).sum()); rows.append({'date':m.index[i+1],'gross':float(w@rr),'turn':turn,'matched':float(rr.mean()),'spy':rr[0]}); prev=w
 q=pd.DataFrame(rows).set_index('date'); tests={k:evaluate(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['50']; b=tests['2020']['costs']['50']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['excess_spy']>0
 out={'schema':'research.p119_equity_style_momentum_r1','parent':'P119','hypothesis':'Fixed 12-to-1 momentum across broad US equity style sleeves creates durable after-cost excess beyond an equal-weight style basket and SPY.','contract':{'universe':U,'signal':'12-to-1 monthly momentum using prices ending t-1','allocation':'monthly top1','cost_bps_turnover':list(COSTS),'matched_control':'equal-weight SPY/IWM/IWD/IWF','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P119_EQUITY_STYLE_MOMENTUM_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P119_EQUITY_STYLE_MOMENTUM_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p119_equity_style_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
