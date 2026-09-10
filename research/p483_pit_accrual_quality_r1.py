from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P483 research@example.invalid'; YEARS=list(range(2018,2025)); N=20; COST=.0010
OUT=Path('research/artifacts/p483_pit_accrual_quality_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy();z.columns=['ticker','cik'];z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual(g,tag,asof):
 vals=[]
 for v in g.get(tag,{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None and 300<=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days<=430:vals.append((v['end'],v['filed'],float(v['val'])))
 return vals
def feat(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); ni=[];cfo=[]
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
def ret1(t,y):
 q=yf.download(t,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)['Close'].dropna()
 if hasattr(q,'columns'):q=q.iloc[:,0]
 if len(q)<2:return None
 a=q[q.index<=pd.Timestamp(f'{y}-07-15')]; b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')]
 if len(a)==0 or len(b)==0:return None
 return float(b.iloc[-1]/a.iloc[0]-1)
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');vals=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.06)
   f=feat(cache[cik],asof)
   if f is not None:
    rr=ret1(row.ticker,y)
    if rr is not None:vals.append({'ticker':row.ticker,'cik':str(cik),'accrual':f,'forward_return':rr})
  except Exception:pass
 coverage=len(vals)/len(s);ready=coverage>=.80
 if ready:
  v=sorted(vals,key=lambda x:x['accrual']);k=max(1,int(np.ceil(.30*len(v))));sel=v[:k]; selret=float(np.mean([x['forward_return'] for x in sel])-COST); ctrl=float(np.mean([x['forward_return'] for x in v])-COST); spy=ret1('SPY',y); spy=(spy-COST) if spy is not None else None
  coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(v),'coverage':coverage,'ready':True,'selected_n':k,'selected_return':selret,'sample_control_return':ctrl,'excess_vs_sample':selret-ctrl,'spy_return':spy,'excess_vs_spy':selret-spy if spy is not None else None})
 else:coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(vals),'coverage':coverage,'ready':False})
ready=[x for x in coh if x['ready']]; supported=len(ready)==len(YEARS) and float(np.mean([x['excess_vs_sample'] for x in ready]))>0 and float(np.mean([x['excess_vs_spy'] for x in ready]))>0 and sum(x['excess_vs_sample']>0 for x in ready)>=5
out={'schema':'research.p483_pit_accrual_quality_r1.v1','workload_id':'P483_PIT_ACCRUAL_QUALITY_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Low cash-based accruals, defined prospectively as (annual net income - annual operating cash flow)/lagged assets using filed-at-safe 10-K facts, should identify higher-quality earnings and improve one-year returns versus the contemporaneous common sample and SPY.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'20 evenly spaced historical S&P members after ticker sort','feature':'(NetIncomeLoss or ProfitLoss - operating cash flow)/latest prior annual 10-K Assets','selection':'lowest 30% accruals','common_sample_coverage_min':.80,'entry_cost_bps':10,'acceptance':'all cohorts coverage-ready; mean excess >0 vs both contemporaneous sample and SPY; excess vs sample positive in >=5/7 years','no_rescue':True},'cohorts':coh,'decision':'PIT_LOW_ACCRUAL_ALPHA_SUPPORTED' if supported else 'PIT_LOW_ACCRUAL_ALPHA_NOT_SUPPORTED','scientific_consequence':'Qualify for independent larger-sample/chronology validation.' if supported else 'Reject exact low-accrual mechanism or classify data-not-ready if any cohort misses coverage; no feature, date, threshold, or constituent rescue.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':out['decision'],'cohorts':coh},sort_keys=True))