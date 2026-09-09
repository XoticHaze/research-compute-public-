from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(idx); s=monthly['SPY'].pct_change().reindex(idx); tests={}
    for bp in (25,50,100):
        cand=.5*(a.gross-a.turnover*bp/10000)+.5*(b.gross-b.turnover*bp/10000); matched=.5*a.ew+.5*b.matched; active=cand-matched
        qcut=float(q.quantile(.1)); mcut=float(matched.quantile(.1)); worstq=q<=qcut; worstm=matched<=mcut
        tests[str(bp)]={
            'worst_QQQ_decile':{'threshold':qcut,'months':int(worstq.sum()),'candidate_mean':float(cand[worstq].mean()),'matched_mean':float(matched[worstq].mean()),'QQQ_mean':float(q[worstq].mean()),'SPY_mean':float(s[worstq].mean()),'active_mean':float(active[worstq].mean()),'candidate_positive_fraction':float((cand[worstq]>0).mean())},
            'worst_matched_decile':{'threshold':mcut,'months':int(worstm.sum()),'candidate_mean':float(cand[worstm].mean()),'matched_mean':float(matched[worstm].mean()),'QQQ_mean':float(q[worstm].mean()),'SPY_mean':float(s[worstm].mean()),'active_mean':float(active[worstm].mean()),'candidate_positive_fraction':float((cand[worstm]>0).mean())},
            'all_months':{'candidate_mean':float(cand.mean()),'matched_mean':float(matched.mean()),'active_mean':float(active.mean())}
        }
    f=tests['50']; supported=f['worst_QQQ_decile']['active_mean']>=0 and f['worst_matched_decile']['active_mean']>=0
    out={'schema':'research.p46_p36_tail_robustness_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'exact blended matched control','tail_definition':['worst decile of QQQ monthly returns','worst decile of matched-control monthly returns'],'costs_bps_per_sleeve':[25,50,100],'incomplete_months_excluded':True,'no_parameter_or_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_DOWNSIDE_TAIL_ALPHA_SUPPORTED' if supported else 'P46_P36_DOWNSIDE_TAIL_ALPHA_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_tail_robustness_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'test50':tests['50']},sort_keys=True))
if __name__=='__main__': main()
