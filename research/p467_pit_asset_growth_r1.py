from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P467 research@example.invalid'; YEARS=list(range(2018,2025)); N=20; COST=.0025
OUT=Path('research/artifacts/p467_pit_asset_growth_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual_asset_growth(facts,asof):
 vals=[]
 for v in facts.get('facts',{}).get('us-gaap',{}).get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
   vals.append((v['end'],v['filed'],float(v['val']),v.get('accn')))
 if not vals:return None
 by_end={}
 for end,filed,val,accn in vals:
  cur=by_end.get(end)
  if cur is None or filed>cur[0]: by_end[end]=(filed,val,accn)
 ordered=sorted(by_end.items(),key=lambda kv:kv[0])
 if len(ordered)<2:return None
 (e0,(f0,a0,x0)),(e1,(f1,a1,x1))=ordered[-2],ordered[-1]
 days=(pd.Timestamp(e1)-pd.Timestamp(e0)).days
 if not (300<=days<=430) or a0<=0:return None
 return {'asset_growth':float(a1/a0-1),'assets_prior':a0,'assets_current':a1,'period_prior':e0,'period_current':e1,'filed_prior':f0,'filed_current':f1}
def fwd_returns(tickers,start,end):
 if not tickers:return {}
 raw=yf.download(tickers,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 if raw.empty:return {}
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series): c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t not in c.columns:continue
  s=c[t].dropna()
  if len(s)>=2: out[t]=float(s.iloc[-1]/s.iloc[0]-1)
 return out
cache={}; cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30'; rev,z=hist(asof); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker')
 feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache: cache[cik]=cf(cik); time.sleep(.08)
   f=annual_asset_growth(cache[cik],asof)
   if f: feats.append({'ticker':row.ticker,'cik':str(cik),**f})
  except Exception: pass
 tick=[x['ticker'] for x in feats]; rets=fwd_returns(tick,f'{y}-07-01',f'{y+1}-07-10')
 usable=[x for x in feats if x['ticker'] in rets]; feature_rate=len(feats)/len(s); price_rate=len(usable)/len(s)
 usable=sorted(usable,key=lambda a:a['asset_growth']); k=max(1,len(usable)//4); selected=usable[:k] if usable else []
 ready=feature_rate>=.80 and price_rate>=.80 and len(selected)>=4
 if ready:
  cand=float(np.mean([rets[x['ticker']] for x in selected]))-COST; ctl=float(np.mean([rets[x['ticker']] for x in usable]))-COST; excess=cand-ctl
 else: cand=ctl=excess=None
 cohorts.append({'year':y,'asof':asof,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(feats),'usable_price_n':len(usable),'feature_rate':feature_rate,'price_rate':price_rate,'selected_n':len(selected),'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'after_cost_excess_return':excess,'selected_tickers':[x['ticker'] for x in selected]})
valid=[x for x in cohorts if x['ready']]; pos=sum(x['after_cost_excess_return']>0 for x in valid); all_ready=len(valid)==len(YEARS)
if all_ready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1); bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/len(valid))-1); ex=cg-bg
else: cg=bg=ex=None
supported=all_ready and pos>=5 and ex is not None and ex>0
decision='PIT_ASSET_GROWTH_ALPHA_SUPPORTED' if supported else ('PIT_ASSET_GROWTH_ALPHA_NOT_SUPPORTED' if all_ready else 'PIT_ASSET_GROWTH_ALPHA_DATA_NOT_READY')
out={'schema':'research.p467_pit_asset_growth_r1.v1','workload_id':'P467_PIT_ASSET_GROWTH_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Materially different causal fundamental mechanism after ROA rejection: conservative investment via lowest trailing annual asset growth. Uses fixed June-30 historical S&P universes, deterministic 20-name samples, latest two annual 10-K Assets observations filed by rebalance date, bottom-quartile asset-growth selection, same-universe equal-weight control, fixed costs, forward 12-month returns, and fail-closed coverage. No ROA threshold rescue, current-membership fill, future filings, post-return constituent dropping, date/product/threshold tuning, or factor blending.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'20 evenly spaced after ticker sort','feature':'latest causal annual Assets growth from two consecutive annual 10-K periods filed by rebalance date','portfolio':'bottom quartile asset growth','matched_control':'equal-weight same deterministic historical sample','endpoint_cost_bps':25,'annual_feature_and_price_coverage_min':.80,'all_years_required':True},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_excess_years':pos,'candidate_compound_cagr':cg,'control_compound_cagr':bg,'after_cost_excess_cagr':ex},'decision_rule':'Support only if every fixed year clears >=80% causal feature and price coverage, >=5/7 annual cohorts have positive after-cost same-universe excess, and compounded candidate CAGR exceeds the same-universe control. Otherwise reject or classify data-not-ready; no rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'summary':out['summary'],'coverage':{str(x['year']):[round(x['feature_rate'],2),round(x['price_rate'],2),x['ready']] for x in cohorts}},sort_keys=True))
