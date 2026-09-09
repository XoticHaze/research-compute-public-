from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100)
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cagr(r),'sharpe_rf0':float(r.mean()*12/v) if v else None,'maxdd':float((eq/eq.cummax()-1).min())}
def ev(q,c):
 z=q.copy(); z['turnover']=(z.x-z.x.shift()).abs(); z.loc[z.index[0],'turnover']=z.x.iloc[0]; z['net']=z.gross-z.turnover*c/10000; mx=float(z.x.mean()); z['matched']=mx*z.spy+(1-mx)*z.bil
 o={k:stats(z[k]) for k in ('net','matched','spy')}; o.update({'excess_matched':o['net']['cagr']-o['matched']['cagr'],'excess_spy':o['net']['cagr']-o['spy']['cagr'],'months':len(z),'mean_spy_exposure':mx})
 fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; m=float(a.x.mean())*a.spy+(1-float(a.x.mean()))*a.bil; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(m)})
 o['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); o['folds']=fs; return o
def main():
 px=yf.download(['SPY','BIL','HYG','IEF'],start='2007-06-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); rel=(m.HYG/m.IEF).pct_change(3); rows=[]
 for i,dt in enumerate(m.index[:-1]):
  if i<3 or pd.isna(rel.loc[dt]): continue
  nxt=m.index[i+1]; rr=r.loc[nxt]; x=1.0 if float(rel.loc[dt])>0 else 0.0; rows.append({'return_month':nxt,'x':x,'gross':x*float(rr.SPY)+(1-x)*float(rr.BIL),'spy':float(rr.SPY),'bil':float(rr.BIL)})
 q=pd.DataFrame(rows).set_index('return_month'); W={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in W.items()}; a=tests['2015']['50']; b=tests['2020']['50']; dec='P145_CREDIT_RISK_REGIME_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P145_CREDIT_RISK_REGIME_NOT_SUPPORTED'
 out={'schema':'research.p145_credit_risk_regime_spy_r1','parent':'P145','hypothesis':'Positive prior-three-month HYG/IEF relative momentum identifies risk appetite strongly enough to improve next-month SPY/BIL allocation versus equal-capital matched exposure.','contract':{'signal':'SPY next month iff completed-month HYG/IEF ratio has positive 3-month return, else BIL','cost_bps':list(COSTS),'matched_control':'static SPY/BIL at evaluated mean SPY exposure','windows':list(W),'folds':5,'no_signal_lookback_threshold_cost_or_asset_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p145_credit_risk_regime_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
