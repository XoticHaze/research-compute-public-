from __future__ import annotations
import json
from pathlib import Path
import numpy as np

LOOKBACK=6


def cagr(x):
    a=np.asarray(x,float)
    return float(np.prod(1+a)**(12/len(a))-1) if len(a) else float('nan')


def summarize(rows, ids):
    ids=np.asarray(ids,int)
    c=np.asarray([rows[i]['candidate_net_50bp'] for i in ids],float)
    ew=np.asarray([rows[i]['equal_weight'] for i in ids],float)
    smh=np.asarray([rows[i]['smh'] for i in ids],float)
    qqq=np.asarray([rows[i]['qqq'] for i in ids],float)
    return {'months':int(len(ids)),'candidate_cagr':cagr(c),'equal_weight_cagr':cagr(ew),'smh_cagr':cagr(smh),'qqq_cagr':cagr(qqq),'excess_vs_equal_weight_cagr':cagr(c)-cagr(ew),'excess_vs_smh_cagr':cagr(c)-cagr(smh),'excess_vs_qqq_cagr':cagr(c)-cagr(qqq),'mean_monthly_excess_vs_equal_weight':float(np.mean(c-ew)),'mean_monthly_excess_vs_smh':float(np.mean(c-smh))}


def main():
    src=json.loads(Path('input/p13_frozen_contract_replay_r1.json').read_text()); rows=src['monthly_records']
    smh=np.asarray([r['smh'] for r in rows],float)
    states=[]
    for i in range(LOOKBACK,len(rows)):
        trailing=float(np.prod(1+smh[i-LOOKBACK:i])-1)
        states.append((i,trailing>0,trailing))
    pos=[i for i,s,_ in states if s]; nonpos=[i for i,s,_ in states if not s]
    by_state={'prior_6m_smh_positive':summarize(rows,pos),'prior_6m_smh_nonpositive':summarize(rows,nonpos)}
    all_ids=[i for i,_,_ in states]
    full=summarize(rows,all_ids)
    years=sorted(set(int(rows[i]['signal_date'][:4]) for i in all_ids))
    yearly={}
    for y in years:
        ids=[i for i,_,_ in states if int(rows[i]['signal_date'][:4])==y]
        yearly[str(y)]=summarize(rows,ids)
    pos_edge=by_state['prior_6m_smh_positive']['mean_monthly_excess_vs_equal_weight']
    neg_edge=by_state['prior_6m_smh_nonpositive']['mean_monthly_excess_vs_equal_weight']
    state='P13_PRIOR_SMH_STATE_DISCRIMINATES_MATCHED_ALPHA' if pos_edge>0 and pos_edge>neg_edge else 'P13_PRIOR_SMH_STATE_DOES_NOT_DISCRIMINATE_MATCHED_ALPHA'
    out={'schema':'research.p13_prior_smh_state_r6','parent':'P13','hypothesis':'The R5 realized-regime asymmetry has a causal antecedent: P13 matched excess is stronger when the prior six completed SMH months have positive compounded return than when they do not.','scientific_contract':{'source_run_id':34325797529,'source_artifact_id':10093700209,'selection_return_fingerprint_sha256':src['selection_return_fingerprint_sha256'],'candidate_cost_bps':50,'state_definition':'sign of compounded SMH return over the six completed outcome months strictly preceding each signal month','lookback_months':LOOKBACK,'no_current_or_future_month_used_in_state':True,'attribution_only_no_new_trading_filter':True,'no_market_data_redownload':True,'no_parameter_or_state_search':True},'full_after_warmup':full,'by_prior_state':by_state,'yearly_after_warmup':yearly,'state_counts':{'positive':len(pos),'nonpositive':len(nonpos)},'decision':state,'interpretation_rule':'This is a causal-state attribution test only. Even a positive result does not authorize gating P13; exact gate turnover/costs plus independent or forward validation are required before treating the state as an executable conditional model.'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_prior_smh_state_r6.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
