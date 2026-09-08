from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import opportunity_cross_family_stagea_capacity_allocator_20260907 as development
import opportunity_prior_alpha_blend_disjoint_family_confirmation_20260907 as disjoint

OUT=Path('opportunity_matched_alpha_memory_recency_20260907.json')
EVAL_FOLDS=(4,5,6)


def pct_rank(values):
    return development.pct_rank(values)


def last_completed_fold_pct(records, fold, alpha_field):
    symbols=sorted({r['symbol'] for r in records}); previous=fold-1; raw={}
    for symbol in symbols:
        vals=[r[alpha_field] for r in records if r['symbol']==symbol and r['fold']==previous]
        raw[symbol]=float(np.mean(vals)) if vals else 0.0
    return raw,pct_rank(raw)


def aggregate(rows):
    stock=float(np.prod([1+r['stock_return'] for r in rows])-1)
    etf=float(np.prod([1+r['matched_etf_return'] for r in rows])-1)
    qqq=float(np.prod([1+r['qqq_return'] for r in rows])-1)
    return {'compound_stock_return':stock,'compound_matched_etf_return':etf,'compound_qqq_return':qqq,'compound_stock_minus_matched_etf':stock-etf,'compound_stock_minus_qqq':stock-qqq,'accepted_trades':sum(r['accepted_trades'] for r in rows),'fold_stock_returns':[r['stock_return'] for r in rows],'fold_matched_excess':[r['stock_minus_matched_etf_return'] for r in rows]}


def evaluate_development(mod,contract):
    calendar,_,families,records=development.build_records(mod,contract)
    symbols=sorted({r['symbol'] for r in records}); folds=[]
    for fold in EVAL_FOLDS:
        cumulative,_=development.prior_symbol_alpha(records,fold,symbols); cumulative_pct=pct_rank(cumulative)
        last_raw,last_pct=last_completed_fold_pct(records,fold,'stock_minus_etf_bps')
        folds.append({'fold':fold,'last_completed_fold':fold-1,'last_fold_symbol_alpha_bps':last_raw,'raw_prediction':development.simulate(records,fold,'global_raw_prediction',{}),'cumulative_memory':development.simulate(records,fold,'prior_alpha_blend',cumulative_pct),'last_fold_memory':development.simulate(records,fold,'prior_alpha_blend',last_pct)})
    return {'surface':'homebuilders_plus_biotech','families':families,'calendar_rows':len(calendar),'candidate_primary_states':len(records),'folds':folds}


def evaluate_disjoint(mod):
    calendar,records=disjoint.build_records(mod); folds=[]
    for fold in EVAL_FOLDS:
        _,cumulative_pct=disjoint.prior_alpha(records,fold)
        last_raw,last_pct=last_completed_fold_pct(records,fold,'matched_excess_bps')
        folds.append({'fold':fold,'last_completed_fold':fold-1,'last_fold_symbol_alpha_bps':last_raw,'raw_prediction':disjoint.simulate(records,fold,'raw_prediction',cumulative_pct),'cumulative_memory':disjoint.simulate(records,fold,'prior_alpha_blend',cumulative_pct),'last_fold_memory':disjoint.simulate(records,fold,'prior_alpha_blend',last_pct)})
    return {'surface':'consumer_staples_metals_reits_pharma','families':disjoint.FAMILIES,'calendar_rows':len(calendar),'candidate_primary_states':len(records),'folds':folds}


def summarize(surface):
    ag={policy:aggregate([f[policy] for f in surface['folds']]) for policy in ('raw_prediction','cumulative_memory','last_fold_memory')}
    last=ag['last_fold_memory']; raw=ag['raw_prediction']; cumulative=ag['cumulative_memory']
    fold_wins_raw=sum(f['last_fold_memory']['stock_return']>f['raw_prediction']['stock_return'] for f in surface['folds'])
    fold_wins_cumulative=sum(f['last_fold_memory']['stock_return']>f['cumulative_memory']['stock_return'] for f in surface['folds'])
    positive_excess=sum(f['last_fold_memory']['stock_minus_matched_etf_return']>0 for f in surface['folds'])
    supported=bool(last['compound_stock_return']>raw['compound_stock_return'] and last['compound_stock_minus_matched_etf']>0 and last['compound_stock_minus_matched_etf']>raw['compound_stock_minus_matched_etf'] and fold_wins_raw>=2 and positive_excess>=2 and last['accepted_trades']>=0.70*raw['accepted_trades'])
    return {'aggregate':ag,'gate':{'last_memory_fold_wins_vs_raw':fold_wins_raw,'last_memory_fold_wins_vs_cumulative':fold_wins_cumulative,'last_memory_positive_matched_excess_folds':positive_excess,'decision':'RECENCY_SUPPORTED_ON_SURFACE' if supported else 'RECENCY_NOT_SUPPORTED_ON_SURFACE'}}


def main():
    mod=development.load_adapter(); contract=json.loads(Path('.campaign/stagea_contract.json').read_text())
    surfaces=[evaluate_development(mod,contract),evaluate_disjoint(mod)]
    for s in surfaces: s.update(summarize(s))
    both=all(s['gate']['decision']=='RECENCY_SUPPORTED_ON_SURFACE' for s in surfaces)
    out={'schema':'public_research.opportunity_matched_alpha_memory_recency.v1','research_only':True,'parent_observation':'Cumulative prior-fold matched-alpha memory strongly improved the original Homebuilder/Biotech allocator but failed cross-family confirmation because positive matched-ETF excess was concentrated in one of three folds.','question':'Is stale cumulative history the problem? Replace only the memory horizon with the immediately completed fold while preserving the frozen 50/50 current-score/matched-alpha blend and capacity-3 shape.','frozen_architecture':{'current_score_weight':0.5,'matched_alpha_weight':0.5,'capacity':3,'memory_challenger':'immediately completed fold only','cumulative_memory_control':'all completed prior folds','parameter_search':False},'evaluation_folds':list(EVAL_FOLDS),'surfaces':surfaces,'decision':'RECENCY_MEMORY_ARCHITECTURE_SUPPORTED' if both else 'RECENCY_MEMORY_ARCHITECTURE_NOT_SUPPORTED','next_boundary':'If supported on both surfaces, test unchanged memory architecture on a truly forward/unseen opportunity batch before product promotion. If not, retain matched-alpha history as research context rather than tuning memory horizon.','external_holdouts_loaded':False,'allocation_runtime_authority':False,'strategy_spec_mutation':False,'promotion_authority':False,'broker_action':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n'); print('OPPORTUNITY_MATCHED_ALPHA_MEMORY_RECENCY='+json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
