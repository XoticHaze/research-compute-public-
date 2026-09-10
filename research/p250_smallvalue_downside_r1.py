from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p248_smallvalue_survivor_complementarity_r1 as p248

WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
svm=p248.close_month[['AVUV','AVDV']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M')
p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
x=sv.to_frame('sv').join(p64.rename(columns={'candidate':'p64'})).join(p36.rename(columns={'candidate':'p36'})).dropna()
out={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)].copy(); full=(q.sv+q.p64+q.p36)/3; wo=(q.p64+q.p36)/2
 stress=(wo<0); crisis=(wo<=wo.quantile(.25)); both=(stress|crisis)
 def stats(mask):
  idx=mask[mask].index; z=q.loc[idx]; f=full.loc[idx]; w=wo.loc[idx]
  return {'months':int(len(idx)),'smallvalue_mean':float(z.sv.mean()),'with_smallvalue_mean':float(f.mean()),'without_smallvalue_mean':float(w.mean()),'mean_delta':float((f-w).mean()),'smallvalue_positive_fraction':float((z.sv>0).mean()),'smallvalue_beats_without_fraction':float((z.sv>w).mean())}
 out[name]={'negative_core_months':stats(stress),'worst_core_quartile':stats(crisis),'union_stress':stats(both),'core_worst_quartile_cutoff':float(wo.quantile(.25))}
a=out['2020']['union_stress']; b=out['2022']['union_stress']; support=a['mean_delta']>0 and b['mean_delta']>0 and a['smallvalue_positive_fraction']>=.4 and b['smallvalue_positive_fraction']>=.4
res={'schema':'research.p250_smallvalue_downside_r1','parent':'P249/P250','claim':'Small value earns its P249 risk-efficiency role by improving fixed P64/P36 outcomes specifically during predeclared downside months, not merely by averaging unrelated strong months.','contract':{'stress':'months where fixed P64/P36 return is negative OR in its own worst quartile','windows':WINDOWS,'no_threshold_weight_window_or_parameter_search':True},'tests':out,'decision':'P250_DOWNSIDE_ROLE_SUPPORTED' if support else 'P250_DOWNSIDE_ROLE_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p250_smallvalue_downside_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True)); print(json.dumps(res,sort_keys=True))
