from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(5,10,25)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1) if len(r) else float('nan')
def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(252)) if len(r)>1 else float('nan'); ann=float(r.mean()*252) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
    z=q.copy(); z['turnover']=(z.exposure-z.exposure.shift()).abs(); z.loc[z.index[0],'turnover']=float(z.exposure.iloc[0]); z['net']=z.gross-z.turnover*cost/10000
    mx=float(z.exposure.mean()); z['matched']=mx*z.spy+(1-mx)*z.bil
    out={k:stats(z[k]) for k in ('net','matched','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'days':len(z),'mean_spy_exposure':mx,'avg_daily_turnover':float(z.turnover.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; mm=float(a.exposure.mean()); matched=mm*a.spy+(1-mm)*a.bil; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['folds']=fs; return out

def main():
    px=yf.download(['SPY','BIL'],start='2007-06-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); r=px.pct_change(fill_method=None).dropna()
    last=pd.Timestamp(r.index.max()); last=last.tz_localize(None) if last.tzinfo else last; r.index=pd.DatetimeIndex([x.tz_localize(None) if getattr(x,'tzinfo',None) else x for x in r.index])
    idx=r.index; ord_in_month=pd.Series(index=idx,dtype=int); last_day=set()
    for _,g in pd.Series(idx,index=idx).groupby(idx.to_period('M')):
        dates=list(g.index); last_day.add(dates[-1]);
        for j,d in enumerate(dates,1): ord_in_month.loc[d]=j
    exposure=pd.Series([1.0 if (d in last_day or int(ord_in_month.loc[d])<=3) else 0.0 for d in idx],index=idx)
    q=pd.DataFrame({'exposure':exposure,'spy':r.SPY,'bil':r.BIL}); q['gross']=q.exposure*q.spy+(1-q.exposure)*q.bil
    windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['10']; b=tests['2020']['10']
    decision='P143_TURN_OF_MONTH_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P143_TURN_OF_MONTH_NOT_SUPPORTED'
    out={'schema':'research.p143_spy_turn_of_month_r1','parent':'P143','hypothesis':'A fixed turn-of-month calendar exposure, SPY on the last trading day and first three trading days of each month and BIL otherwise, creates after-cost excess versus static SPY/BIL with identical average equity exposure.','contract':{'equity_days':'last trading day plus first three trading days of each calendar month','assets':['SPY','BIL'],'cost_bps':list(COSTS),'matched_control':'static SPY/BIL using evaluated-window mean SPY exposure','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_calendar_window_cost_or_asset_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_observed_date':str(last.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p143_spy_turn_of_month_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
