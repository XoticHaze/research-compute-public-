from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P471 research@example.invalid'; YEARS=list(range(2018,2025)); N=20; COST=.0025
REV_TAGS=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues']
COGS_TAGS=['CostOfRevenue','CostOfGoodsAndServicesSold','CostOfGoodsSold']
OUT=Path('research/artifacts/p471_pit_gross_profitability_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy();z.columns=['ticker','cik'];z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual_flows(g,tags,asof):
 out=[]
 for tag in tags:
  for v in g.get(tag,{}).get('units',{}).get('USD',[]):
   if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
    days=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
    if 300<=days<=430:out.append((v['end'],v['filed'],float(v['val']),tag,v['start']))
 return out
def gross_profitability(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); rev=annual_flows(g,REV_TAGS,asof); cogs=annual_flows(g,COGS_TAGS,asof)
 if not rev or not cogs:return None
 common=sorted(set(x[0] for x in rev)&set(x[0] for x in cogs))
 if not common:return None
 end=common[-1];rv=max([x for x in rev if x[0]==end],key=lambda x:x[1]);cv=max([x for x in cogs if x[0]==end],key=lambda x:x[1]);start=rv[4]
 assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v.get('val') is not None:
   assets.append((v['end'],v['filed'],float(v['val'])))
 prior=[x for x in assets if x[0] < end]
 if not prior:return None
 pa=max(prior,key=lambda x:(x[0],x[1]))
 if pa[2]<=0:return None
 gp=rv[2]-cv[2]
 return {'gross_profitability':gp/pa[2],'revenue':rv[2],'cost_of_revenue':cv[2],'lagged_assets':pa[2],'period_end':end,'revenue_tag':rv[3],'cost_tag':cv[3],'revenue_filed':rv[1],'cost_filed':cv[1],'assets_period_end':pa[0],'assets_filed':pa[1]}
def fwd(tickers,start,end):
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
cache={};cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.07)
   x=gross_profitability(cache[cik],asof)
   if x:feats.append({'ticker':row.ticker,'cik':str(cik),**x})
  except Exception:pass
 rr=fwd([x['ticker'] for x in feats],f'{y}-07-01',f'{y+1}-07-10');usable=[x for x in feats if x['ticker'] in rr];fr=len(feats)/len(s);pr=len(usable)/len(s)
 usable=sorted(usable,key=lambda x:x['gross_profitability']);k=max(1,len(usable)//4);top=usable[-k:] if usable else [];ready=fr>=.80 and pr>=.80 and len(top)>=4
 if ready:
  cand=float(np.mean([rr[x['ticker']] for x in top]))-COST;ctl=float(np.mean([rr[x['ticker']] for x in usable]))-COST;ex=cand-ctl
 else:cand=ctl=ex=None
 cohorts.append({'year':y,'asof':asof,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(feats),'usable_price_n':len(usable),'feature_rate':fr,'price_rate':pr,'selected_n':len(top),'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'after_cost_excess_return':ex,'selected':[{'ticker':x['ticker'],'gross_profitability':x['gross_profitability'],'revenue_tag':x['revenue_tag'],'cost_tag':x['cost_tag'],'revenue_filed':x['revenue_filed'],'cost_filed':x['cost_filed'],'assets_filed':x['assets_filed']} for x in top]})
valid=[x for x in cohorts if x['ready']];pos=sum(x['after_cost_excess_return']>0 for x in valid);all_ready=len(valid)==len(YEARS)
if all_ready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1);bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/len(valid))-1);ex=cg-bg
else:cg=bg=ex=None
support=all_ready and pos>=5 and ex is not None and ex>0
decision='PIT_GROSS_PROFITABILITY_ALPHA_SUPPORTED' if support else ('PIT_GROSS_PROFITABILITY_ALPHA_NOT_SUPPORTED' if all_ready else 'PIT_GROSS_PROFITABILITY_DATA_NOT_READY')
out={'schema':'research.p471_pit_gross_profitability_r1.v1','workload_id':'P471_PIT_GROSS_PROFITABILITY_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Prospectively frozen causal gross-profitability test: gross profit is annual 10-K revenue minus annual 10-K cost of revenue, divided by lagged annual Assets, all filed by June 30; rank deterministic historical S&P sample high-to-low and compare top quartile forward after-cost returns with same-universe equal-weight control.','preperformance_tag_map':{'revenue_tags':REV_TAGS,'cost_of_revenue_tags':COGS_TAGS,'selection_rule':'latest common annual period end; within tag list, latest filed observation; tag priority is source list only when period/filed ties','denominator':'latest prior annual 10-K Assets observation before flow period end'},'contract':{'years':YEARS,'sample_n':N,'sample_rule':'20 evenly spaced historical S&P members after ticker sort','portfolio':'top quartile gross profitability','matched_control':'equal-weight same deterministic historical sample','endpoint_cost_bps':25,'feature_coverage_min':.80,'price_coverage_min':.80,'all_years_required':True,'support':'>=5/7 positive after-cost excess cohorts and compounded candidate CAGR > control'},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_excess_years':pos,'candidate_compound_cagr':cg,'control_compound_cagr':bg,'after_cost_excess_cagr':ex},'decision':decision,'no_rescue':{'post_return_tag_selection':False,'roa_rescue':False,'asset_growth_rescue':False,'date_or_threshold_search':False,'factor_blending':False},'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'coverage':{str(x['year']):[round(x['feature_rate'],2),round(x['price_rate'],2),x['ready']] for x in cohorts}},sort_keys=True))