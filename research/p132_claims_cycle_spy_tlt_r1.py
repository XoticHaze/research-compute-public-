from __future__ import annotations
import io,json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
COSTS=(25,50,100)

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
 z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000; out={k:stats(z[k]) for k in ('net','matched','spy')}; out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['months']=len(z); out['avg_turnover']=float(z.turnover.mean()); fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out
def main():
 url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICSA'; raw=requests.get(url,timeout=30).content; x=pd.read_csv(io.BytesIO(raw)); x.columns=['date','claims']; x.date=pd.to_datetime(x.date); x.claims=pd.to_numeric(x.claims,errors='coerce'); x=x.dropna().set_index('date').sort_index()
 px=yf.download(['SPY','TLT'],start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); rows=[]
 for i,dt in enumerate(m.index[:-1]):
  # Conservative release timing: use only claims observations dated at least 7 calendar days before month end.
  h=x.loc[:dt-pd.Timedelta(days=7),'claims']
  if len(h)<13: continue
  short=float(h.tail(4).mean()); long=float(h.tail(13).mean()); nxt=m.index[i+1]; rr=r.loc[nxt]
  if rr.isna().any(): continue
  asset='SPY' if short<=long else 'TLT'; rows.append({'signal_month':dt,'return_month':nxt,'claims_4w':short,'claims_13w':long,'asset':asset,'gross':float(rr[asset]),'matched':float(.5*rr.SPY+.5*rr.TLT),'spy':float(rr.SPY)})
 q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']; decision='P132_CLAIMS_CYCLE_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_spy']>0 and b['positive_spy_folds']>=3 else 'P132_CLAIMS_CYCLE_NOT_SUPPORTED'
 out={'schema':'research.p132_claims_cycle_spy_tlt_r1','parent':'P132','hypothesis':'A conservatively lagged weekly claims cycle can distinguish equity-friendly versus defensive months: 4-week ICSA average <= 13-week average selects SPY next month, otherwise TLT.','contract':{'signal_series':'FRED ICSA','availability_lag_calendar_days':7,'signal':'4-week average <= 13-week average selects SPY else TLT','assets':['SPY','TLT'],'cost_bps':list(COSTS),'matched_control':'static 50/50 SPY/TLT','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_threshold_horizon_weight_or_cost_search':True},'source':{'fred_sha256':hashlib.sha256(raw).hexdigest(),'price_provider':'Yahoo Finance via yfinance; research-only','price_panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'last_complete_month_end':str(cut.date())},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p132_claims_cycle_spy_tlt_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
