import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
A=['AVUV','AVDV','IJR','VSS','SPY']; B=10

def cagr(r):
 q=np.asarray(r,float); return float(np.prod(1+q)**(12/len(q))-1)
def cost(r):
 q=np.asarray(r,float).copy(); f=B/10000
 if len(q): q[0]-=f; q[-1]-=f
 return q
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('ME').last().pct_change().dropna(how='any')
rows=[]
for yr,q in r.groupby(r.index.year):
 if len(q)<6: continue
 avuv=q.AVUV.to_numpy(); avdv=q.AVDV.to_numpy(); ijr=q.IJR.to_numpy(); vss=q.VSS.to_numpy(); spy=q.SPY.to_numpy(); combo=.5*avuv+.5*avdv; matched=.5*ijr+.5*vss
 rows.append({'year':int(yr),'months':len(q),'combo_vs_matched':cagr(cost(combo))-cagr(cost(matched)),'combo_vs_spy':cagr(cost(combo))-cagr(cost(spy)),'us_component_vs_control':cagr(cost(avuv))-cagr(cost(ijr)),'intl_component_vs_control':cagr(cost(avdv))-cagr(cost(vss))})
full={'combo_vs_matched':cagr(cost(.5*r.AVUV.to_numpy()+.5*r.AVDV.to_numpy()))-cagr(cost(.5*r.IJR.to_numpy()+.5*r.VSS.to_numpy())),'combo_vs_spy':cagr(cost(.5*r.AVUV.to_numpy()+.5*r.AVDV.to_numpy()))-cagr(cost(r.SPY.to_numpy()))}
pos_combo=sum(x['combo_vs_matched']>0 for x in rows); both=sum(x['us_component_vs_control']>0 and x['intl_component_vs_control']>0 for x in rows); either=sum(x['us_component_vs_control']>0 or x['intl_component_vs_control']>0 for x in rows)
ok=full['combo_vs_matched']>0 and pos_combo>=4 and either>=5
out={'schema':'research.p242_smallvalue_component_persistence_r1','parent':'P239/P240/P241','claim':'fixed AVUV/AVDV combination matched excess is temporally persistent and not solely an aggregate artifact of one component','contract':{'candidate_weights':{'AVUV':0.5,'AVDV':0.5},'matched_control_weights':{'IJR':0.5,'VSS':0.5},'calendar_years_fixed':True,'minimum_months_per_year':6,'cost_bps':B,'no_weight_window_fund_or_parameter_search':True,'gate':'full matched excess positive, >=4 positive combo calendar years, >=5 years with at least one component positive versus its matched control'},'full_period':full,'calendar_years':rows,'positive_combo_years':pos_combo,'both_components_positive_years':both,'at_least_one_component_positive_years':either,'decision':'P242_SUPPORT' if ok else 'P242_COMPONENT_PERSISTENCE_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p242_smallvalue_component_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
