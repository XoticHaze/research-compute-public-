from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['SPY','IEF','GLD']; COSTS=(10,25,50); LOOK=6

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 out={'months':len(q),'controls':{'equal_weight':mt(q['ew']),'spy':mt(q['spy']),'60_40_spy_ief':mt(q['6040'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; fs.append({'fold':j,'ew':cg(x)-cg(a['ew']),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_equal_weight':m['cagr']-out['controls']['equal_weight']['cagr'],'excess_spy':m['cagr']-out['controls']['spy']['cagr'],'excess_60_40':m['cagr']-out['controls']['60_40_spy_ief']['cagr'],'positive_ew_folds':sum(x['ew']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(U,start='2003-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rm=m.pct_change(fill_method=None); rows=[]; prev=np.zeros(len(U))
 for i in range(LOOK+1,len(m)-1):
  vol=rm.iloc[i-LOOK:i].std(ddof=1).to_numpy(); inv=1/np.maximum(vol,1e-8); w=inv/inv.sum(); rr=np.array([float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U]); turn=float(.5*np.abs(w-prev).sum()); rows.append({'date':m.index[i+1],'gross':float(w@rr),'turn':turn,'ew':float(rr.mean()),'spy':rr[0],'6040':float(.6*rr[0]+.4*rr[1])}); prev=w
 q=pd.DataFrame(rows).set_index('date'); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['25']; b=tests['2020']['costs']['25']; ok=a['excess_equal_weight']>0 and b['excess_equal_weight']>0 and a['positive_ew_folds']>=3 and b['positive_ew_folds']>=3 and b['excess_spy']>0
 out={'schema':'research.p127_inverse_vol_multiasset_r1','parent':'P127','hypothesis':'Fixed monthly inverse-volatility allocation across SPY, IEF and GLD creates durable after-cost excess beyond equal-weight multi-asset allocation while remaining competitive with SPY opportunity cost.','contract':{'universe':U,'signal':'inverse of prior-only six completed monthly return volatility','allocation':'monthly normalized inverse-vol weights','cost_bps_turnover':list(COSTS),'matched_control':'equal-weight SPY/IEF/GLD','secondary_control':'60/40 SPY/IEF','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'parameter_search':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P127_INVERSE_VOL_MULTI_ASSET_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P127_INVERSE_VOL_MULTI_ASSET_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p127_inverse_vol_multiasset_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
