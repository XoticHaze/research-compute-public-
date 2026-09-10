from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['JAAA','SGOV','AVDV','VSS','IDMO','EFA','SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-10'; LB=24
BLOCKS={'2021_2022':('2021-01-01','2022-12-31'),'2023_2024':('2023-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
def mr(t): return c[t].dropna().resample('ME').last().pct_change().dropna().rename(t)
R={t:mr(t) for t in T}
p249=pd.concat([R['SPMO'],R['IJS']],axis=1).dropna().mean(axis=1).rename('p249')
p249ctl=pd.concat([R['SPY'],R['IJR']],axis=1).dropna().mean(axis=1).rename('p249ctl')
intl=pd.concat([R['AVDV'],R['IDMO']],axis=1).dropna().mean(axis=1).rename('intl')
intlctl=pd.concat([R['VSS'],R['EFA']],axis=1).dropna().mean(axis=1).rename('intlctl')
ls=pd.concat([R['SRLN'],R['HYG'],R['SHY']],axis=1).dropna(); bs=[]
for i in range(len(ls)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(ls[['HYG','SHY']].iloc[i-LB:i].values,ls.SRLN.iloc[i-LB:i].values,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1: b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=ls.index,columns=['hyg','shy']).shift(1); loanctl=(b.hyg*ls.HYG+b.shy*ls.SHY).rename('loanctl')
x=pd.concat([p249,p249ctl,R['SRLN'].rename('loan'),loanctl,R['JAAA'].rename('clo'),R['SGOV'].rename('cloctl'),intl,intlctl],axis=1).dropna().loc['2021-01-01':]
coverage={k:int(len(x.loc[a:b])) for k,(a,b) in BLOCKS.items()}; coverage_ok=all(v>=12 for v in coverage.values())
if not coverage_ok:
 out={'schema':'research.aaa_avdv_idmo_joint_complement_r1','workload_id':'AAA_AVDV_IDMO_JOINT_COMPLEMENT_R1','coverage':coverage,'coverage_ok':False,'decision':'COVERAGE_GATE_FAILED'}; Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/aaa_avdv_idmo_joint_complement_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out)); raise SystemExit(0)
# Frozen endpoint costs from prior experiments, applied once to each sleeve/control before blending.
def ep(s,cost): y=s.copy(); y.iloc[0]-=cost; y.iloc[-1]-=cost; return y
for col,cost in [('p249',.001),('p249ctl',.001),('loan',.001),('loanctl',.001),('clo',.0025),('cloctl',.0025),('intl',.0025),('intlctl',.0025)]: x[col]=ep(x[col],cost)
def stats(s):
 q=pd.Series(s,dtype=float).dropna(); n=len(q); w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(q.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(q):
 base=(q.p249+q.loan)/2; aa=(q.p249+q.loan+q.clo)/3; ai=(q.p249+q.loan+q.intl)/3; joint=(q.p249+q.loan+q.clo+q.intl)/4
 ctl=(q.p249ctl+q.loanctl)/2; aactl=(q.p249ctl+q.loanctl+q.cloctl)/3; aictl=(q.p249ctl+q.loanctl+q.intlctl)/3; jctl=(q.p249ctl+q.loanctl+q.cloctl+q.intlctl)/4
 s={k:stats(v) for k,v in [('base',base),('aaa',aa),('intl',ai),('joint',joint),('base_ctl',ctl),('aaa_ctl',aactl),('intl_ctl',aictl),('joint_ctl',jctl)]}
 s['matched_excess']={k:s[k]['cagr']-s[k+'_ctl']['cagr'] for k in ['base','aaa','intl','joint']}
 s['joint_vs_base']={m:s['joint'][m]-s['base'][m] for m in ['cagr','sharpe','max_drawdown']}
 s['joint_vs_aaa']={m:s['joint'][m]-s['aaa'][m] for m in ['cagr','sharpe','max_drawdown']}
 s['joint_vs_intl']={m:s['joint'][m]-s['intl'][m] for m in ['cagr','sharpe','max_drawdown']}
 return s
full=ev(x); sub={k:ev(x.loc[a:b]) for k,(a,b) in BLOCKS.items()}; pos=sum(v['matched_excess']['joint']>0 for v in sub.values())
# Joint complement is supported only if it preserves positive matched excess and chronology and improves at least one risk/return dimension vs each single-add portfolio without both CAGR and Sharpe worsening vs either.
def useful(d): return d['cagr']>0 or d['sharpe']>0 or d['max_drawdown']>0
def not_double_worse(d): return not (d['cagr']<0 and d['sharpe']<0)
supported=full['matched_excess']['joint']>0 and pos>=2 and useful(full['joint_vs_aaa']) and useful(full['joint_vs_intl']) and not_double_worse(full['joint_vs_aaa']) and not_double_worse(full['joint_vs_intl'])
decision='JOINT_COMPLEMENT_SUPPORTED' if supported else 'JOINT_COMPLEMENT_NOT_SUPPORTED'
out={'schema':'research.aaa_avdv_idmo_joint_complement_r1','workload_id':'AAA_AVDV_IDMO_JOINT_COMPLEMENT_R1','claim':'Test whether confirmed AAA CLO risk shaping and fixed AVDV+IDMO return enhancement remain jointly complementary beyond frozen P249+P373 without optimizing weights/products/dates/controls.','coverage':coverage,'coverage_ok':coverage_ok,'contract':{'base':'50/50 P249+P373','aaa_add':'equal capital P249+P373+JAAA','intl_add':'equal capital P249+P373+(50/50 AVDV+IDMO)','joint':'equal capital P249+P373+JAAA+(50/50 AVDV+IDMO)','matched_controls':'P249 ctl + causal P373 ctl + SGOV + 50/50 VSS/EFA as applicable','blocks':BLOCKS,'no_optimization':True},'full_sample':full,'chronology':sub,'positive_joint_excess_blocks':pos,'decision_rule':'Support only if joint matched excess >0 full sample and >=2/3 blocks, and joint improves at least one CAGR/Sharpe/maxDD dimension versus each single-add portfolio without simultaneously worsening both CAGR and Sharpe versus either.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/aaa_avdv_idmo_joint_complement_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'coverage':coverage,'joint_excess_pp':round(100*full['matched_excess']['joint'],3),'positive_blocks':pos,'joint_vs_base':full['joint_vs_base'],'joint_vs_aaa':full['joint_vs_aaa'],'joint_vs_intl':full['joint_vs_intl']},sort_keys=True))
