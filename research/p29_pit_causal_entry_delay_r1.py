#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pitindex
import p29_pit_p28_independent_validation_20260908 as base

DELAYS=(1,3,5)
COSTS=(25,50,100)
MONTHS=pd.date_range('2005-01-31','2026-08-31',freq='ME')
RECENT=pd.Timestamp('2022-01-01')

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else None

def stats(frame):
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(len(frame)),5),1):
        q=frame.iloc[ids]
        folds.append({'fold':i,'start':q.index.min().date().isoformat(),'end':q.index.max().date().isoformat(),'excess_vs_pit_ew_cagr':cagr(q.net)-cagr(q.pit_ew),'excess_vs_smh_cagr':cagr(q.net)-cagr(q.smh)})
    return {'months':int(len(frame)),'candidate_cagr':cagr(frame.net),'pit_ew_cagr':cagr(frame.pit_ew),'smh_cagr':cagr(frame.smh),'excess_vs_pit_ew_cagr':cagr(frame.net)-cagr(frame.pit_ew),'excess_vs_smh_cagr':cagr(frame.net)-cagr(frame.smh),'positive_folds_vs_pit_ew':sum(x['excess_vs_pit_ew_cagr']>0 for x in folds),'positive_folds_vs_smh':sum(x['excess_vs_smh_cagr']>0 for x in folds),'folds':folds}

def main():
    snapshots={}; universe=set()
    for date in MONTHS:
        df=pitindex.get_constituents(date.date().isoformat(),index='sp500')
        mask=df['gics_sub_industry'].fillna('').str.contains('Semiconductor',case=False,regex=False)
        tickers=sorted(set(df.loc[mask,'ticker'].astype(str)))
        snapshots[date]=tickers; universe.update(tickers)
    daily={}; prov={}; failed={}
    for sym in sorted(universe|{'SMH'}):
        s,p=base.fetch(sym)
        if s is None: failed[sym]=p
        else: daily[sym]=s; prov[sym]=p
    monthly={k:v.resample('ME').last() for k,v in daily.items()}
    result={'schema':'research.p29_pit_causal_entry_delay_r1','parent':'P29','scientific_contract':{'parent_rule':'point-in-time S&P500 semiconductor membership; prior-6-month momentum; top3 equal weight','entry_exit_delays_trading_days':list(DELAYS),'costs_bps':list(COSTS),'matched_control':'same eligible PIT semiconductor equal-weight over identical delayed entry/exit intervals','secondary_control':'SMH over identical delayed intervals','point_in_time_provider':'pitindex','point_in_time_commit':base.PIT_COMMIT,'no_parameter_or_topk_tuning':True},'source':{'successful':prov,'failed':failed},'tests':{}}
    for delay in DELAYS:
        raw=[]; prev=set()
        for date in MONTHS[:-1]:
            nxt=date+pd.offsets.MonthEnd(1); prior=date-pd.offsets.MonthEnd(6)
            members=snapshots[date]; eligible=[]; mom={}; shifted_ret={}
            for sym in members:
                ds=daily.get(sym); ms=monthly.get(sym)
                if ds is None or ms is None or date not in ms.index or prior not in ms.index: continue
                a=ds.index.get_indexer([date],method='pad')[0]+delay; z=ds.index.get_indexer([nxt],method='pad')[0]+delay
                if a<0 or z<0 or a>=len(ds) or z>=len(ds): continue
                if pd.isna(ms.loc[date]) or pd.isna(ms.loc[prior]): continue
                eligible.append(sym); mom[sym]=float(ms.loc[date]/ms.loc[prior]-1); shifted_ret[sym]=float(ds.iloc[z]/ds.iloc[a]-1)
            smh=daily.get('SMH')
            if len(eligible)<4 or smh is None: continue
            sa=smh.index.get_indexer([date],method='pad')[0]+delay; sz=smh.index.get_indexer([nxt],method='pad')[0]+delay
            if sa<0 or sz<0 or sa>=len(smh) or sz>=len(smh): continue
            chosen=sorted(eligible,key=lambda x:(-mom[x],x))[:3]; chosen_set=set(chosen)
            gross=float(np.mean([shifted_ret[x] for x in chosen])); ew=float(np.mean([shifted_ret[x] for x in eligible])); smhr=float(smh.iloc[sz]/smh.iloc[sa]-1)
            turn=1.0 if not prev else 1-len(prev&chosen_set)/3.0; prev=chosen_set
            raw.append({'date':date,'gross':gross,'pit_ew':ew,'smh':smhr,'turn':turn,'members':len(members),'eligible':len(eligible),'coverage':len(eligible)/len(members) if members else 0.0})
        base_frame=pd.DataFrame(raw).set_index('date')
        result['tests'][str(delay)]={}
        for bp in COSTS:
            f=base_frame.copy(); f['net']=f.gross-f.turn*bp/10000.0
            result['tests'][str(delay)][str(bp)]={'full':stats(f),'2022_forward':stats(f.loc[f.index>=RECENT]),'coverage':{'median':float(f.coverage.median()),'p10':float(f.coverage.quantile(.1)),'months_ge_80pct':int((f.coverage>=.8).sum()),'months':int(len(f))}}
    p=result['tests']['1']['50']; q=result['tests']['3']['50']; ok=p['full']['excess_vs_pit_ew_cagr']>0 and p['full']['positive_folds_vs_pit_ew']>=3 and p['2022_forward']['excess_vs_pit_ew_cagr']>0 and q['full']['excess_vs_pit_ew_cagr']>0
    result['decision']='P29_PIT_CAUSAL_DELAY_SUPPORTED' if ok else 'P29_PIT_CAUSAL_DELAY_WEAK'
    Path('p29_pit_causal_entry_delay_r1.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':result['decision'],'delay1_50':p,'delay3_50':q},sort_keys=True))
if __name__=='__main__': main()
