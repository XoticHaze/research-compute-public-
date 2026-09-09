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
 z=q.copy(); z['turnover']=(z.x-z.x.shift()).abs(); z.loc[z.index[0],'turnover']=z.x.iloc[0]; z['net']=z.gross-z.turnover*c/10000; mx=float(z.x.mean()); z['matched']=mx*z.iwm+(1-mx)*z.spy
 o={k:stats(z[k]) for k in ('net','matched','spy')}; o.update({'excess_matched':o['net']['cagr']-o['matched']['cagr'],'excess_spy':o['net']['cagr']-o['spy']['cagr'],'months':len(z),'mean_iwm_exposure':mx})
 fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; m=float(a.x.mean())*a.iwm+(1-float(a.x.mean()))*a.spy; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(m),'spy_excess':cagr(a.net)-cagr(a.spy)})
 o['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); o['positive_spy_folds']=sum(f['spy_excess']>0 for f in fs); o['folds']=fs; return o
def main():
 px=yf.download(['IWM','SPY'],start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); lead=m.IWM.pct_change(6)-m.SPY.pct_change(6); rows=[]
 for i,dt in enumerate(m.index[:-1]):
  if i<6 or pd.isna(lead.loc[dt]): continue
  nxt=m.index[i+1]; rr=r.loc[nxt]; x=1.0 if float(lead.loc[dt])>0 else 0.0; rows.append({'return_month':nxt,'x':x,'gross':x*float(rr.IWM)+(1-x)*float(rr.SPY),'iwm':float(rr.IWM),'spy':float(rr.SPY)})
 q=pd.DataFrame(rows).set_index('return_month'); W={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in W.items()}; a=tests['2015']['50']; b=tests['2020']['50']; dec='P149_SMALLCAP_LEADERSHIP_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and a['excess_spy']>0 else 'P149_SMALLCAP_LEADERSHIP_NOT_SUPPORTED'
 out={'schema':'research.p149_smallcap_leadership_r1','parent':'P149','hypothesis':'Prior completed-month six-month IWM leadership over SPY persists enough to improve next-month IWM/SPY selection versus exposure-matched static allocation and SPY after costs.','contract':{'signal':'IWM next month iff completed-month trailing-6-month IWM return exceeds SPY, else SPY','cost_bps':list(COSTS),'matched_control':'static IWM/SPY at evaluated mean IWM exposure','opportunity_control':'SPY','windows':list(W),'folds':5,'no_horizon_threshold_weight_cost_or_asset_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p149_smallcap_leadership_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
