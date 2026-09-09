from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p57_crossasset_parsimonious_r1 as p57
import p47_deep_robustness_r2 as p47

IND=("SOXX","XBI","XHB","KRE","ITA","IGV","IYT","XRT","XOP","IHI"); FACTORS=("mom6","trend200")
COMPONENT_BP=50; GATE_COSTS=(25,50)
WINDOWS={'2015_forward':'2015-01-01','2020_forward':'2020-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')
def folds(a,b):
    out=[]
    for i,ids in enumerate(np.array_split(np.arange(len(a)),5),1):
        x=a.iloc[ids]; y=b.iloc[ids]; out.append({'fold':i,'excess_cagr':cagr(x)-cagr(y)})
    return out

def build():
    cr,cc=p57.run(0); ir,ic=p47.run(IND,FACTORS,0)
    last=min(pd.Timestamp(cc.index.max()).tz_localize(None) if pd.Timestamp(cc.index.max()).tzinfo else pd.Timestamp(cc.index.max()),pd.Timestamp(ic.index.max()).tz_localize(None) if pd.Timestamp(ic.index.max()).tzinfo else pd.Timestamp(ic.index.max()))
    cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); cr=cr.loc[cr.index<=cutoff]; ir=ir.loc[ir.index<=cutoff]; idx=cr.index.intersection(ir.index)
    f=pd.DataFrame(index=idx)
    f['p64']=.5*(cr.loc[idx].gross-cr.loc[idx].turnover*COMPONENT_BP/10000)+.5*(ir.loc[idx].gross-ir.loc[idx].turnover*COMPONENT_BP/10000)
    f['matched']=.5*cr.loc[idx].ew+.5*ir.loc[idx].ew
    qm=cc.QQQ.resample('ME').last().reindex(idx); f['qqq']=qm.pct_change()
    qtrend=(cc.QQQ/cc.QQQ.rolling(200,min_periods=160).mean()).resample('ME').last().reindex(idx)
    # Return labeled t is selected using only state observed at t-1 month-end.
    f['prior_qqq_below_200d']=(qtrend.shift(1)<=1).astype(float)
    return f.dropna(),cc,ic,cutoff

def evaluate(q,gate_bp):
    active=q.prior_qqq_below_200d.astype(float)
    # Full allocation switches between frozen P64 and QQQ. Charge explicit gate switching cost.
    turn=active.diff().abs().fillna(active.iloc[0])
    gate=active*q.p64+(1-active)*q.qqq-turn*gate_bp/10000
    gate_matched=active*q.matched+(1-active)*q.qqq-turn*gate_bp/10000
    fg=folds(gate,q.qqq); fm=folds(gate,gate_matched); fu=folds(gate,q.p64)
    return {'months':len(q),'active_p64_fraction':float(active.mean()),'gate_switches':int((turn>0).sum()),'gate_cagr':cagr(gate),'gated_matched_cagr':cagr(gate_matched),'ungated_p64_cagr':cagr(q.p64),'qqq_cagr':cagr(q.qqq),'gate_mdd':mdd(gate),'gated_matched_mdd':mdd(gate_matched),'ungated_p64_mdd':mdd(q.p64),'qqq_mdd':mdd(q.qqq),'excess_vs_gated_matched':cagr(gate)-cagr(gate_matched),'excess_vs_ungated_p64':cagr(gate)-cagr(q.p64),'excess_vs_qqq':cagr(gate)-cagr(q.qqq),'positive_folds_vs_gated_matched':sum(x['excess_cagr']>0 for x in fm),'positive_folds_vs_ungated_p64':sum(x['excess_cagr']>0 for x in fu),'positive_folds_vs_qqq':sum(x['excess_cagr']>0 for x in fg),'folds_vs_gated_matched':fm,'folds_vs_ungated_p64':fu,'folds_vs_qqq':fg}

def main():
    f,cc,ic,cutoff=build(); out={'schema':'research.p64_exante_qqq200d_gate_r1','parent':'P64','hypothesis':'The state association in P64 opportunity-cost attribution is causally usable: invest the frozen P64 blend next month only when prior month-end QQQ is at/below its trailing 200-session mean, otherwise hold QQQ.','scientific_contract':{'component_cost_bps':COMPONENT_BP,'gate_switch_costs_bps':list(GATE_COSTS),'sleeve_weights':[.5,.5],'gate':'prior month-end QQQ <= trailing 200-session mean selects P64 for next return month; otherwise QQQ','matched_control':'same causal gate applied to P64 matched-control blend versus QQQ','other_controls':['ungated P64','QQQ'],'windows':WINDOWS,'chronological_folds':5,'complete_months_only':True,'no_factor_weight_lookback_or_threshold_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_panel_sha256':base.source_hash(cc),'industry_panel_sha256':base.source_hash(ic),'last_complete_month_end':str(cutoff.date())}}
    for name,start in WINDOWS.items():
        q=f.loc[pd.Timestamp(start):]
        out['tests'][name]={str(bp):evaluate(q,bp) for bp in GATE_COSTS}
    t=out['tests']['2020_forward']['50']; out['decision']='P64_EXANTE_REGIME_GATE_SUPPORTED' if t['excess_vs_gated_matched']>0 and t['excess_vs_qqq']>0 and t['positive_folds_vs_qqq']>=3 else 'P64_EXANTE_REGIME_GATE_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_exante_qqq200d_gate_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
