from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p273_industry_capital_role_cost_stress_r1 as p273

BLOCKS={'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
out={}
for name,(start,end) in BLOCKS.items():
 q=p273.x.loc[p273.x.index>=pd.Timestamp(start)].copy()
 if end: q=q.loc[q.index<=pd.Timestamp(end)]
 full=p273.ep((q.sv+q.p64+q.p36+q.ind)/4,p273.SV_BP/4)
 matched=p273.ep((q.svm+q.p64m+q.p36m+q.indm)/4,p273.SV_BP/4)
 base=p273.ep((q.sv+q.p64+q.p36)/3,p273.SV_BP/3)
 fm,mm,bm=p273.metrics(full),p273.metrics(matched),p273.metrics(base)
 out[name]={'months':len(q),'equal_four':fm,'matched_equal_four':mm,'p249_base':bm,'matched_excess_cagr':fm['cagr']-mm['cagr'],'industry_addition_cagr_delta':fm['cagr']-bm['cagr'],'industry_addition_maxdd_delta':fm['maxdd']-bm['maxdd'],'industry_addition_sharpe_delta':fm['sharpe_rf0']-bm['sharpe_rf0']}
me=sum(v['matched_excess_cagr']>0 for v in out.values()); add=sum(v['industry_addition_cagr_delta']>0 for v in out.values()); dd=sum(v['industry_addition_maxdd_delta']>=0 for v in out.values())
if me==3 and add>=2 and dd>=2: decision='P277_CALENDAR_BLOCK_PERSISTENCE_SUPPORTED'
elif me>=2 and (add>=2 or dd>=2): decision='P277_CALENDAR_BLOCK_PERSISTENCE_MIXED'
else: decision='P277_CALENDAR_BLOCK_PERSISTENCE_NOT_SUPPORTED_DIMENSION'
res={'schema':'research.p277_industry_calendar_block_r1','parent':'P266/P272/P273/P277','claim':'With P273 signals, equal-quarter weights, costs, universe and controls frozen, test non-overlapping calendar-block persistence of matched alpha and the P266 industry sleeve incremental capital role.','contract':{'source_spec':'P273 unchanged','blocks':BLOCKS,'gate':'SUPPORTED only if matched excess is positive in all 3 blocks and the P266 addition improves CAGR in >=2/3 blocks and max drawdown in >=2/3 blocks; MIXED if matched excess positive >=2/3 and either addition CAGR or drawdown improves >=2/3; otherwise NOT_SUPPORTED_DIMENSION','no_parameter_rescue':True},'tests':out,'matched_positive_blocks':me,'industry_addition_positive_cagr_blocks':add,'industry_addition_nonworse_maxdd_blocks':dd,'decision':decision,'limitations':['Yahoo adjusted prices research-only','calendar blocks are prospectively fixed descriptive persistence slices','scientific evidence only; no portfolio allocation/ranking authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p277_industry_calendar_block_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
