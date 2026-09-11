from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P493 research@example.invalid'; YEARS=list(range(2018,2025)); N=40; COST=.001
OUT=Path('research/artifacts/p493_pit_operating_margin_improvement_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}; j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual(g,tag,asof):
 vals=[]
 for unit,arr in g.get(tag,{}).get('units',{}).items():
  if unit!='USD': continue
  for v in arr:
   if v.get('form')!='10-K' or not v.get('start') or not v.get('end') or not v.get('filed') or v['filed']>asof or v['end']>asof or v.get('val') is None: continue
   try: days=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
   except Exception: continue
   if 250<=days<=450: vals.append((v['end'],v['filed'],float(v['val'])))
 d={}
 for x in vals:
  if x[0] not in d or x[1]>d[x[0]][1]: d[x[0]]=x
 return [d[k] for k in sorted(d)]
def feat(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); op=annual(g,'OperatingIncomeLoss',asof); rev=annual(g,'Revenues',asof)
 if not rev: rev=annual(g,'SalesRevenueNet',asof)
 common=sorted(set(x[0] for x in op)&set(x[0] for x in rev))
 if len(common)<2:return None
 margins=[]
 for end in common:
  ov=[x for x in op if x[0]==end][-1][2]; rv=[x for x in rev if x[0]==end][-1][2]
  if rv>0:margins.append((end,ov/rv))
 if len(margins)<2:return None
 return margins[-1][1]-margins[-2][1]
def ret1(t,y):
 q=yf.download(t,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)['Close'].dropna()
 if hasattr(q,'columns'):q=q.iloc[:,0]
 if len(q)<2:return None
 a=q[q.index<=pd.Timestamp(f'{y}-07-15')]; b=q[q.index>=pd.Timestamp(f'{y+1}-06-15')]
 if len(a)==0 or len(b)==0:return None
 return float(b.iloc[-1]/a.iloc[0]-1)
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30'; rev,z=hist(asof); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker'); vals=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache: cache[cik]=cf(cik); time.sleep(.04)
   f=feat(cache[cik],asof)
   if f is not None:
    rr=ret1(row.ticker,y)
    if rr is not None:vals.append({'ticker':row.ticker,'cik':str(cik),'margin_improvement':f,'forward_return':rr})
  except Exception:pass
 coverage=len(vals)/len(s); ready=coverage>=.80
 if ready:
  v=sorted(vals,key=lambda x:x['margin_improvement'],reverse=True); k=max(1,int(np.ceil(.30*len(v)))); sel=v[:k]; sr=float(np.mean([x['forward_return'] for x in sel])-COST); ctrl=float(np.mean([x['forward_return'] for x in v])-COST); spy=ret1('SPY',y); spy=(spy-COST) if spy is not None else None
  coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(v),'coverage':coverage,'ready':True,'selected_n':k,'selected_return':sr,'sample_control_return':ctrl,'excess_vs_sample':sr-ctrl,'spy_return':spy,'excess_vs_spy':sr-spy if spy is not None else None})
 else:coh.append({'year':y,'revision_id':int(rev['revid']),'common_n':len(vals),'coverage':coverage,'ready':False})
ready=[x for x in coh if x['ready']]; sup=len(ready)==len(YEARS) and np.mean([x['excess_vs_sample'] for x in ready])>0 and np.mean([x['excess_vs_spy'] for x in ready])>0 and sum(x['excess_vs_sample']>0 for x in ready)>=5
out={'schema':'research.p493_pit_operating_margin_improvement_r1.v1','workload_id':'P493_PIT_OPERATING_MARGIN_IMPROVEMENT_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Filed-at-safe improvement in annual operating margin identifies improving economics that raises one-year returns versus contemporaneous sample and SPY.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'40 evenly spaced historical S&P members after ticker sort','feature':'latest annual OperatingIncomeLoss/Revenue minus prior annual margin using 10-K facts filed by June 30','selection':'top 30% largest margin improvement','common_sample_coverage_min':.80,'entry_cost_bps':10,'acceptance':'all cohorts coverage-ready; mean excess >0 vs sample and SPY; sample excess positive >=5/7 years','no_rescue':True},'cohorts':coh,'decision':'PIT_MARGIN_IMPROVEMENT_ALPHA_SUPPORTED' if sup else ('PIT_MARGIN_IMPROVEMENT_DATA_NOT_READY' if len(ready)<len(YEARS) else 'PIT_MARGIN_IMPROVEMENT_ALPHA_NOT_SUPPORTED'),'scientific_consequence':'Qualify for independent validation.' if sup else 'Reject exact mechanism if coverage complete; otherwise preserve as data-not-ready without threshold/date/feature rescue.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'cohorts':coh},sort_keys=True))