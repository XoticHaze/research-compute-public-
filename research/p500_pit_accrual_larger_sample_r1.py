from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P500 research@example.invalid'; YEARS=list(range(2018,2025)); N=40; COST=.0010
OUT=Path('research/artifacts/p500_pit_accrual_larger_sample_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy();z.columns=['ticker','cik'];z.ticker=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z.cik=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual(g,tag,asof):
 out=[]
 for v in g.get(tag,{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
   try:d=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
   except:continue
   if 300<=d<=430:out.append((v['end'],v['filed'],float(v['val'])))
 return out
def feat(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{});ni=[];cfo=[]
 for t in ['NetIncomeLoss','ProfitLoss']:ni+=annual(g,t,asof)
 for t in ['NetCashProvidedByUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']:cfo+=annual(g,t,asof)
 common=sorted(set(x[0] for x in ni)&set(x[0] for x in cfo));assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v.get('val') is not None and float(v['val'])>0:assets.append((v['end'],v['filed'],float(v['val'])))
 for end in reversed(common):
  n=max([x for x in ni if x[0]==end],key=lambda x:x[1]);c=max([x for x in cfo if x[0]==end],key=lambda x:x[1]);a=[x for x in assets if x[0]<end]
  if a:
   aa=max(a,key=lambda x:(x[0],x[1]));return (n[2]-c[2])/aa[2]
 return None
def batch_returns(tickers,y):
 if not tickers:return {}
 raw=yf.download(tickers,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=True)
 if raw.empty:return {}
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series):c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t not in c.columns:continue
  q=c[t].dropna();a=q[q.index<=pd.Timestamp(f'{y}-07-15')];b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')]
  if len(a) and len(b):out[t]=float(b.iloc[-1]/a.iloc[0]-1)
 return out
def spyret(y):
 x=yf.download('SPY',start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)['Close'].dropna();q=x.iloc[:,0] if hasattr(x,'columns') else x;a=q[q.index<=pd.Timestamp(f'{y}-07-15')];b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')];return float(b.iloc[-1]/a.iloc[0]-1) if len(a) and len(b) else None
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');frows=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.04)
   f=feat(cache[cik],asof)
   if f is not None:frows.append({'ticker':row.ticker,'cik':str(cik),'accrual':f})
  except Exception:pass
 rets=batch_returns([x['ticker'] for x in frows],y);vals=[{**x,'forward_return':rets[x['ticker']]} for x in frows if x['ticker'] in rets];coverage=len(vals)/len(s);ready=coverage>=.80
 if ready:
  v=sorted(vals,key=lambda x:x['accrual']);k=max(1,int(np.ceil(.30*len(v))));sel=v[:k];selret=float(np.mean([x['forward_return'] for x in sel])-COST);ctrl=float(np.mean([x['forward_return'] for x in v])-COST);sp=spyret(y);sp=(sp-COST) if sp is not None else None
  coh.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(s),'common_n':len(v),'coverage':coverage,'ready':True,'selected_n':k,'selected_return':selret,'sample_control_return':ctrl,'excess_vs_sample':selret-ctrl,'spy_return':sp,'excess_vs_spy':selret-sp if sp is not None else None})
 else:coh.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(s),'common_n':len(vals),'coverage':coverage,'ready':False})
ready=[x for x in coh if x['ready']];mean_sample=float(np.mean([x['excess_vs_sample'] for x in ready])) if ready else None;mean_spy=float(np.mean([x['excess_vs_spy'] for x in ready])) if ready else None;pos=sum(x['excess_vs_sample']>0 for x in ready)
supported=len(ready)==len(YEARS) and mean_sample>0 and mean_spy>0 and pos>=5
decision='PIT_LOW_ACCRUAL_LARGER_SAMPLE_SUPPORTED' if supported else ('PIT_LOW_ACCRUAL_LARGER_SAMPLE_NOT_SUPPORTED' if len(ready)==len(YEARS) else 'PIT_LOW_ACCRUAL_LARGER_SAMPLE_DATA_NOT_READY')
out={'schema':'research.p500_pit_accrual_larger_sample_r1.v1','workload_id':'P500_PIT_ACCRUAL_LARGER_SAMPLE_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Independent larger-sample validation of the unchanged P483 low-accrual mechanism using 40 deterministic historical S&P members per year instead of 20. Feature, lowest-30% selection, years, filed-at causality, >=80% common feature+price gate, 10 bp entry cost, controls, and acceptance rule remain unchanged.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'40 evenly spaced historical S&P members after ticker sort','feature':'(annual net income - annual operating cash flow)/latest prior annual 10-K Assets','selection':'lowest 30% accruals','common_sample_coverage_min':.80,'entry_cost_bps':10,'acceptance':'all cohorts coverage-ready; mean excess >0 vs both contemporaneous sample and SPY; excess vs sample positive in >=5/7 years','no_rescue':True},'cohorts':coh,'summary':{'ready_years':len(ready),'positive_sample_excess_years':pos,'mean_excess_vs_sample':mean_sample,'mean_excess_vs_spy':mean_spy},'decision':decision,'scientific_consequence':'If supported, low-accrual advances beyond small-sample status; otherwise reject or park exact mechanism according to readiness without changing the P483 contract.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'cohorts':[{k:x.get(k) for k in ['year','coverage','ready','excess_vs_sample','excess_vs_spy']} for x in coh]},sort_keys=True))
