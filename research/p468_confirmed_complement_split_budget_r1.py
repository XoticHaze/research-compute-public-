from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','JAAA','SGOV','AVDV','IDMO','VSS','EFA']; COST=.0025; W=.25
raw=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None); p=.5*(r.SPMO+r.IJS); pc=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
 z=r[['HYG','SHY','SRLN']].iloc[max(0,i-24):i].dropna()
 if len(z)<24: bs.append((np.nan,np.nan)); continue
 b=np.clip(np.linalg.lstsq(z[['HYG','SHY']].values,z.SRLN.values,rcond=None)[0],0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(b))
b=pd.DataFrame(bs,index=r.index,columns=['h','s']).shift(1); lc=b.h*r.HYG+b.s*r.SHY
q=pd.DataFrame({'p':p,'pc':pc,'loan':r.SRLN,'lc':lc,'aaa':r.JAAA,'aaac':r.SGOV,'intl':.5*(r.AVDV+r.IDMO),'intlc':.5*(r.VSS+r.EFA)}).dropna().loc['2021-01-01':]
def st(s):
 x=s.copy(); x.iloc[0]-=COST; x.iloc[-1]-=COST; w=(1+x).cumprod(); n=len(x); vol=x.std(ddof=1)*math.sqrt(12); neg=x[x<0].std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/vol),'max_drawdown':float((w/w.cummax()-1).min()),'downside_vol':float(neg) if pd.notna(neg) else None}
def ev(z):
 core=.5*z.p+.5*z.loan; corec=.5*z.pc+.5*z.lc
 ser={'aaa':.75*core+.25*z.aaa,'intl':.75*core+.25*z.intl,'split':.75*core+.125*z.aaa+.125*z.intl}
 ctl={'aaa':.75*corec+.25*z.aaac,'intl':.75*corec+.25*z.intlc,'split':.75*corec+.125*z.aaac+.125*z.intlc}
 out={'core':st(core),'core_control':st(corec),'correlation':{'aaa_core':float(z.aaa.corr(core)),'intl_core':float(z.intl.corr(core)),'aaa_intl':float(z.aaa.corr(z.intl))}}
 for k in ser:
  a=st(ser[k]); cc=st(ctl[k]); a['matched_excess_cagr']=a['cagr']-cc['cagr']; a['vs_core']={m:a[m]-out['core'][m] for m in ['cagr','sharpe','max_drawdown','downside_vol']}; out[k]=a; out[k+'_control']=cc
 out['split_vs_aaa']={m:out['split'][m]-out['aaa'][m] for m in ['cagr','sharpe','max_drawdown','downside_vol']}; out['split_vs_intl']={m:out['split'][m]-out['intl'][m] for m in ['cagr','sharpe','max_drawdown','downside_vol']}
 return out
full=ev(q); n=len(q); sizes=[n//3,n//3,n-2*(n//3)]; blocks=[]; off=0
for i,s in enumerate(sizes,1): z=q.iloc[off:off+s]; off+=s; blocks.append({'block':i,'start':str(z.index[0].date()),'end':str(z.index[-1].date()),'result':ev(z)})
pos={k:sum(b['result'][k]['matched_excess_cagr']>0 for b in blocks) for k in ['aaa','intl','split']}
split_beats_aaa=sum((b['result']['split']['cagr']>b['result']['aaa']['cagr'])+(b['result']['split']['sharpe']>b['result']['aaa']['sharpe'])+(b['result']['split']['max_drawdown']>b['result']['aaa']['max_drawdown'])>=2 for b in blocks)
split_beats_intl=sum((b['result']['split']['cagr']>b['result']['intl']['cagr'])+(b['result']['split']['sharpe']>b['result']['intl']['sharpe'])+(b['result']['split']['max_drawdown']>b['result']['intl']['max_drawdown'])>=2 for b in blocks)
full_split_support=full['split']['matched_excess_cagr']>0 and sum(full['split']['vs_core'][m]>0 for m in ['cagr','sharpe','max_drawdown'])>=2
full_vs_aaa=sum(full['split_vs_aaa'][m]>0 for m in ['cagr','sharpe','max_drawdown'])>=2
full_vs_intl=sum(full['split_vs_intl'][m]>0 for m in ['cagr','sharpe','max_drawdown'])>=2
if full_split_support and pos['split']>=2 and full_vs_aaa and full_vs_intl and split_beats_aaa>=2 and split_beats_intl>=2: decision='SPLIT_ROBUSTLY_ADDITIVE'
elif full_split_support and full_vs_aaa and split_beats_aaa>=2: decision='SPLIT_BEATS_AAA_NOT_INTL'
elif full_split_support and full_vs_intl and split_beats_intl>=2: decision='SPLIT_BEATS_INTL_NOT_AAA'
else: decision='MIXED_NO_DOMINANCE'
out={'schema':'research.p468_confirmed_complement_split_budget_r1.v1','workload_id':'P468_CONFIRMED_COMPLEMENT_SPLIT_BUDGET_R1','parent':'FUND_MODEL_SURVIVOR_PORTFOLIO','claim':'Fixed total 25% incremental-capital composition test: compare 25% AAA CLO, 25% 50/50 AVDV+IDMO, and fixed 12.5% AAA + 12.5% AVDV+IDMO beyond the frozen P249+P373 core on one common sample. No weight search.','contract':{'core':'P249+P373 frozen core','total_incremental_budget':.25,'aaa':'JAAA / SGOV matched control','international':'50/50 AVDV+IDMO / 50/50 VSS+EFA matched control','split':'12.5% JAAA + 12.5% AVDV+IDMO','endpoint_cost_bps':25,'chronology':'three equal-count blocks','split_support_rule':'positive matched excess, >=2/3 positive blocks, and >=2 of CAGR/Sharpe/maxDD improve versus both single-complement alternatives full-sample and in >=2/3 blocks','weight_grid':False},'coverage':{'months':n,'start':str(q.index[0].date()),'end':str(q.index[-1].date()),'block_sizes':sizes},'full_sample':full,'chronology':blocks,'positive_matched_excess_blocks':pos,'split_beats_aaa_blocks':split_beats_aaa,'split_beats_intl_blocks':split_beats_intl,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p468_confirmed_complement_split_budget_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'coverage':out['coverage'],'positive_blocks':pos,'split_beats_aaa_blocks':split_beats_aaa,'split_beats_intl_blocks':split_beats_intl,'full':{k:{'matched_excess_pp':round(100*full[k]['matched_excess_cagr'],3),'vs_core':full[k]['vs_core']} for k in ['aaa','intl','split']},'split_vs_aaa':full['split_vs_aaa'],'split_vs_intl':full['split_vs_intl'],'correlation':full['correlation']},sort_keys=True))