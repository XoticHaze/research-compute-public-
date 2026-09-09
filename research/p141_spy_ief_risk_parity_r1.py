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
    z=q.copy(); z['turnover']=(z.spy_w-z.spy_w.shift()).abs(); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000
    meanw=float(z.spy_w.mean()); z['matched']=meanw*z.spy+(1-meanw)*z.ief; z['sixty40']=.6*z.spy+.4*z.ief
    out={k:stats(z[k]) for k in ('net','matched','sixty40','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_6040':out['net']['cagr']-out['sixty40']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_spy_weight':meanw,'avg_turnover':float(z.turnover.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; mw=float(a.spy_w.mean()); matched=mw*a.spy+(1-mw)*a.ief
        fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(matched),'sixty40_excess':cagr(a.net)-cagr(.6*a.spy+.4*a.ief),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_6040_folds']=sum(x['sixty40_excess']>0 for x in fs); out['folds']=fs; return out

def main():
    px=yf.download(['SPY','IEF'],start='2003-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    d=px.pct_change(fill_method=None); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None); rows=[]
    for i,dt in enumerate(m.index[:-1]):
        h=d.loc[:dt].tail(63).dropna()
        if len(h)<63: continue
        vol=h.std(ddof=1)*math.sqrt(252); inv=1/vol; w=inv/inv.sum(); nxt=m.index[i+1]
        if nxt not in mr.index or mr.loc[nxt].isna().any(): continue
        spy=float(mr.loc[nxt,'SPY']); ief=float(mr.loc[nxt,'IEF']); sw=float(w.SPY)
        rows.append({'signal_month':dt,'return_month':nxt,'spy_w':sw,'ief_w':1-sw,'spy':spy,'ief':ief,'gross':sw*spy+(1-sw)*ief})
    q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']
    risk=a['net']['sharpe_rf0']>a['matched']['sharpe_rf0'] and a['net']['maxdd']>a['matched']['maxdd']
    decision='P141_SPY_IEF_RISK_PARITY_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and risk else 'P141_SPY_IEF_RISK_PARITY_NOT_SUPPORTED'
    out={'schema':'research.p141_spy_ief_risk_parity_r1','parent':'P141','hypothesis':'A fixed monthly inverse-volatility SPY/IEF allocation using only the prior 63 trading days can improve after-cost risk-adjusted fund utility versus a capital-usage-matched static blend.','contract':{'signal':'At each completed month-end compute 63-trading-day annualized SPY and IEF volatility; next-month weights are normalized inverse volatility','assets':['SPY','IEF'],'lookback_days':63,'cost_bps':list(COSTS),'matched_control':'static SPY/IEF blend using evaluated-window mean SPY weight','secondary_control':'static 60/40 SPY/IEF','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_lookback_weight_floor_cost_or_asset_search':True,'no_leverage':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p141_spy_ief_risk_parity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
