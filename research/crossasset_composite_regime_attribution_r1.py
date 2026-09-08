from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base

SYMBOLS = base.UNIVERSES["crossasset"]


def build_months(close: pd.DataFrame) -> pd.DataFrame:
    monthly = close.resample("ME").last()
    last = pd.Timestamp(close.index.max())
    if last.tzinfo is not None:
        last = last.tz_localize(None)
    monthly = monthly.loc[monthly.index <= last.normalize()].copy()
    daily_r = close.pct_change()
    vol6 = (daily_r.rolling(126, min_periods=100).std(ddof=0) * np.sqrt(252)).resample("ME").last()
    trend200 = (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    dd6 = (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom6 = monthly.pct_change(6)
    prev={s:0.0 for s in SYMBOLS}; rows=[]
    for month in monthly.index:
        block=pd.DataFrame(index=list(SYMBOLS))
        block['mom6']=mom6.loc[month,list(SYMBOLS)]
        block['trend200']=trend200.loc[month,list(SYMBOLS)]
        block['low_vol6']=-vol6.loc[month,list(SYMBOLS)]
        block['drawdown6']=dd6.loc[month,list(SYMBOLS)]
        if block.isna().any().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1)
        chosen=score.sort_values(ascending=False).head(2).index.tolist()
        loc=monthly.index.get_loc(month)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
        nxt=monthly.index[loc+1]
        realized=monthly.loc[nxt,list(SYMBOLS)]/monthly.loc[month,list(SYMBOLS)]-1
        if realized.isna().any(): continue
        w={s:(0.5 if s in chosen else 0.0) for s in SYMBOLS}
        turnover=0.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
        gross=sum(w[s]*float(realized[s]) for s in SYMBOLS)
        ew=float(realized.mean())
        spy=float(monthly.at[nxt,'SPY']/monthly.at[month,'SPY']-1)
        qqq=float(monthly.at[nxt,'QQQ']/monthly.at[month,'QQQ']-1)
        prior_spy_6m=float(mom6.at[month,'SPY'])
        rows.append({'feature_month':str(month.date()),'return_month':str(nxt.date()),'gross':gross,'net25':gross-turnover*0.0025,'ew':ew,'spy':spy,'qqq':qqq,'turnover':turnover,'prior_spy_6m':prior_spy_6m,'risk_state':'risk_off' if prior_spy_6m<=0 else 'risk_on','chosen':chosen})
        prev=w
    return pd.DataFrame(rows)


def conditional_metrics(frame: pd.DataFrame) -> dict:
    out={}
    for state in ['risk_on','risk_off']:
        f=frame[frame.risk_state==state].reset_index(drop=True)
        out[state]={'months':len(f),'candidate':base.metrics(f.net25),'ew':base.metrics(f.ew),'spy':base.metrics(f.spy),'qqq':base.metrics(f.qqq),'mean_excess_vs_ew':float((f.net25-f.ew).mean()),'mean_excess_vs_spy':float((f.net25-f.spy).mean()),'mean_excess_vs_qqq':float((f.net25-f.qqq).mean())}
    return out


def main():
    close=base.load(SYMBOLS)
    frame=build_months(close)
    selection={s:int(frame.chosen.apply(lambda x:s in x).sum()) for s in SYMBOLS}
    excess=frame.net25-frame.ew
    worst_trim=frame.loc[excess.nlargest(5).index]
    trimmed=frame.drop(index=worst_trim.index).reset_index(drop=True)
    result={'schema':'research.crossasset_composite_regime_attribution_r1','source_sha256':base.source_hash(close),'window':{'start':frame.iloc[0].return_month,'end':frame.iloc[-1].return_month,'months':len(frame)},'selection_counts':selection,'conditional':conditional_metrics(frame),'full':{'candidate':base.metrics(frame.net25),'ew':base.metrics(frame.ew),'spy':base.metrics(frame.spy),'qqq':base.metrics(frame.qqq),'excess_cagr_vs_ew':base.metrics(frame.net25)['cagr']-base.metrics(frame.ew)['cagr']},'top5_relative_months_removed':{'months_removed':worst_trim[['return_month','net25','ew']].to_dict('records'),'candidate':base.metrics(trimmed.net25),'ew':base.metrics(trimmed.ew),'excess_cagr_vs_ew':base.metrics(trimmed.net25)['cagr']-base.metrics(trimmed.ew)['cagr']},'interpretation_rule':'If matched-control edge remains positive after removing the five best relative months and is not confined to risk-off months, classify broad persistence; otherwise classify defensive/crisis concentration.'}
    c=result['conditional']; trimmed_ex=result['top5_relative_months_removed']['excess_cagr_vs_ew']
    broad = trimmed_ex>0 and c['risk_on']['mean_excess_vs_ew']>0 and c['risk_off']['mean_excess_vs_ew']>0
    result['decision']='BROAD_MATCHED_CONTROL_PERSISTENCE' if broad else 'EDGE_CONCENTRATED_REQUIRES_CAUTION'
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/crossasset_composite_regime_attribution.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'decision':result['decision'],'trimmed_excess_cagr':trimmed_ex,'risk_on_mean_excess':c['risk_on']['mean_excess_vs_ew'],'risk_off_mean_excess':c['risk_off']['mean_excess_vs_ew']},sort_keys=True))

if __name__=='__main__': main()
