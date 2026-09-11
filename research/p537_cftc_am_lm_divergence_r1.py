from __future__ import annotations
import json, math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
import yfinance as yf

BASE='https://publicreporting.cftc.gov/resource/gpe5-46if.json'
CODE='13874A'; START='2010-01-01'; COST=0.001
WINDOWS={'all':'2012-01-01','recent':'2020-01-01'}

def fetch():
 q=urlencode({'$where':f"cftc_contract_market_code='{CODE}' AND report_date_as_yyyy_mm_dd >= '{START}T00:00:00.000'",'$order':'report_date_as_yyyy_mm_dd ASC','$limit':'5000'})
 req=Request(BASE+'?'+q,headers={'User-Agent':'XoticHaze-Research/1.0'})
 rows=json.loads(urlopen(req,timeout=45).read().decode()); out=[]
 for r in rows:
  oi=float(r['open_interest_all']); d=pd.Timestamp(r['report_date_as_yyyy_mm_dd']).tz_localize(None)
  am=(float(r['asset_mgr_positions_long'])-float(r['asset_mgr_positions_short']))/oi
  lm=(float(r['lev_money_positions_long'])-float(r['lev_money_positions_short']))/oi
  out.append((d,am,lm))
 return pd.DataFrame(out,columns=['report','am','lm']).drop_duplicates('report').set_index('report').sort_index()

def met(x):
 x=pd.Series(x,dtype=float).dropna(); n=len(x)
 if not n:return {'weeks':0,'cagr':None,'maxdd':None,'sharpe':None}
 e=(1+x).cumprod(); c=float(e.iloc[-1]**(52/n)-1); dd=float((e/e.cummax()-1).min())
 v=float(x.std(ddof=1)*math.sqrt(52)) if n>1 else 0
 return {'weeks':n,'cagr':c,'maxdd':dd,'sharpe':float(x.mean()*52/v) if v else None}

cot=fetch(); cot['release']=cot.index+pd.Timedelta(days=3); cot['div']=cot.am-cot.lm
# expanding causal percentile of participant divergence, no fitted return parameters
cot['pct']=np.nan
for i in range(104,len(cot)):
 hist=cot['div'].iloc[:i].dropna(); cot.iloc[i,cot.columns.get_loc('pct')]=float((hist<=cot['div'].iloc[i]).mean())
raw=yf.download('SPY',start=START,end=(pd.Timestamp.utcnow()+pd.Timedelta(days=1)).date().isoformat(),auto_adjust=True,progress=False,threads=False)
close=(raw['Close']['SPY'] if isinstance(raw.columns,pd.MultiIndex) else raw['Close']).dropna(); rows=[]
for _,r in cot.dropna(subset=['pct']).iterrows():
 ix=close.index.searchsorted(r.release)
 if ix+1>=len(close):continue
 sd=close.index[ix]; nd=close.index[ix+1]; rows.append((sd,r.pct,float(close.loc[nd]/close.loc[sd]-1)))
d=pd.DataFrame(rows,columns=['date','pct','fwd']).drop_duplicates('date').set_index('date').sort_index()
# predeclared mechanism: asset managers unusually more bullish than leveraged money => SPY, otherwise cash
# threshold is distributional median, not performance-selected
signal=(d.pct>0.5).astype(int); gross=signal*d.fwd; turn=signal.ne(signal.shift()).astype(float); turn.iloc[0]=float(signal.iloc[0]); d['net']=gross-COST*turn
out={'schema':'research.p537_cftc_am_lm_divergence_r1','claim':'Test whether causally released ES asset-manager versus leveraged-money positioning divergence contains equity timing information distinct from prior NQ-vs-ES relative-selection work.','contract':{'source':'CFTC TFF gpe5-46if ES 13874A','release_lag':'Tuesday observation usable first market close on/after Friday','feature':'expanding causal percentile of ES asset-manager net/OI minus leveraged-money net/OI after 104-week warmup','rule':'SPY if percentile > 0.50 else cash','switch_cost_bps':10,'matched_control':'static SPY exposure matched to signal fraction','windows':WINDOWS,'gate':'positive after-cost excess over exposure-matched SPY in both windows and >=3/5 positive chronology folds; no threshold/window/cost search'},'tests':{}}
for name,start in WINDOWS.items():
 q=d.loc[d.index>=start].copy(); frac=float((q.pct>0.5).mean()); ctrl=q.fwd*frac; m=met(q.net); b=met(ctrl); m['exposure']=frac; m['matched_cagr']=b['cagr']; m['matched_excess_cagr']=m['cagr']-b['cagr'];
 folds=[]
 for j,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  if len(ix): folds.append({'fold':j,'excess_cagr':met(q.net.iloc[ix])['cagr']-met(ctrl.iloc[ix])['cagr']})
 out['tests'][name]={'strategy':m,'folds':folds,'positive_folds':sum(x['excess_cagr']>0 for x in folds)}
a=out['tests']['all']; r=out['tests']['recent']; out['decision']='SUPPORTED' if a['strategy']['matched_excess_cagr']>0 and r['strategy']['matched_excess_cagr']>0 and a['positive_folds']>=3 and r['positive_folds']>=3 else 'NOT_SUPPORTED'
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p537_cftc_am_lm_divergence_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
