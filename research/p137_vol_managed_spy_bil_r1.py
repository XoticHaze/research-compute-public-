from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

COSTS=(25,50,100)
TARGET_VOL=0.12

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}

def evaluate(q,cost_bps):
    z=q.copy(); z['turnover']=(z.exposure-z.exposure.shift()).abs(); z.loc[z.index[0],'turnover']=1.0
    z['net']=z.gross-z.turnover*cost_bps/10000.0
    mean_x=float(z.exposure.mean()); z['matched']=mean_x*z.spy+(1-mean_x)*z.bil
    out={k:stats(z[k]) for k in ('net','matched','spy')}
    out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_spy_exposure':mean_x,'avg_turnover':float(z.turnover.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs
    return out

def main():
    px=yf.download(['SPY','BIL'],start='2007-06-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    dret=px.pct_change(fill_method=None); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None)
    rows=[]
    for i,dt in enumerate(m.index[:-1]):
        hist=dret.loc[:dt,'SPY'].dropna().tail(21)
        if len(hist)<21: continue
        rv=float(hist.std(ddof=1)*math.sqrt(252)); exposure=float(min(1.0,max(0.0,TARGET_VOL/rv))) if rv>0 else 1.0
        nxt=m.index[i+1]
        if nxt not in mr.index or pd.isna(mr.loc[nxt,'SPY']) or pd.isna(mr.loc[nxt,'BIL']): continue
        spy=float(mr.loc[nxt,'SPY']); bil=float(mr.loc[nxt,'BIL'])
        rows.append({'signal_month':dt,'return_month':nxt,'realized_vol21':rv,'exposure':exposure,'spy':spy,'bil':bil,'gross':exposure*spy+(1-exposure)*bil})
    q=pd.DataFrame(rows).set_index('return_month')
    windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}
    a=tests['2015']['50']; b=tests['2020']['50']
    risk_pass=(a['net']['sharpe_rf0']>a['matched']['sharpe_rf0'] and a['net']['maxdd']>a['matched']['maxdd'])
    persistence=(a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3)
    decision='P137_VOL_MANAGED_SPY_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if risk_pass and persistence else 'P137_VOL_MANAGED_SPY_NOT_SUPPORTED'
    out={'schema':'research.p137_vol_managed_spy_bil_r1','parent':'P137','hypothesis':'Ex-ante volatility scaling of SPY using only the prior completed month can improve risk-adjusted fund utility and after-cost return versus a capital-usage-matched SPY/BIL control without leverage.','contract':{'signal':'At each completed month-end, annualize the trailing 21 SPY daily-return volatility; next-month SPY weight=min(1,12%/realized_vol), remainder BIL.','target_vol':TARGET_VOL,'assets':['SPY','BIL'],'cost_bps':list(COSTS),'matched_control':'static SPY/BIL blend using the evaluated window mean SPY exposure','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_target_horizon_cap_cost_or_asset_search':True,'no_leverage':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p137_vol_managed_spy_bil_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
