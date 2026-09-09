from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p47_deep_robustness_r2 as p47
SYMS=p47.BASE; FACTORS=('mom6','trend200')
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def main():
 fr,close=p47.run(SYMS,FACTORS,0); fr=fr.loc[pd.Timestamp('2022-01-01'):]; tests={}
 for bp in (25,50):
  c=fr.gross-fr.turnover*bp/10000; active=c-fr.ew; strongest=active.nlargest(5).index; keep=~fr.index.isin(strongest)
  tests[str(bp)]={'full_excess_cagr':cagr(c)-cagr(fr.ew),'strongest_relative_months':[str(x.date()) for x in strongest],'strongest_relative_months_sum':float(active.loc[strongest].sum()),'residual_excess_cagr_after_removing_top5':cagr(c[keep])-cagr(fr.ew[keep]),'residual_months':int(keep.sum())}
 supported=tests['25']['residual_excess_cagr_after_removing_top5']>0 and tests['50']['residual_excess_cagr_after_removing_top5']>0
 out={'schema':'research.p52_recent_concentration_r1','parent':'P52','scientific_contract':{'economics':'unchanged mom6+trend200 industry top-3 monthly','window':'2022-forward','costs_bps':[25,50],'matched_control':'same-industry equal weight','falsification':'remove five strongest candidate-minus-matched months then recompute CAGR difference','no_parameter_tuning':True},'source':{'industry_panel_sha256':p47.base.source_hash(close)},'tests':tests,'decision':'P52_RECENT_ALPHA_SURVIVES_TOP5_REMOVAL' if supported else 'P52_RECENT_ALPHA_CONCENTRATED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p52_recent_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
