from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
    z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000
    out={k:stats(z[k]) for k in ('net','matched','spy')}; out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['months']=len(z); out['avg_turnover']=float(z.turnover.mean()); fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out
def main():
    px=yf.download(['QUAL','SPY'],start='2013-07-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    m=px.resample('ME').last(); r=m.pct_change(fill_method=None); mom=m.pct_change(6); rows=[]
    for i,dt in enumerate(m.index[:-1]):
        if mom.loc[dt].isna().any(): continue
        nxt=m.index[i+1]; rr=r.loc[nxt]
        if rr.isna().any(): continue
        asset='QUAL' if float(mom.loc[dt,'QUAL'])>float(mom.loc[dt,'SPY']) else 'SPY'
        rows.append({'signal_month':dt,'return_month':nxt,'qual_mom6':float(mom.loc[dt,'QUAL']),'spy_mom6':float(mom.loc[dt,'SPY']),'asset':asset,'gross':float(rr[asset]),'matched':float(.5*rr.QUAL+.5*rr.SPY),'spy':float(rr.SPY)})
    q=pd.DataFrame(rows).set_index('return_month'); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']
    decision='P136_QUALITY_LEADERSHIP_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_spy']>0 and b['positive_spy_folds']>=3 else 'P136_QUALITY_LEADERSHIP_NOT_SUPPORTED'
    out={'schema':'research.p136_quality_leadership_qual_spy_r1','parent':'P136','hypothesis':'Prior completed-month six-month quality leadership is persistent enough to select QUAL over SPY next month and create after-cost excess.','contract':{'signal':'QUAL six-month total return > SPY six-month total return selects QUAL next month, else SPY','assets':['QUAL','SPY'],'cost_bps':list(COSTS),'matched_control':'static 50/50 QUAL/SPY','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_horizon_threshold_weight_or_cost_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p136_quality_leadership_qual_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
