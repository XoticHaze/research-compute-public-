from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def main():
 close=base.load(p46.SYMBOLS); fr=p46.returns(close,p46.FACTORS); q=close['QQQ'].resample('ME').last().pct_change().reindex(fr.index); tests={}
 for label,ix in [('full',fr.index),('2022_forward',fr.loc[pd.Timestamp('2022-01-01'):].index)]:
  sub=fr.loc[ix]; qq=q.loc[ix]; tests[label]={}
  for bp in (25,50):
   p46net=sub.gross-sub.turnover*bp/10000; candidate=.5*p46net+.5*qq; matched=.5*sub.ew+.5*qq; active=candidate-matched; strongest=active.nlargest(5).index; keep=~candidate.index.isin(strongest)
   tests[label][str(bp)]={'full_incremental_excess_cagr':cagr(candidate)-cagr(matched),'top5_relative_months':[str(x.date()) for x in strongest],'top5_relative_sum':float(active.loc[strongest].sum()),'residual_incremental_excess_cagr':cagr(candidate[keep])-cagr(matched[keep]),'residual_months':int(keep.sum())}
 f25=tests['full']['25']; f50=tests['full']['50']; r25=tests['2022_forward']['25']; supported=f25['residual_incremental_excess_cagr']>0 and f50['residual_incremental_excess_cagr']>0 and r25['residual_incremental_excess_cagr']>0
 out={'schema':'research.p46_qqq_blend_concentration_r1','parent':'P46','scientific_contract':{'candidate':'fixed research-only 50% P46 + 50% QQQ','matched_control':'50% same-universe equal weight + 50% QQQ','costs_bps_on_p46_sleeve':[25,50],'falsification':'remove five strongest candidate-minus-matched months and recompute CAGR difference','windows':['full','2022-forward'],'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'normalized_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_QQQ_BLEND_INCREMENTAL_ALPHA_SURVIVES_TOP5_REMOVAL' if supported else 'P46_QQQ_BLEND_INCREMENTAL_ALPHA_CONCENTRATED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_qqq_blend_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
