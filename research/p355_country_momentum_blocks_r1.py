from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

COUNTRIES=['EWA','EWC','EWG','EWH','EWJ','EWW','EWS','EWT','EWU','EWY','EZA','FXI']; CONTROLS=['ACWI','SPY']
START='2009-01-01'; END='2026-09-10'; COST_BP=50; TOP_K=3; LOOKBACK=12
BLOCKS={'pre_2020':['2015-01-01','2019-12-31'],'2020_2022':['2020-01-01','2022-12-31'],'2023_plus':['2023-01-01','2026-09-10']}
raw=yf.download(COUNTRIES+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[COUNTRIES+CONTROLS].dropna(); m=close.resample('ME').last(); ret=m.pct_change(); score=m[COUNTRIES].shift(1)/m[COUNTRIES].shift(LOOKBACK)-1
w=pd.DataFrame(0.0,index=m.index,columns=COUNTRIES)
for dt,row in score.iterrows():
    if row.notna().sum()==len(COUNTRIES): w.loc[dt,row.nlargest(TOP_K).index]=1/TOP_K
turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
if active.any(): turn.loc[active.idxmax()]=1.0
cand=(w*ret[COUNTRIES]).sum(axis=1)-turn*(COST_BP/10000); matched=ret[COUNTRIES].mean(axis=1).copy(); acwi=ret.ACWI.copy(); spy=ret.SPY.copy()
if active.any():
    first=active.idxmax(); matched.loc[first]-=COST_BP/10000; acwi.loc[first]-=COST_BP/10000; spy.loc[first]-=COST_BP/10000
x=pd.DataFrame({'candidate':cand,'matched':matched,'ACWI':acwi,'SPY':spy}).loc[active].dropna()
def metrics(q):
    q=pd.Series(q).dropna(); n=len(q); eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
out={}
for name,(start,end) in BLOCKS.items():
    q=x.loc[(x.index>=pd.Timestamp(start))&(x.index<=pd.Timestamp(end))]
    a,b,c,s=metrics(q.candidate),metrics(q.matched),metrics(q.ACWI),metrics(q.SPY)
    out[name]={'candidate':a,'matched':b,'ACWI':c,'SPY':s,'matched_excess_cagr':a['cagr']-b['cagr'],'vs_ACWI_cagr':a['cagr']-c['cagr'],'vs_SPY_cagr':a['cagr']-s['cagr']}
positive=sum(v['matched_excess_cagr']>0 for v in out.values()); pre=out['pre_2020']['matched_excess_cagr']
# Thesis being adjudicated is broad temporal transport, not merely post-2020 usefulness.
# Broad support requires positive matched excess in >=2/3 non-overlapping blocks AND in pre-2020 specifically.
supported=positive>=2 and pre>0
decision='P355_COUNTRY_MOMENTUM_BROAD_TEMPORAL_STABILITY_SUPPORTED' if supported else 'P355_COUNTRY_MOMENTUM_BROAD_TEMPORAL_STABILITY_NOT_CONFIRMED'
res={'schema':'research.p355_country_momentum_blocks_r1','parent':'P354_COUNTRY_MOMENTUM_TRANSPORT','claim':'Orthogonal temporal-stability adjudicator for the unchanged P354 country momentum transport. Uses non-overlapping predeclared calendar blocks and no parameter, country, cost, threshold, top-k, lookback, or block search.','contract':{'countries':COUNTRIES,'lookback_months':LOOKBACK,'top_k':TOP_K,'one_way_turnover_cost_bps':COST_BP,'blocks':BLOCKS,'gate':'positive matched excess in >=2/3 blocks AND positive pre-2020 matched excess'},'results':out,'positive_matched_blocks':positive,'pre_2020_matched_excess_cagr':pre,'decision':decision,'scientific_consequence':'Pass supports a broad temporal transport claim. Failure narrows P354 to regime-conditional/recent support while preserving its passing 2020+ and 2022+ evidence; do not parameter rescue or kill the industry survivor.','limitations':['same Yahoo adjusted-price representation as P354','ETF country proxies','2023+ block ends at input cutoff even though monthly resample label may be month-end'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p355_country_momentum_blocks_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
