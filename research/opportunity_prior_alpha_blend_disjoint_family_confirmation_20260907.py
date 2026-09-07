from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ADAPTER = Path('.campaign/stagea.py')
OUT = Path('opportunity_prior_alpha_blend_disjoint_family_confirmation_20260907.json')
CAPACITY = 3
EVAL_FOLDS = (4, 5, 6)
STOCK_COST_BPS = 25.0
ETF_COST_BPS = 10.0
FAMILIES = {
    'consumer_staples': {'primary_industry_etf': 'XLP', 'development_universe': ['PG','KO','PEP','PM','MO','CL','KMB','GIS']},
    'metals_mining': {'primary_industry_etf': 'XME', 'development_universe': ['NEM','FCX','SCCO','NUE','STLD','CLF','AA','CENX']},
    'reits': {'primary_industry_etf': 'VNQ', 'development_universe': ['AMT','PLD','O','SPG','EQIX','PSA','WELL','DLR']},
    'pharma': {'primary_industry_etf': 'PPH', 'development_universe': ['LLY','MRK','PFE','BMY','ABBV','JNJ','AMGN','AZN']},
}


def load_adapter():
    spec=importlib.util.spec_from_file_location('stagea',ADAPTER)
    if spec is None or spec.loader is None: raise RuntimeError('cannot load adapter')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def pct_rank(values):
    keys=list(values)
    if not keys: return {}
    vals=pd.Series([values[k] for k in keys],index=keys,dtype=float)
    return vals.rank(method='average',pct=True).to_dict()


def build_records(mod):
    cutoff=pd.Timestamp('2026-09-01T13:30:00+00:00')
    symbols=[]; family_of={}
    for family,spec in FAMILIES.items():
        for s in spec['development_universe']:
            if s in family_of: raise RuntimeError(f'duplicate {s}')
            symbols.append(s); family_of[s]=family
    raw={s:mod._bounded(s,cutoff) for s in (*mod.TRAIN,*symbols,'QQQ')}
    calendar=pd.DatetimeIndex(sorted(set.intersection(*[set(x.timestamp) for x in raw.values()])))
    if len(calendar)<1500 or calendar[-1]!=cutoff: raise RuntimeError(f'invalid common calendar rows={len(calendar)} last={calendar[-1] if len(calendar) else None}')
    prices={s:raw[s].set_index('timestamp').price.reindex(calendar) for s in raw}
    if any(x.isna().any() for x in prices.values()): raise RuntimeError('missing selection price')
    benchmarks={}
    for family,spec in FAMILIES.items():
        series=mod._bounded(spec['primary_industry_etf'],cutoff).set_index('timestamp').price.reindex(calendar)
        if series.isna().any(): raise RuntimeError(f'{family} benchmark missing')
        benchmarks[family]=series
    data=mod._engineer(prices,calendar,(*mod.TRAIN,*symbols))
    folds=mod._global_folds(len(calendar))
    train_states=mod._state_frame(mod.TRAIN,data,folds)
    test_states=mod._state_frame(tuple(symbols),data,folds)
    records=[]
    for fold in range(mod.EVAL_FIRST_FOLD,mod.FOLDS+1):
        start,_=folds[fold-1]
        train=train_states[train_states.signal_i < start-mod.PURGE]
        model=mod._fit(train)
        for s in symbols:
            family=family_of[s]
            test=test_states[(test_states.symbol==s)&(test_states.fold==fold)].copy()
            pred=model.predict(test[mod.FEATURES].to_numpy(float)); test['prediction_bps']=pred
            chosen=test[test.prediction_bps>0].copy()
            prior=data[s].iloc[:start-mod.PURGE].mom20.dropna()
            if len(prior)<250: raise RuntimeError(f'{s} insufficient threshold support')
            threshold=float(prior.quantile(1.0-mod.TAIL)); primary=chosen[chosen.mom20<threshold]
            for row in primary.itertuples(index=False):
                signal_i=int(row.signal_i); entry_i=signal_i+mod.DELAY; exit_i=entry_i+mod.HOLD
                stock=float(prices[s].iloc[exit_i]/prices[s].iloc[entry_i]-1.0)
                etf=float(benchmarks[family].iloc[exit_i]/benchmarks[family].iloc[entry_i]-1.0)
                qqq=float(prices['QQQ'].iloc[exit_i]/prices['QQQ'].iloc[entry_i]-1.0)
                records.append({'fold':fold,'family':family,'symbol':s,'entry_i':entry_i,'exit_i':exit_i,'prediction_bps':float(row.prediction_bps),'stock_net':stock-STOCK_COST_BPS/10000.0,'etf_net':etf-ETF_COST_BPS/10000.0,'qqq_net':qqq-ETF_COST_BPS/10000.0,'matched_excess_bps':(stock-STOCK_COST_BPS/10000.0-etf)*10000.0})
    return calendar,records


def prior_alpha(records,before_fold):
    symbols=sorted({r['symbol'] for r in records}); raw={}
    for s in symbols:
        vals=[r['matched_excess_bps'] for r in records if r['symbol']==s and r['fold']<before_fold]
        raw[s]=float(np.mean(vals)) if vals else 0.0
    return raw,pct_rank(raw)


def simulate(records,fold,policy,alpha_pct):
    day=defaultdict(list)
    for r in records:
        if r['fold']==fold: day[r['entry_i']].append(r)
    slots=[{'stock':1/CAPACITY,'etf':1/CAPACITY,'qqq':1/CAPACITY,'record':None,'exit_i':-1} for _ in range(CAPACITY)]
    accepted=[]
    def realize(i):
        for slot in slots:
            r=slot['record']
            if r is not None and slot['exit_i']<=i:
                slot['stock']*=1+r['stock_net']; slot['etf']*=1+r['etf_net']; slot['qqq']*=1+r['qqq_net']; slot['record']=None; slot['exit_i']=-1
    for entry_i in sorted(day):
        realize(entry_i); free=[s for s in slots if s['record'] is None]
        if not free: continue
        active={s['record']['symbol'] for s in slots if s['record'] is not None}
        candidates=day[entry_i]
        if policy=='raw_prediction':
            ordered=sorted(candidates,key=lambda r:(-r['prediction_bps'],r['family'],r['symbol']))
        elif policy=='prior_alpha_blend':
            pp=pct_rank({str(i):r['prediction_bps'] for i,r in enumerate(candidates)})
            scored=[(0.5*pp[str(i)]+0.5*alpha_pct.get(r['symbol'],0.5),r) for i,r in enumerate(candidates)]
            ordered=[r for _,r in sorted(scored,key=lambda x:(-x[0],-x[1]['prediction_bps'],x[1]['family'],x[1]['symbol']))]
        else: raise RuntimeError(policy)
        for r in ordered:
            if not free: break
            if r['symbol'] in active: continue
            slot=free.pop(0); slot['record']=r; slot['exit_i']=r['exit_i']; active.add(r['symbol']); accepted.append(r)
    realize(10**9)
    sw=float(sum(s['stock'] for s in slots)); ew=float(sum(s['etf'] for s in slots)); qw=float(sum(s['qqq'] for s in slots))
    counts=defaultdict(int)
    for r in accepted: counts[r['family']]+=1
    return {'stock_return':sw-1,'matched_etf_return':ew-1,'qqq_return':qw-1,'stock_minus_matched_etf_return':sw-ew,'stock_minus_qqq_return':sw-qw,'accepted_trades':len(accepted),'family_trade_counts':dict(sorted(counts.items()))}


def main():
    mod=load_adapter(); calendar,records=build_records(mod)
    folds=[]
    for fold in EVAL_FOLDS:
        raw_alpha,alpha_pct=prior_alpha(records,fold)
        folds.append({'fold':fold,'prior_folds':list(range(mod.EVAL_FIRST_FOLD,fold)),'prior_symbol_matched_alpha_bps':raw_alpha,'raw_prediction':simulate(records,fold,'raw_prediction',alpha_pct),'prior_alpha_blend':simulate(records,fold,'prior_alpha_blend',alpha_pct)})
    def agg(policy):
        rows=[x[policy] for x in folds]; sw=float(np.prod([1+r['stock_return'] for r in rows])-1); ew=float(np.prod([1+r['matched_etf_return'] for r in rows])-1); qw=float(np.prod([1+r['qqq_return'] for r in rows])-1)
        return {'compound_stock_return':sw,'compound_matched_etf_return':ew,'compound_qqq_return':qw,'compound_stock_minus_matched_etf':sw-ew,'compound_stock_minus_qqq':sw-qw,'accepted_trades':sum(r['accepted_trades'] for r in rows),'fold_stock_returns':[r['stock_return'] for r in rows],'fold_matched_excess':[r['stock_minus_matched_etf_return'] for r in rows]}
    control=agg('raw_prediction'); challenger=agg('prior_alpha_blend')
    fold_wins=sum(x['prior_alpha_blend']['stock_return']>x['raw_prediction']['stock_return'] for x in folds)
    excess_folds=sum(x['prior_alpha_blend']['stock_minus_matched_etf_return']>0 for x in folds)
    supported=bool(challenger['compound_stock_return']>control['compound_stock_return'] and challenger['compound_stock_minus_matched_etf']>0 and challenger['compound_stock_minus_matched_etf']>control['compound_stock_minus_matched_etf'] and fold_wins>=2 and excess_folds>=2 and challenger['accepted_trades']>=0.70*control['accepted_trades'])
    out={'schema':'public_research.opportunity_prior_alpha_blend_disjoint_family_confirmation.v1','research_only':True,'architecture_frozen_from_run':34109147314,'architecture':'50% current cross-sectional shared-model prediction percentile + 50% ticker matched-industry-ETF alpha percentile from completed prior folds; capacity 3','confirmation_families':FAMILIES,'selection_reason':'entire pre-existing Stage-A Batch-3 four-family surface selected without inspecting this mechanism on those families','candidate_primary_states':len(records),'selection_calendar':{'rows':len(calendar),'first':calendar[0].isoformat(),'last':calendar[-1].isoformat()},'evaluation_folds':list(EVAL_FOLDS),'folds':folds,'aggregate':{'raw_prediction':control,'prior_alpha_blend':challenger},'gate':{'fold_wins_vs_raw':fold_wins,'positive_matched_etf_excess_folds':excess_folds,'decision':'CONFIRMED' if supported else 'NOT_CONFIRMED'},'external_holdouts_loaded':False,'threshold_search':False,'hyperparameter_search':False,'allocation_runtime_authority':False,'strategy_spec_mutation':False,'promotion_authority':False,'broker_action':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n'); print('OPPORTUNITY_PRIOR_ALPHA_BLEND_DISJOINT_CONFIRMATION='+json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
