from __future__ import annotations
import json,math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import numpy as np,pandas as pd,yfinance as yf
BASE='https://publicreporting.cftc.gov/resource/gpe5-46if.json'; CODE='13874A'; START='2010-01-01'; COST=.001
WINDOWS={'all':'2012-01-01','recent':'2020-01-01'}
def met(x):
 x=pd.Series(x,dtype=float).dropna(); n=len(x)
 if not n:return {'weeks':0,'cagr':None,'maxdd':None}
 e=(1+x).cumprod(); return {'weeks':n,'cagr':float(e.iloc[-1]**(52/n)-1),'maxdd':float((e/e.cummax()-1).min())}
q=urlencode({'$where':f"cftc_contract_market_code='{CODE}' AND report_date_as_yyyy_mm_dd >= '{START}T00:00:00.000'",'$order':'report_date_as_yyyy_mm_dd ASC','$limit':'5000'})
rows=json.loads(urlopen(Request(BASE+'?'+q,headers={'User-Agent':'XoticHaze-Research/1.0'}),timeout=45).read().decode()); a=[]
for r in rows:
 oi=float(r['open_interest_all']); a.append((pd.Timestamp(r['report_date_as_yyyy_mm_dd']).tz_localize(None),(float(r['lev_money_positions_long'])-float(r['lev_money_positions_short']))/oi))
cot=pd.DataFrame(a,columns=['report','lm']).drop_duplicates('report').set_index('report').sort_index(); cot['release']=cot.index+pd.Timedelta(days=3); cot['pct']=np.nan
for i in range(104,len(cot)):
 h=cot.lm.iloc[:i].dropna(); cot.iloc[i,cot.columns.get_loc('pct')]=float((h<=cot.lm.iloc[i]).mean())
raw=yf.download('SPY',start=START,end=(pd.Timestamp.utcnow()+pd.Timedelta(days=1)).date().isoformat(),auto_adjust=True,progress=False,threads=False); close=(raw['Close']['SPY'] if isinstance(raw.columns,pd.MultiIndex) else raw['Close']).dropna(); z=[]
for _,r in cot.dropna(subset=['pct']).iterrows():
 i=close.index.searchsorted(r.release)
 if i+1<len(close): z.append((close.index[i],r.pct,float(close.iloc[i+1]/close.iloc[i]-1)))
d=pd.DataFrame(z,columns=['date','pct','fwd']).drop_duplicates('date').set_index('date').sort_index()
# contrarian crowding mechanism: avoid equity only when leveraged money is in top historical quartile
sig=(d.pct<=.75).astype(int); turn=sig.ne(sig.shift()).astype(float); turn.iloc[0]=float(sig.iloc[0]); d['net']=sig*d.fwd-COST*turn
out={'schema':'research.p538_cftc_lm_crowding_contrarian_r1','claim':'Test whether extreme causally released ES leveraged-money long crowding predicts weak enough subsequent equity returns to improve SPY exposure after costs.','contract':{'feature':'expanding causal percentile of ES leveraged-money net/OI after 104 weeks','rule':'SPY unless percentile > 0.75, then cash','switch_cost_bps':10,'matched_control':'static SPY exposure matched to signal fraction','windows':WINDOWS,'gate':'positive matched excess both windows and >=3/5 positive chronology folds both; no parameter search'},'tests':{}}
for n,s in WINDOWS.items():
 q=d.loc[d.index>=s]; frac=float((q.pct<=.75).mean()); ctrl=q.fwd*frac; m=met(q.net); b=met(ctrl); folds=[]
 for j,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  if len(ix):folds.append({'fold':j,'excess_cagr':met(q.net.iloc[ix])['cagr']-met(ctrl.iloc[ix])['cagr']})
 m.update({'exposure':frac,'matched_cagr':b['cagr'],'matched_excess_cagr':m['cagr']-b['cagr']}); out['tests'][n]={'strategy':m,'folds':folds,'positive_folds':sum(x['excess_cagr']>0 for x in folds)}
a=out['tests']['all'];r=out['tests']['recent'];out['decision']='SUPPORTED' if a['strategy']['matched_excess_cagr']>0 and r['strategy']['matched_excess_cagr']>0 and a['positive_folds']>=3 and r['positive_folds']>=3 else 'NOT_SUPPORTED';Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p538_cftc_lm_crowding_contrarian_r1.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
