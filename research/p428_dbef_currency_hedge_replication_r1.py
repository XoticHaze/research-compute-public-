from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
T=['DBEF','EFA','SPY']; EP=.0025
x=yf.download(T,start='2012-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change(fill_method=None).dropna()
def ep(s):
 y=s.copy()
 if len(y): y.iloc[0]-=EP; y.iloc[-1]-=EP
 return y
def stats(s):
 q=ep(s.dropna()); n=len(q)
 if n<2:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None}
 w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(a,b=None):
 q=r.loc[a:b]; s=stats(q.DBEF); ctl=stats(q.EFA); opp=stats(q.SPY)
 return {'dbef':s,'efa_control':ctl,'spy_opportunity':opp,'matched_excess_pp':100*(s['cagr']-ctl['cagr']),'spy_excess_pp':100*(s['cagr']-opp['cagr']),'sharpe_delta':s['sharpe']-ctl['sharpe'],'maxdd_delta':s['max_drawdown']-ctl['max_drawdown']}
windows={k:ev(v) for k,v in {'2013+':'2013-01-01','2018+':'2018-01-01','2022+':'2022-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2013_2015':('2013-01-01','2015-12-31'),'2016_2019':('2016-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}.items()}
pos=sum(z['matched_excess_pp']>0 for z in blocks.values()); supported=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=3
decision='CURRENCY_HEDGE_INDEPENDENT_REPLICATION_SUPPORTED' if supported else 'CURRENCY_HEDGE_INDEPENDENT_REPLICATION_NOT_SUPPORTED'
out={'schema':'research.p428_dbef_currency_hedge_replication_r1.v1','workload_id':'P428_DBEF_CURRENCY_HEDGE_REPLICATION_R1','parent':'DEVELOPED_EXUS_CURRENCY_HEDGE','claim':'An independent developed ex-U.S. currency-hedged implementation (DBEF) can replicate positive after-cost matched excess versus an unhedged broad developed control (EFA), without modifying P426 HEFA parameters or dates.','cost_bps_each_endpoint':25,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'decision_rule':'Replication support requires positive DBEF-EFA after-cost CAGR excess in 2013+/2018+/2022+ and >=3/4 fixed chronology blocks. SPY opportunity cost is context only.','decision':decision,'scientific_consequence':('Independent implementation replication supports a broader currency-hedging mechanism claim, while any negative blocks remain explicit regime evidence.' if supported else 'Preserve P426 HEFA scoped survivor but reject broad currency-hedge transport; do not search additional hedged products, hedge ratios, or dates to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p428_dbef_currency_hedge_replication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_blocks':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'blocks':{k:round(v['matched_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
