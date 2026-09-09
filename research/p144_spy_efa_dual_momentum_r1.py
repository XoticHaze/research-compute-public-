from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
    z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000
    er=float((z.asset!='BIL').mean()); z['matched']=er*.5*z.spy+er*.5*z.efa+(1-er)*z.bil
    out={k:stats(z[k]) for k in ('net','matched','spy','efa')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'equity_exposure':er,'avg_turnover':float(z.turnover.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; ee=float((a.asset!='BIL').mean()); matched=ee*.5*a.spy+ee*.5*a.efa+(1-ee)*a.bil; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out

def main():
    px=yf.download(['SPY','EFA','BIL'],start='2007-06-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    m=px.resample('ME').last(); r=m.pct_change(fill_method=None); mom=m.pct_change(12); rows=[]
    for i,dt in enumerate(m.index[:-1]):
        if i<12 or mom.loc[dt].isna().any(): continue
        nxt=m.index[i+1]; rr=r.loc[nxt]
        if rr.isna().any(): continue
        leader='SPY' if float(mom.loc[dt,'SPY'])>=float(mom.loc[dt,'EFA']) else 'EFA'
        asset=leader if float(mom.loc[dt,leader])>float(mom.loc[dt,'BIL']) else 'BIL'
        rows.append({'signal_month':dt,'return_month':nxt,'asset':asset,'spy_mom12':float(mom.loc[dt,'SPY']),'efa_mom12':float(mom.loc[dt,'EFA']),'bil_mom12':float(mom.loc[dt,'BIL']),'gross':float(rr[asset]),'spy':float(rr.SPY),'efa':float(rr.EFA),'bil':float(rr.BIL)})
    q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']
    decision='P144_DUAL_MOMENTUM_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P144_DUAL_MOMENTUM_NOT_SUPPORTED'
    out={'schema':'research.p144_spy_efa_dual_momentum_r1','parent':'P144','hypothesis':'A fixed 12-month relative-plus-absolute momentum rule across US and developed ex-US equities can create after-cost excess beyond a static blend with the same equity capital usage.','contract':{'signal':'At completed month-end choose higher 12-month momentum of SPY/EFA; hold it next month only if its 12-month return exceeds BIL, otherwise BIL','assets':['SPY','EFA','BIL'],'lookback_months':12,'cost_bps':list(COSTS),'matched_control':'same evaluated-window equity exposure times 50/50 SPY/EFA plus BIL','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_lookback_threshold_weight_cost_or_asset_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p144_spy_efa_dual_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
