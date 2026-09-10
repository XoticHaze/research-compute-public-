from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CAND=['SPMO','CALF']; BASE=['SPY','IJR']; CONTROL='QQQ'; START='2018-01-01'; END='2026-09-11'; COST=10/10000; WINDOWS={'2019':'2019-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def equal_rebalanced(r,cols):
 target=pd.Series({c:1/len(cols) for c in cols},dtype=float); out=[]; turns=[]; prev_end=None
 for _,row in r[cols].iterrows():
  if prev_end is None:
   turnover=1.0
  else:
   turnover=float((target-prev_end).abs().sum()/2)
  gross=float((target*row).sum()); out.append(gross-turnover*COST); turns.append(turnover)
  grown=target*(1+row); denom=float(grown.sum()); prev_end=(grown/denom) if denom else target.copy()
 return pd.Series(out,index=r.index,dtype=float),pd.Series(turns,index=r.index,dtype=float)
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return out
syms=CAND+BASE+[CONTROL]; raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); cand,ct=equal_rebalanced(r,CAND); base,bt=equal_rebalanced(r,BASE); results={}
for name,start in WINDOWS.items():
 ix=r.index>=pd.Timestamp(start); a=cand.loc[ix]; b=base.loc[ix]; qqq=r.loc[ix,CONTROL]; f=folds(a,b); am=metric(a); bm=metric(b); qm=metric(qqq); results[name]={'candidate':am,'matched_blend':bm,'matched_excess_cagr':am['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'vs_QQQ_cagr':am['cagr']-qm['cagr'],'candidate_avg_monthly_turnover':float(ct.loc[ix].mean()),'matched_avg_monthly_turnover':float(bt.loc[ix].mean())}
p=results['2019']; q=results['2020']; s=results['2022']; ok=p['matched_excess_cagr']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched_blend']['maxdd']-.05 and q['matched_excess_cagr']>0 and s['matched_excess_cagr']>0
out={'schema':'research.spmo_calf_exploratory_combo_r1','workload_id':'SPMO_CALF_EXPLORATORY_COMBO_R1','claim':'Exploratorily test whether fixed equal-weight combination of the already-observed SPMO and CALF sleeves improves after-cost matched excess versus an equal-weight SPY+IJR control representing the same large/small-cap capital split.','parameters':{'candidate':CAND,'matched':BASE,'weights':[0.5,0.5],'monthly_rebalance':True,'one_way_turnover_cost_bps':10,'windows':WINDOWS,'no_weight_or_component_search':True,'turnover_method':'monthly target-weight rebalance from prior post-return drift; full initial entry charged'},'results':results,'decision_rule':'Exploratory support requires positive 2019+ matched excess, >=3/5 positive chronology folds, no >5pp max-drawdown penalty, and positive matched excess in 2020+ and 2022+. Because components were selected from same-firing evidence before this test, any pass requires future independent confirmation and is not prospective proof.','decision':'SPMO_CALF_EXPLORATORY_COMBO_SUPPORTED_REQUIRES_INDEPENDENT_CONFIRMATION' if ok else 'SPMO_CALF_EXPLORATORY_COMBO_NOT_SUPPORTED','limitations':['post-selection exploratory combination; not a clean prospective holdout','fund methodologies/fees embedded in adjusted returns','scientific combination evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/spmo_calf_exploratory_combo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
