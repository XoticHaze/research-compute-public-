from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13


def score_twofactor(close: pd.DataFrame, name: str, sig: int) -> float:
    px = close[[name, 'SMH', 'QQQ']].iloc[sig-p13.LOOKBACK:sig+1].dropna()
    if len(px) < p13.MIN_OBS + 1:
        return np.nan
    r = px.pct_change().dropna()
    if len(r) < p13.MIN_OBS:
        return np.nan
    y = r[name].to_numpy(float)
    X = r[['SMH','QQQ']].to_numpy(float)
    Z = np.column_stack([np.ones(len(y)), X])
    if not np.all(np.isfinite(Z)) or not np.all(np.isfinite(y)):
        return np.nan
    coef = np.linalg.lstsq(Z, y, rcond=None)[0]
    resid = y - Z @ coef
    return float(resid.sum())


def cagr(x):
    x = pd.Series(x,dtype=float).dropna()
    return float((1+x).prod()**(12/len(x))-1)


def mdd(x):
    eq=(1+pd.Series(x,dtype=float).fillna(0)).cumprod()
    return float((eq/eq.cummax()-1).min())


def main():
    close, volume = p13.download()
    positions = p13.month_end_indices(close.index)
    rows=[]
    for j in range(len(positions)-1):
        sig,nxt=positions[j],positions[j+1]
        entry,exit_=sig+1,nxt+1
        if sig < p13.LOOKBACK or entry>=len(close) or exit_>=len(close) or close.index[entry] < pd.Timestamp('2019-01-01'):
            continue
        two, one, raw = {}, {}, {}
        for name in p13.UNIVERSE:
            now,then=close.iloc[sig][name],close.iloc[sig-p13.LOOKBACK][name]
            if np.isfinite(now) and np.isfinite(then) and then>0:
                raw[name]=float(now/then-1)
            s1=p13.stock_specific_residual_score(close,name,sig)
            s2=score_twofactor(close,name,sig)
            if np.isfinite(s1): one[name]=s1
            if np.isfinite(s2): two[name]=s2
        common=set(raw).intersection(one).intersection(two)
        if len(common)<8: continue
        n2=sorted(common,key=lambda n:two[n],reverse=True)[:p13.TOP_N]
        n1=sorted(common,key=lambda n:one[n],reverse=True)[:p13.TOP_N]
        nr=sorted(common,key=lambda n:raw[n],reverse=True)[:p13.TOP_N]
        vals=[p13.basket_return(close,n2,entry,exit_),p13.basket_return(close,n1,entry,exit_),p13.basket_return(close,nr,entry,exit_),p13.basket_return(close,sorted(common),entry,exit_),p13.asset_return(close,'SMH',entry,exit_),p13.asset_return(close,'QQQ',entry,exit_)]
        if not all(np.isfinite(v) for v in vals): continue
        rows.append({'entry':close.index[entry],'two':vals[0],'one':vals[1],'raw':vals[2],'ew':vals[3],'smh':vals[4],'qqq':vals[5],'changed_vs_one':n2!=n1})
    f=pd.DataFrame(rows)
    tests={}
    for label,g in [('full',f),('2019_2021',f[(f.entry>='2019-01-01')&(f.entry<'2022-01-01')]),('2022_forward',f[f.entry>='2022-01-01'])]:
        if len(g)<12: continue
        costs={}
        for bp in (25,50):
            drag=bp/10000
            r=g.two-drag
            one=g.one-drag
            raw=g.raw-drag
            costs[str(bp)]={'months':int(len(g)),'twofactor_cagr':cagr(r),'onefactor_cagr':cagr(one),'raw_cagr':cagr(raw),'ew_cagr':cagr(g.ew),'smh_cagr':cagr(g.smh),'qqq_cagr':cagr(g.qqq),'excess_vs_onefactor_cagr':cagr(r)-cagr(one),'excess_vs_raw_cagr':cagr(r)-cagr(raw),'excess_vs_ew_cagr':cagr(r)-cagr(g.ew),'excess_vs_smh_cagr':cagr(r)-cagr(g.smh),'excess_vs_qqq_cagr':cagr(r)-cagr(g.qqq),'max_drawdown':mdd(r)}
        tests[label]=costs
    recent=tests['2022_forward']['50']
    decision='P13_TWOFACTOR_RESIDUAL_SUPPORTED_RECENT' if recent['excess_vs_onefactor_cagr']>0 and recent['excess_vs_smh_cagr']>0 and recent['excess_vs_ew_cagr']>0 else 'P13_TWOFACTOR_RESIDUAL_NOT_INCREMENTAL'
    out={'schema':'research.p13_twofactor_residual_r1','parent':'P13','scientific_contract':{'mutation':'replace prior-window single SMH beta residual with prior-only two-factor SMH+QQQ residual','lookback_sessions':p13.LOOKBACK,'top_n':p13.TOP_N,'comparators':['frozen one-factor P13 residual','raw momentum','equal-weight same-name universe','SMH','QQQ'],'costs_bps':[25,50],'holdouts':['2019-2021','2022-forward'],'known_current-name_survivorship_risk_preserved':True,'no_parameter_search':True},'selection_changed_fraction_vs_onefactor':float(f.changed_vs_one.mean()),'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p13_twofactor_residual_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
