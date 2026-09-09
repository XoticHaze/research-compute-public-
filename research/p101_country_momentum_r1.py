from __future__ import annotations
import json, math, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

COUNTRIES=['EWJ','EWU','EWG','EWC','EWA','EWY','EWT','EWH','EWS','EWW','EWZ','EZA']
ALL=COUNTRIES+['SPY']
COSTS=(25,50,100)
TOPK=3
LOOKBACK=12
SKIP=1
WINDOWS={'2010_forward':'2010-01-01','2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol else None,'max_drawdown':float((eq/eq.cummax()-1).min())}

def score_window(f):
    out={'months':int(len(f)),'controls':{'matched_equal_weight':metrics(f.matched),'spy':metrics(f.spy)},'average_names':float(f.eligible.mean()),'costs':{}}
    ids=np.array_split(np.arange(len(f)),5)
    for bp in COSTS:
        net=f.gross-f.turnover*bp/10000
        cm=metrics(net); folds=[]
        for j,ix in enumerate(ids,1):
            q=f.iloc[ix]; cand=q.gross-q.turnover*bp/10000
            folds.append({'fold':j,'excess_vs_matched_cagr':cagr(cand)-cagr(q.matched),'excess_vs_spy_cagr':cagr(cand)-cagr(q.spy)})
        out['costs'][str(bp)]={'candidate':cm,'excess_vs_matched_cagr':cm['cagr']-out['controls']['matched_equal_weight']['cagr'],'excess_vs_spy_cagr':cm['cagr']-out['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-out['controls']['matched_equal_weight']['sharpe_rf0'],'maxdd_delta_vs_matched':cm['max_drawdown']-out['controls']['matched_equal_weight']['max_drawdown'],'positive_matched_folds':sum(x['excess_vs_matched_cagr']>0 for x in folds),'positive_spy_folds':sum(x['excess_vs_spy_cagr']>0 for x in folds),'folds':folds}
    return out

def main():
    raw=yf.download(ALL,start='2003-01-01',auto_adjust=True,progress=False,threads=False,group_by='column')
    close=raw['Close'].sort_index().astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m[m.index<=cutoff]
    rows=[]; prev={s:0.0 for s in COUNTRIES}
    for i in range(LOOKBACK+SKIP,len(m)-1):
        dt=m.index[i]; nxt=m.index[i+1]
        signal_end=i-SKIP; signal_start=i-LOOKBACK
        scores={}
        for s in COUNTRIES:
            p0=m.iloc[signal_start][s]; p1=m.iloc[signal_end][s]; pnow=m.iloc[i][s]; pnxt=m.iloc[i+1][s]
            if pd.notna(p0) and pd.notna(p1) and pd.notna(pnow) and pd.notna(pnxt) and p0>0 and pnow>0:
                scores[s]=float(p1/p0-1)
        if len(scores)<8 or pd.isna(m.iloc[i].SPY) or pd.isna(m.iloc[i+1].SPY): continue
        chosen=set(sorted(scores,key=lambda s:(-scores[s],s))[:TOPK])
        w={s:(1/TOPK if s in chosen else 0.0) for s in COUNTRIES}
        turn=.5*sum(abs(w[s]-prev[s]) for s in COUNTRIES)
        rets={s:float(m.iloc[i+1][s]/m.iloc[i][s]-1) for s in scores}
        gross=sum(w[s]*rets[s] for s in chosen)
        matched=float(np.mean(list(rets.values())))
        spy=float(m.iloc[i+1].SPY/m.iloc[i].SPY-1)
        rows.append({'date':nxt,'gross':gross,'turnover':turn,'matched':matched,'spy':spy,'eligible':len(scores),'chosen':sorted(chosen)})
        prev=w
    f=pd.DataFrame(rows).set_index('date')
    tests={name:score_window(f.loc[start:]) for name,start in WINDOWS.items()}
    t=tests['2020_forward']['costs']['50']; t15=tests['2015_forward']['costs']['50']
    supported=t['excess_vs_matched_cagr']>0 and t['excess_vs_spy_cagr']>0 and t['positive_matched_folds']>=3 and t15['excess_vs_matched_cagr']>0
    out={'schema':'research.p101_country_momentum_r1','parent':'P101','hypothesis':'A predeclared lagged 12-to-1 momentum rank across liquid single-country equity ETFs creates durable after-cost cross-sectional excess beyond same-universe equal weight and SPY opportunity cost.','contract':{'universe':COUNTRIES,'signal':'12-to-1 monthly momentum: price at t-1 divided by price at t-12 minus one','execution':'rank at month-end t using data ending t-1; hold top3 equal weight t to t+1','topk':TOPK,'cost_bps_turnover':list(COSTS),'matched_control':'same eligible country universe equal weight','opportunity_control':'SPY','windows':WINDOWS,'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'monthly_panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P101_COUNTRY_MOMENTUM_SUPPORTED' if supported else 'P101_COUNTRY_MOMENTUM_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p101_country_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
