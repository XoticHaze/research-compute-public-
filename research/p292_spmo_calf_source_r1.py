from __future__ import annotations
import io,json,math,urllib.request
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=['SPMO','CALF','SPY','IJR','QQQ']; START='2018-01-01'; END='2026-09-10'; COST=10/10000
CAND=['SPMO','CALF']; BASE=['SPY','IJR']; BLOCKS={'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_present':('2025-01-01','2026-09-10')}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None}
def reb(r,cols):
 target=pd.Series({c:1/len(cols) for c in cols},dtype=float); prev=None; out=[]
 for _,row in r[cols].iterrows():
  turn=1.0 if prev is None else float((target-prev).abs().sum()/2); out.append(float((target*row).sum())-turn*COST); grown=target*(1+row); prev=grown/float(grown.sum())
 return pd.Series(out,index=r.index,dtype=float)
def stooq(sym):
 url=f'https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d&d1=20180101&d2=20260910'; req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}); raw=urllib.request.urlopen(req,timeout=30).read().decode('utf-8'); df=pd.read_csv(io.StringIO(raw));
 if 'Date' not in df or 'Close' not in df or len(df)<100: return pd.Series(dtype=float)
 s=pd.Series(pd.to_numeric(df.Close,errors='coerce').values,index=pd.to_datetime(df.Date),name=sym).dropna(); return s
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); ypx=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); yr=ypx.pct_change().dropna()
scols={s:stooq(s) for s in SYMS}; coverage={s:int(len(v)) for s,v in scols.items()}; available=[s for s,v in scols.items() if len(v)>=100]
if len(available)==len(SYMS):
 spx=pd.concat(scols,axis=1).dropna().resample('ME').last(); sr=spx.pct_change().dropna(); common=yr.index.intersection(sr.index); fidelity={}
 for s in SYMS:
  a=yr.loc[common,s]; b=sr.loc[common,s]; fidelity[s]={'common_months':int(len(common)),'return_corr':float(a.corr(b)),'median_abs_return_diff_bp':float((a-b).abs().median()*10000),'max_abs_return_diff_bp':float((a-b).abs().max()*10000)}
 cand=reb(sr,CAND); base=reb(sr,BASE); q=sr['QQQ']; blocks={}
 for n,(a,b) in BLOCKS.items():
  ix=(sr.index>=pd.Timestamp(a))&(sr.index<=pd.Timestamp(b)); cm=metric(cand.loc[ix]); bm=metric(base.loc[ix]); qm=metric(q.loc[ix]); blocks[n]={'matched_excess_cagr':cm['cagr']-bm['cagr'],'vs_QQQ_cagr':cm['cagr']-qm['cagr'],'candidate':cm,'matched':bm}
 pos=sum(v['matched_excess_cagr']>0 for v in blocks.values()); corrpass=sum(v['return_corr']>=0.995 for v in fidelity.values()); decision='P292_STOOQ_SOURCE_CONFIRMATION' if pos==3 and corrpass==len(SYMS) else 'P292_SOURCE_REPRESENTATION_DIVERGENCE'
else:
 fidelity={}; blocks={}; pos=0; corrpass=0; decision='P292_STOOQ_SOURCE_COVERAGE_INSUFFICIENT'
out={'schema':'research.p292_spmo_calf_source_r1','parent':'P292','claim':'Adjudicate whether the frozen SPMO+CALF matched-excess evidence is reproducible using Stooq as an independent adjusted-price representation, without changing components, weights, cadence, costs, controls, or calendar blocks.','stooq_daily_coverage':coverage,'available_symbols':available,'monthly_return_fidelity':fidelity,'stooq_calendar_blocks':blocks,'summary':{'positive_matched_blocks':pos,'high_fidelity_symbols':corrpass},'decision_rule':'Confirm only if all five symbols have usable Stooq coverage, monthly-return correlation to the original adjusted-return representation is >=0.995 for every symbol, and frozen SPMO+CALF matched excess remains positive in all three fixed calendar blocks. Insufficient coverage or price-representation divergence is DATA/REPRESENTATION evidence, not model failure.','decision':decision,'limitations':['Stooq adjusted-price semantics may differ from the original provider','source-fidelity adjudication only; no parameter rescue','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p292_spmo_calf_source_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
