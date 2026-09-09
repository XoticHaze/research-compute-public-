from __future__ import annotations
import json, math, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

COUNTRIES=['EWJ','EWU','EWG','EWC','EWA','EWY','EWT','EWH','EWS','EWW','EWZ','EZA']
ALL=COUNTRIES+['SPY']
COSTS=(25,50,100)
VOL_MONTHS=6
TOPK=3
WINDOWS={'2010_forward':'2010-01-01','2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol else None,'max_drawdown':float((eq/eq.cummax()-1).min()),'annual_vol':vol}

def evaluate(q):
    z={'months':int(len(q)),'controls':{'matched_equal_weight':metrics(q.matched),'spy':metrics(q.spy)},'costs':{}}
    folds=np.array_split(np.arange(len(q)),5)
    for bp in COSTS:
        net=q.gross-q.turnover*bp/10000; cm=metrics(net); fs=[]
        for j,ix in enumerate(folds,1):
            a=q.iloc[ix]; n=a.gross-a.turnover*bp/10000
            fs.append({'fold':j,'excess_matched':cagr(n)-cagr(a.matched),'excess_spy':cagr(n)-cagr(a.spy)})
        z['costs'][str(bp)]={'candidate':cm,'excess_vs_matched_cagr':cm['cagr']-z['controls']['matched_equal_weight']['cagr'],'excess_vs_spy_cagr':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched_equal_weight']['sharpe_rf0'],'maxdd_delta_vs_matched':cm['max_drawdown']-z['controls']['matched_equal_weight']['max_drawdown'],'positive_matched_folds':sum(x['excess_matched']>0 for x in fs),'positive_spy_folds':sum(x['excess_spy']>0 for x in fs),'folds':fs}
    return z

def main():
    raw=yf.download(ALL,start='2003-01-01',auto_adjust=True,progress=False,threads=False)['Close'].sort_index().astype(float)
    last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=raw.resample('ME').last(); m=m[m.index<=cutoff]
    mr=m.pct_change()
    rows=[]; prev={s:0.0 for s in COUNTRIES}
    for i in range(VOL_MONTHS+1,len(m)-1):
        # At close t, rank using six monthly returns ending at t-1; hold t -> t+1.
        hist=mr.iloc[i-VOL_MONTHS:i]
        vols={s:float(hist[s].std(ddof=1)) for s in COUNTRIES if hist[s].notna().all() and pd.notna(m.iloc[i][s]) and pd.notna(m.iloc[i+1][s])}
        if len(vols)<8 or pd.isna(m.iloc[i]['SPY']) or pd.isna(m.iloc[i+1]['SPY']): continue
        chosen=set(sorted(vols,key=lambda s:(vols[s],s))[:TOPK])
        w={s:(1/TOPK if s in chosen else 0.0) for s in COUNTRIES}
        turn=.5*sum(abs(w[s]-prev[s]) for s in COUNTRIES)
        rets={s:float(m.iloc[i+1][s]/m.iloc[i][s]-1) for s in vols}
        gross=sum(w[s]*rets[s] for s in chosen)
        rows.append({'date':m.index[i+1],'gross':gross,'turnover':turn,'matched':float(np.mean(list(rets.values()))),'spy':float(m.iloc[i+1]['SPY']/m.iloc[i]['SPY']-1)})
        prev=w
    f=pd.DataFrame(rows).set_index('date')
    tests={name:evaluate(f.loc[start:]) for name,start in WINDOWS.items()}
    a=tests['2015_forward']['costs']['50']; b=tests['2020_forward']['costs']['50']
    supported=(a['excess_vs_matched_cagr']>0 and b['excess_vs_matched_cagr']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['candidate']['sharpe_rf0']>tests['2020_forward']['controls']['matched_equal_weight']['sharpe_rf0'])
    out={'schema':'research.p105_country_lowvol_r1','parent':'P105','hypothesis':'A fixed country-ETF low-volatility rank creates durable after-cost excess and risk-adjusted improvement beyond the same country universe equal weight.','contract':{'universe':COUNTRIES,'signal':'six completed monthly returns ending t-1, rank ascending realized volatility','allocation':'monthly lowest-volatility top3 equal weight','cost_bps_turnover':list(COSTS),'matched_control':'same eligible country universe equal weight','opportunity_control':'SPY','windows':WINDOWS,'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P105_COUNTRY_LOWVOL_SUPPORTED_FOR_FURTHER_FALSIFICATION' if supported else 'P105_COUNTRY_LOWVOL_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p105_country_lowvol_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
