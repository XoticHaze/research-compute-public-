from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P496 research@example.invalid'; YEARS=list(range(2018,2025)); N=20; COST=.0025
OUT=Path('research/artifacts/p496_pit_equity_assets_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
EQUITY=['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']
def hist(asof):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':asof+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0];h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy();z.columns=['ticker','cik'];z.ticker=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z.cik=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def facts(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def latest(cf,names,asof):
 g=cf.get('facts',{}).get('us-gaap',{});vals=[]
 for name in names:
  for v in g.get(name,{}).get('units',{}).get('USD',[]):
   if v.get('form') in ('10-K','10-Q') and not v.get('start') and v.get('filed') and v.get('end') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:vals.append((v['filed'],v['end'],float(v['val']),name))
 return max(vals,key=lambda x:(x[0],x[1])) if vals else None
def fwd(tickers,y):
 raw=yf.download(tickers,start=f'{y}-07-01',end=f'{y+1}-07-10',auto_adjust=True,progress=False,threads=False)
 if raw.empty:return {}
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series):c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t in c.columns:
   s=c[t].dropna()
   if len(s)>=2:out[t]=float(s.iloc[-1]/s.iloc[0]-1)
 return out
cache={};coh=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');feats=[]
 for _,row in s.iterrows():
  try:
   cik=int(row.cik)
   if cik not in cache:cache[cik]=facts(cik);time.sleep(.06)
   a=latest(cache[cik],['Assets'],asof);e=latest(cache[cik],EQUITY,asof)
   if a and e and a[2]>0:feats.append({'ticker':row.ticker,'cik':str(cik),'equity_assets':e[2]/a[2]})
  except Exception:pass
 rets=fwd([x['ticker'] for x in feats],y);usable=[x for x in feats if x['ticker'] in rets];fr=len(feats)/len(s);pr=len(usable)/len(s);usable=sorted(usable,key=lambda x:x['equity_assets']);k=max(1,len(usable)//4);top=usable[-k:] if usable else [];ready=fr>=.80 and pr>=.80 and len(top)>=4
 if ready:
  cand=float(np.mean([rets[x['ticker']] for x in top]))-COST;ctl=float(np.mean([rets[x['ticker']] for x in usable]))-COST;exc=cand-ctl
 else:cand=ctl=exc=None
 coh.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(feats),'usable_price_n':len(usable),'feature_rate':fr,'price_rate':pr,'selected_n':len(top),'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'after_cost_excess_return':exc,'selected_tickers':[x['ticker'] for x in top]})
valid=[x for x in coh if x['ready']];pos=sum(x['after_cost_excess_return']>0 for x in valid);allready=len(valid)==len(YEARS)
if allready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1);bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/len(valid))-1);ex=cg-bg
else:cg=bg=ex=None
sup=allready and pos>=5 and ex is not None and ex>0;dec='PIT_CAPITAL_STRUCTURE_ALPHA_SUPPORTED' if sup else ('PIT_CAPITAL_STRUCTURE_ALPHA_NOT_SUPPORTED' if allready else 'PIT_CAPITAL_STRUCTURE_DATA_NOT_READY')
out={'schema':'research.p496_pit_equity_assets_r1.v1','workload_id':'P496_PIT_EQUITY_ASSETS_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Using only the already high-coverage filed-at Assets and StockholdersEquity concepts, test whether high equity/assets (low balance-sheet leverage) predicts superior one-year after-cost return versus the same contemporaneous historical-universe sample.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'20 evenly spaced historical S&P members after ticker sort','feature':'latest filed-at StockholdersEquity-or-including-NCI divided by Assets by June 30','selection':'top quartile equity/assets','matched_control':'equal-weight same usable historical sample','endpoint_cost_bps':25,'feature_and_price_coverage_min':.80,'all_years_required':True,'acceptance':'all cohorts ready; positive compounded excess; >=5/7 annual excess-positive','no_rescue':True},'cohorts':coh,'summary':{'ready_years':len(valid),'positive_excess_years':pos,'candidate_compound_cagr':cg,'control_compound_cagr':bg,'after_cost_excess_cagr':ex},'decision':dec,'scientific_consequence':'Qualify only if frozen acceptance passes; otherwise reject exact capital-structure formulation or classify data-not-ready without threshold/date/concept rescue.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':dec,'summary':out['summary'],'coverage':{str(x['year']):[round(x['feature_rate'],2),round(x['price_rate'],2),x['ready']] for x in coh}},sort_keys=True))