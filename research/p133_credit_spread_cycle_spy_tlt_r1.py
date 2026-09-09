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
 z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000; out={k:stats(z[k]) for k in ('net','matched','spy')}; out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['months']=len(z); fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out
def main():
 url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2'; raw=requests.get(url,timeout=30).content; x=pd.read_csv(io.BytesIO(raw)); x.columns=['date','oas']; x.date=pd.to_datetime(x.date); x.oas=pd.to_numeric(x.oas,errors='coerce'); x=x.dropna().set_index('date').sort_index()
 px=yf.download(['SPY','TLT'],start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); rows=[]
 for i,dt in enumerate(m.index[:-1]):
  # Conservative availability: exclude final two calendar days before month end.
  h=x.loc[:dt-pd.Timedelta(days=2),'oas'];
  if len(h)<70: continue
  recent=float(h.iloc[-1]); prior=float(h.iloc[max(0,len(h)-64)]); change=recent-prior; nxt=m.index[i+1]; rr=r.loc[nxt]
  if rr.isna().any(): continue
  asset='SPY' if change<=0 else 'TLT'; rows.append({'signal_month':dt,'return_month':nxt,'oas':recent,'oas_change_approx_3m':change,'asset':asset,'gross':float(rr[asset]),'matched':float(.5*rr.SPY+.5*rr.TLT),'spy':float(rr.SPY)})
 q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']; decision='P133_CREDIT_SPREAD_CYCLE_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_spy']>0 and b['positive_spy_folds']>=3 else 'P133_CREDIT_SPREAD_CYCLE_NOT_SUPPORTED'
 out={'schema':'research.p133_credit_spread_cycle_spy_tlt_r1','parent':'P133','hypothesis':'A conservatively lagged three-month high-yield OAS direction separates equity-friendly from defensive months: non-widening spreads select SPY next month, widening spreads select TLT.','contract':{'signal_series':'FRED BAMLH0A0HYM2','availability_lag_calendar_days':2,'signal':'approximately 3-month OAS change <= 0 selects SPY else TLT','assets':['SPY','TLT'],'cost_bps':list(COSTS),'matched_control':'static 50/50 SPY/TLT','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_threshold_horizon_weight_or_cost_search':True},'source':{'fred_sha256':hashlib.sha256(raw).hexdigest(),'price_provider':'Yahoo Finance via yfinance; research-only','price_panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'last_complete_month_end':str(cut.date())},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p133_credit_spread_cycle_spy_tlt_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
