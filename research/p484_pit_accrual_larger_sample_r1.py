from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P484 research@example.invalid'; YEARS=list(range(2018,2025)); N=40; COST=.0010
OUT=Path('research/artifacts/p484_pit_accrual_larger_sample_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
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
 g=facts.get('facts',{}).get('us-gaap',{});ni=[];cfo=[]
 for t in ['NetIncomeLoss','ProfitLoss']:ni+=annual(g,t,asof)
 for t in ['NetCashProvidedByUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']:cfo+=annual(g,t,asof)
 common=sorted(set(x[0] for x in ni)&set(x[0] for x in cfo));assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v.get('val') is not None and float(v['val'])>0:assets.append((v['end'],v['filed'],float(v['val'])))
 for end in reversed(common):
  n=max([x for x in ni if x[0]==end],key=lambda x:x[1]);c=max([x for x in cfo if x[0]==end],key=lambda x:x[1]);a=[x for x in assets if x[0]<end]
  if a:return (n[2]-c[2])/max(a,key=lambda x:(x[0],x[1]))[2]
 return None
def price_returns(tickers,y):
 raw=yf.download(tickers+['SPY'],start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=True)['Close']; out={}
 if isinstance(raw,pd.Series):raw=raw.to_frame(tickers[0])
 for t in tickers+['SPY']:
  if t not in raw.columns:continue
  q=raw[t].dropna();a=q[q.index<=pd.Timestamp(f'{y}-07-15')];b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')]
  if len(a) and len(b):out[t]=float(b.iloc[-1]/a.iloc[0]-1)
 return out
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker'); feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.04)
   f=feat(cache[cik],asof)
   if f is not None:feats.append({'ticker':row.ticker,'cik':str(cik),'accrual':f})
  except Exception:pass
 pr=price_returns([x['ticker'] for x in feats],y);vals=[{**x,'forward_return':pr[x['ticker']]} for x in feats if x['ticker'] in pr];coverage=len(vals)/len(s);ready=coverage>=.80
 if ready:
  v=sorted(vals,key=lambda x:x['accrual']);k=max(1,int(np.ceil(.30*len(v))));sel=v[:k];selret=float(np.mean([x['forward_return'] for x in sel])-COST);ctrl=float(np.mean([x['forward_return'] for x in v])-COST);spy=(pr.get('SPY')-COST) if pr.get('SPY') is not None else None
  coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(v),'coverage':coverage,'ready':True,'selected_n':k,'selected_return':selret,'sample_control_return':ctrl,'excess_vs_sample':selret-ctrl,'spy_return':spy,'excess_vs_spy':selret-spy if spy is not None else None})
 else:coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(vals),'coverage':coverage,'ready':False})
ready=[x for x in coh if x['ready']];supported=len(ready)==len(YEARS) and float(np.mean([x['excess_vs_sample'] for x in ready]))>0 and float(np.mean([x['excess_vs_spy'] for x in ready]))>0 and sum(x['excess_vs_sample']>0 for x in ready)>=5
out={'schema':'research.p484_pit_accrual_larger_sample_r1.v1','workload_id':'P484_PIT_ACCRUAL_LARGER_SAMPLE_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Replicate unchanged P483 low-accrual mechanism on a doubled deterministic historical sample before promotion.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'40 evenly spaced historical S&P members after ticker sort','feature':'unchanged P483 cash-based accrual','selection':'unchanged lowest 30%','common_sample_coverage_min':.80,'entry_cost_bps':10,'acceptance':'unchanged: all cohorts ready; mean excess >0 vs sample and SPY; sample excess positive >=5/7 years','no_rescue':True},'cohorts':coh,'decision':'PIT_LOW_ACCRUAL_LARGER_SAMPLE_SUPPORTED' if supported else 'PIT_LOW_ACCRUAL_LARGER_SAMPLE_NOT_SUPPORTED','scientific_consequence':'Strengthen low-accrual candidate for broader chronology/complementarity testing.' if supported else 'Do not promote low-accrual from P483 small-sample support; larger deterministic sample failed unchanged gate.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':out['decision'],'cohorts':coh},sort_keys=True))