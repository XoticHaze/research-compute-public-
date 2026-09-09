from __future__ import annotations
import io,json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
COSTS=(25,50,100)

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def eval(q,cost):
 z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000; out={k:stats(z[k]) for k in ('net','matched','spy','eem')}; out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['excess_eem']=out['net']['cagr']-out['eem']['cagr']; out['months']=len(z); out['avg_turnover']=float(z.turnover.mean()); fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out
def main():
 url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS'; raw=requests.get(url,timeout=30).content; fx=pd.read_csv(io.BytesIO(raw)); fx.columns=['date','usd']; fx['date']=pd.to_datetime(fx.date); fx['usd']=pd.to_numeric(fx.usd,errors='coerce'); fx=fx.dropna().set_index('date').sort_index()
 px=yf.download(['EEM','SPY'],start='2006-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cutoff]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); fm=fx.resample('ME').last().reindex(m.index,method='ffill'); d3=fm.usd.pct_change(3); rows=[]
 for i,dt in enumerate(m.index[:-1]):
  if pd.isna(d3.loc[dt]): continue
  nxt=m.index[i+1]; rr=r.loc[nxt]
  if rr.isna().any(): continue
  # Predeclared mechanism: falling broad USD supports EM financial conditions; rising USD favors US equity.
  asset='EEM' if d3.loc[dt] < 0 else 'SPY'; rows.append({'signal_month':dt,'return_month':nxt,'usd_3m_change':float(d3.loc[dt]),'asset':asset,'gross':float(rr[asset]),'matched':float(.5*rr.EEM+.5*rr.SPY),'spy':float(rr.SPY),'eem':float(rr.EEM)})
 q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; tests={w:{str(c):eval(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']; decision='P131_DOLLAR_REGIME_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_spy']>0 and b['positive_spy_folds']>=3 else 'P131_DOLLAR_REGIME_NOT_SUPPORTED'
 out={'schema':'research.p131_dollar_regime_eem_spy_r1','parent':'P131','hypothesis':'Use only the sign of the prior completed month three-month change in the Fed broad dollar index: weakening USD selects EEM next month, otherwise SPY.','contract':{'signal_series':'FRED DTWEXBGS','signal':'3 completed-month percent change < 0 selects EEM, else SPY','assets':['EEM','SPY'],'cost_bps':list(COSTS),'matched_control':'static 50/50 EEM/SPY','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_threshold_horizon_weight_or_cost_search':True},'source':{'fred_sha256':hashlib.sha256(raw).hexdigest(),'price_provider':'Yahoo Finance via yfinance; research-only','price_panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'last_complete_month_end':str(cutoff.date())},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p131_dollar_regime_eem_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
