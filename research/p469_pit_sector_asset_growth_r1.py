from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P469 research@example.invalid'; YEARS=list(range(2018,2025)); N=40; COST=.0025; MIN_SECTOR_N=3; MIN_ELIGIBLE_SECTORS=6
OUT=Path('research/artifacts/p469_pit_sector_asset_growth_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); gk=next((low[k] for k in low if k in ('gicssector','sector')),None)
  if sk and ck and gk:
   z=t[[sk,ck,gk]].copy(); z.columns=['ticker','cik','sector']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); z['sector']=z.sector.astype(str).str.strip(); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def ag(facts,asof):
 vals=[]
 for v in facts.get('facts',{}).get('us-gaap',{}).get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None: vals.append((v['end'],v['filed'],float(v['val'])))
 if not vals:return None
 by={}
 for e,f,a in vals:
  if e not in by or f>by[e][0]:by[e]=(f,a)
 o=sorted(by.items())
 if len(o)<2:return None
 e0,(f0,a0)=o[-2]; e1,(f1,a1)=o[-1]; d=(pd.Timestamp(e1)-pd.Timestamp(e0)).days
 if not(300<=d<=430) or a0<=0:return None
 return float(a1/a0-1)
def rets(tickers,start,end):
 if not tickers:return {}
 raw=yf.download(tickers,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 if raw.empty:return {}
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series):c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t in c.columns:
   s=c[t].dropna()
   if len(s)>=2:out[t]=float(s.iloc[-1]/s.iloc[0]-1)
 return out
cache={}; cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30'; rev,z=hist(asof); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker')
 f=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.04)
   x=ag(cache[cik],asof)
   if x is not None:f.append({'ticker':row.ticker,'sector':row.sector,'asset_growth':x})
  except Exception:pass
 rr=rets([x['ticker'] for x in f],f'{y}-07-01',f'{y+1}-07-10'); usable=[x for x in f if x['ticker'] in rr]
 feature_rate=len(f)/len(s);price_rate=len(usable)/len(s); sec={}
 for x in usable:sec.setdefault(x['sector'],[]).append(x)
 eligible={k:v for k,v in sec.items() if len(v)>=MIN_SECTOR_N}; chosen=min(eligible,key=lambda k:np.median([x['asset_growth'] for x in eligible[k]])) if eligible else None
 ready=feature_rate>=.85 and price_rate>=.80 and len(eligible)>=MIN_ELIGIBLE_SECTORS and chosen is not None
 if ready:
  cand=float(np.mean([rr[x['ticker']] for x in eligible[chosen]]))-COST;ctl=float(np.mean([rr[x['ticker']] for x in usable]))-COST;ex=cand-ctl
 else:cand=ctl=ex=None
 cohorts.append({'year':y,'revision_id':int(rev['revid']),'feature_rate':feature_rate,'price_rate':price_rate,'eligible_sector_n':len(eligible),'chosen_sector':chosen,'chosen_sector_n':len(eligible.get(chosen,[])) if chosen else 0,'chosen_median_asset_growth':float(np.median([x['asset_growth'] for x in eligible[chosen]])) if chosen else None,'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'after_cost_excess_return':ex})
valid=[x for x in cohorts if x['ready']];pos=sum(x['after_cost_excess_return']>0 for x in valid);all_ready=len(valid)==len(YEARS)
if all_ready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1);bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/len(valid))-1);ex=cg-bg
else:cg=bg=ex=None
support=all_ready and pos>=5 and ex is not None and ex>0
decision='PIT_SECTOR_ASSET_GROWTH_ALPHA_SUPPORTED' if support else ('PIT_SECTOR_ASSET_GROWTH_ALPHA_NOT_SUPPORTED' if all_ready else 'PIT_SECTOR_ASSET_GROWTH_DATA_NOT_READY')
out={'schema':'research.p469_pit_sector_asset_growth_r1.v1','workload_id':'P469_PIT_SECTOR_ASSET_GROWTH_R1','parent':'P07_INDUSTRY_OPPORTUNITY_ENGINE_SUPPORT','claim':'Materially different industry information architecture: aggregate causal filed-at annual asset-growth fundamentals to historical GICS sector state, select the eligible sector with lowest median asset growth, and test its sampled constituents forward against the same historical-universe control. This asks whether cross-industry aggregation extracts signal after single-stock P467 failed; it is not a P467 threshold/sample rescue.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'40 evenly spaced historical S&P members after ticker sort','feature':'two consecutive annual 10-K Assets values filed by June 30','sector_state':'median asset growth among sample names','eligible_sector_min_names':MIN_SECTOR_N,'eligible_sector_min_count':MIN_ELIGIBLE_SECTORS,'selection':'lowest median asset-growth eligible historical GICS sector','matched_control':'equal-weight all usable names in same deterministic historical sample','endpoint_cost_bps':25,'feature_coverage_min':.85,'price_coverage_min':.80,'all_years_required':True},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_excess_years':pos,'candidate_compound_cagr':cg,'control_compound_cagr':bg,'after_cost_excess_cagr':ex},'decision_rule':'Support only if all seven fixed annual cohorts clear causal coverage, >=5/7 selected-sector cohorts beat the same-universe control after costs, and compound candidate CAGR exceeds control. Otherwise reject or classify data-not-ready; no sector/date/sample/threshold rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'cohorts':[{k:x[k] for k in ['year','ready','eligible_sector_n','chosen_sector','after_cost_excess_return']} for x in cohorts]},sort_keys=True))