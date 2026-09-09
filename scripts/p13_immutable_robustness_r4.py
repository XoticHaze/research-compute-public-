from __future__ import annotations
import json
from pathlib import Path
import numpy as np

DRAWS=5000; BLOCK=12

def cagr(vals):
    x=np.asarray(vals,float); return float(np.prod(1+x)**(12/len(x))-1)

def block_bootstrap(excess, seed):
    x=np.asarray(excess,float); n=len(x); starts=np.arange(n-BLOCK+1); rng=np.random.default_rng(seed); out=[]
    for _ in range(DRAWS):
        chunks=[]; size=0
        while size<n:
            s=int(rng.choice(starts)); z=x[s:s+BLOCK]; chunks.append(z); size+=len(z)
        y=np.concatenate(chunks)[:n]; out.append(float(y.mean()*12))
    a=np.asarray(out,float); lo,hi=np.quantile(a,[.025,.975])
    return {'draws':DRAWS,'block_months':BLOCK,'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(lo),float(hi)],'p_excess_le_zero':float((a<=0).mean())}

def rolling(candidate, comp, months):
    z=[]
    for i in range(len(candidate)-months+1): z.append(cagr(candidate[i:i+months])-cagr(comp[i:i+months]))
    a=np.asarray(z,float); return {'months':months,'n':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'worst_excess_cagr':float(a.min()),'best_excess_cagr':float(a.max())}

def top_month_removal(candidate, comp, k):
    rel=np.asarray(candidate,float)-np.asarray(comp,float); keep=np.ones(len(rel),dtype=bool); keep[np.argsort(rel)[-k:]]=False
    return {'remove_top_relative_months':k,'months_remaining':int(keep.sum()),'candidate_cagr':cagr(np.asarray(candidate)[keep]),'comparator_cagr':cagr(np.asarray(comp)[keep]),'excess_cagr':cagr(np.asarray(candidate)[keep])-cagr(np.asarray(comp)[keep])}

def main():
    src=json.loads(Path('input/p13_frozen_contract_replay_r1.json').read_text()); rows=src['monthly_records']
    cand=np.asarray([r['candidate_net_50bp'] for r in rows],float)
    comps={'equal_weight':np.asarray([r['equal_weight'] for r in rows],float),'smh':np.asarray([r['smh'] for r in rows],float),'qqq':np.asarray([r['qqq'] for r in rows],float)}
    tests={}
    for j,(name,comp) in enumerate(comps.items()):
        tests[name]={
          'full_excess_cagr':cagr(cand)-cagr(comp),
          'rolling_24m':rolling(cand,comp,24),
          'rolling_36m':rolling(cand,comp,36),
          'block_bootstrap':block_bootstrap(cand-comp,1300+j),
          'remove_top_3':top_month_removal(cand,comp,3),
          'remove_top_5':top_month_removal(cand,comp,5),
        }
    matched=tests['equal_weight']; smh=tests['smh']
    supported=(matched['rolling_36m']['positive_fraction']>=.65 and matched['block_bootstrap']['p_excess_le_zero']<=.10 and matched['remove_top_5']['excess_cagr']>0 and smh['rolling_36m']['positive_fraction']>=.60 and smh['remove_top_5']['excess_cagr']>0)
    out={
      'schema':'research.p13_immutable_robustness_r4','parent':'P13',
      'hypothesis':'The frozen P13 top-3 semiconductor selector retains after-cost excess beyond a few extreme months and across contiguous windows under serial-dependence-aware uncertainty, using only its immutable monthly decision/return record.',
      'scientific_contract':{'source_run_id':34325797529,'source_artifact_id':10093700209,'selection_return_fingerprint_sha256':src['selection_return_fingerprint_sha256'],'candidate_cost_bps':50,'comparators':['eligible semiconductor equal weight','SMH','QQQ'],'rolling_windows_months':[24,36],'moving_block_months':12,'bootstrap_draws':DRAWS,'top_relative_month_removals':[3,5],'no_market_data_redownload':True,'no_parameter_tuning':True},
      'tests':tests,
      'decision':'P13_IMMUTABLE_ROBUSTNESS_SUPPORTED' if supported else 'P13_IMMUTABLE_ROBUSTNESS_WEAK'
    }
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_immutable_robustness_r4.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
