from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def rolling(c,b,n=60):
 a=np.array([cagr(c.iloc[i-n:i])-cagr(b.iloc[i-n:i]) for i in range(n,len(c)+1)]); return {'windows':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1))}
def main():
 close=base.load(p46.SYMBOLS); fr=p46.returns(close,p46.FACTORS); q=close['QQQ'].resample('ME').last().pct_change().reindex(fr.index); tests={}
 for label,ix in [('full',fr.index),('2022_forward',fr.loc[pd.Timestamp('2022-01-01'):].index)]:
  sub=fr.loc[ix]; qq=q.loc[ix]; tests[label]={}
  for bp in (25,50,100):
   p46net=sub.gross-sub.turnover*bp/10000; candidate=.5*p46net+.5*qq; matched=.5*sub.ew+.5*qq; cm,bm,qm=base.metrics(candidate),base.metrics(matched),base.metrics(qq); pos,folds=base.fold_count(candidate,matched)
   tests[label][str(bp)]={'candidate':cm,'matched_50qqq_50ew':bm,'QQQ':qm,'incremental_excess_cagr':cm['cagr']-bm['cagr'],'excess_vs_QQQ_cagr':cm['cagr']-qm['cagr'],'positive_folds_vs_matched':pos,'folds':folds,'rolling60_vs_matched':rolling(candidate,matched) if len(candidate)>=60 else None}
 f50=tests['full']['50']; r50=tests['2022_forward']['50']; supported=f50['incremental_excess_cagr']>0 and f50['rolling60_vs_matched']['positive_fraction']>=.6 and r50['incremental_excess_cagr']>0
 out={'schema':'research.p46_qqq_incremental_blend_r1','parent':'P46','scientific_contract':{'candidate':'fixed research-only 50% P46 + 50% QQQ','matched_control':'50% same-universe equal weight + 50% QQQ','opportunity_control':'QQQ','costs_bps_on_p46_sleeve':[25,50,100],'holdout':'2022-forward','no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_INCREMENTAL_DIVERSIFIER_SUPPORTED' if supported else 'P46_INCREMENTAL_DIVERSIFIER_NOT_SUPPORTED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_qqq_incremental_blend_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'full50':f50,'recent50':r50},sort_keys=True))
if __name__=='__main__': main()
