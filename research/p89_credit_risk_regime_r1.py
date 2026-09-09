from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

COSTS=(25,50,100)
TICKERS=['HYG','LQD','QQQ','TLT','SPY']

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def metrics(r):
    r=pd.Series(r,dtype=float).dropna()
    eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    dd=float((eq/eq.cummax()-1).min()) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'max_drawdown':dd}

def main():
    raw=yf.download(TICKERS,start='2007-01-01',auto_adjust=True,progress=False,threads=False)
    close=raw['Close'].dropna().astype(float)
    last=pd.Timestamp(close.index.max())
    last=last.tz_localize(None) if last.tzinfo else last
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last()
    m=m[m.index<=cutoff]
    rows=[]
    prev=np.array([0.5,0.5])
    for i in range(3,len(m)-1):
        dt=m.index[i]; nxt=m.index[i+1]
        credit_now=float(m.loc[dt,'HYG']/m.loc[dt,'LQD'])
        credit_lag=float(m.iloc[i-3]['HYG']/m.iloc[i-3]['LQD'])
        risk_on=credit_now>credit_lag
        w=np.array([1.0,0.0]) if risk_on else np.array([0.0,1.0])
        r=(m.loc[nxt,['QQQ','TLT']]/m.loc[dt,['QQQ','TLT']]-1).to_numpy(float)
        turn=0.5*float(abs(w-prev).sum())
        rows.append({'date':nxt,'gross':float(w@r),'turnover':turn,'matched':float(0.5*r.sum()),'qqq':float(r[0]),'spy':float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1),'risk_on':bool(risk_on)})
        prev=w
    f=pd.DataFrame(rows).set_index('date')
    out={'schema':'research.p89_credit_risk_regime_r1','parent':'P89','hypothesis':'A fixed three-month HYG/LQD relative-strength state can allocate between QQQ and TLT with durable after-cost excess over static 50/50 QQQ-TLT and broad-market opportunity controls.','contract':{'signal':'HYG/LQD ratio higher than three months earlier = QQQ, otherwise TLT','allocation':'100% QQQ or 100% TLT monthly','costs_bps':list(COSTS),'matched_control':'static 50/50 QQQ-TLT','opportunity_controls':['QQQ','SPY'],'windows':['full','2015_forward','2020_forward'],'folds':5,'no_parameter_search':True},'tests':{}}
    for name,start in [('full',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')]:
        q=f if start is None else f.loc[start:]
        z={'months':len(q),'risk_on_fraction':float(q.risk_on.mean()),'controls':{'matched':metrics(q.matched),'qqq':metrics(q.qqq),'spy':metrics(q.spy)},'costs':{}}
        ids=np.array_split(np.arange(len(q)),5)
        for bp in COSTS:
            net=q.gross-q.turnover*bp/10000
            cm=metrics(net)
            folds=[]
            for j,x in enumerate(ids,1):
                a=q.iloc[x]
                candidate=a.gross-a.turnover*bp/10000
                folds.append({'fold':j,'excess_cagr_vs_matched':cagr(candidate)-cagr(a.matched),'excess_cagr_vs_qqq':cagr(candidate)-cagr(a.qqq)})
            z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_matched':cm['cagr']-z['controls']['matched']['cagr'],'excess_cagr_vs_qqq':cm['cagr']-z['controls']['qqq']['cagr'],'excess_cagr_vs_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-z['controls']['matched']['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr_vs_matched']>0 for x in folds),'positive_qqq_folds':sum(x['excess_cagr_vs_qqq']>0 for x in folds),'folds':folds}
        out['tests'][name]=z
    p=out['tests']['2020_forward']['costs']['50']
    out['decision']='P89_CREDIT_REGIME_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P89_CREDIT_REGIME_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p89_credit_risk_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__':
    main()
