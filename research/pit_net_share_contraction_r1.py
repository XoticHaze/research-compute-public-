import bisect,json,math,statistics,time,urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
E='PIT_NET_SHARE_CONTRACTION_R1_20260913';START='2014-01-01';RECENT='2022-01-01';TH=-.02;NEG=.02;HOLD=126;COST=.005;SPY='SPY'
UA='XoticHaze market-research PIT capital-allocation study contact@example.com'
T={'AAPL':'XLK','MSFT':'XLK','NVDA':'SMH','AMD':'SMH','AMAT':'SMH','AVGO':'SMH','JPM':'XLF','BAC':'XLF','GS':'XLF','XOM':'XLE','CVX':'XLE','COP':'XLE','CAT':'XLI','HON':'XLI','GE':'XLI','JNJ':'XLV','LLY':'XLV','UNH':'XLV','PG':'XLP','KO':'XLP','PEP':'XLP','HD':'XLY','MCD':'XLY','NKE':'XLY','TSLA':'XLY','META':'XLC','GOOGL':'XLC','NFLX':'XLC','NEE':'XLU','DUK':'XLU','LIN':'XLB','FCX':'XLB','PLD':'XLRE','AMT':'XLRE'}
def gj(u,sec=False):
 h={'User-Agent':UA if sec else 'Mozilla/5.0 XoticHaze-research/1.0','Accept':'application/json'}
 for n in range(6):
  try:
   with urllib.request.urlopen(urllib.request.Request(u,headers=h),timeout=60) as r:return json.loads(r.read())
  except Exception:
   if n==5:raise
   time.sleep(min(12,.8*(2**n)))
def px(s):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=1388534400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true';x=gj(u)['chart']['result'][0];q=x['indicators']['quote'][0];a=x['indicators']['adjclose'][0]['adjclose'];o=[]
 for ts,op,cl,ac in zip(x['timestamp'],q['open'],q['close'],a):
  if op is None or cl in (None,0) or ac is None:continue
  z=float(ac)/float(cl);o.append((date.fromtimestamp(ts).isoformat(),float(op)*z,float(ac)))
 return o
def annual_shares(cik):
 d=gj(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json',True);dei=d.get('facts',{}).get('dei',{});u=dei.get('EntityCommonStockSharesOutstanding',{}).get('units',{}).get('shares',[]);rows=[]
 for v in u:
  if v.get('form')!='10-K' or not all(v.get(k) is not None for k in ('filed','end','fy','val','accn')):continue
  if v['filed']<START or float(v['val'])<=0:continue
  try:fy=int(v['fy'])
  except:continue
  rows.append({'fy':fy,'filed':v['filed'],'end':v['end'],'shares':float(v['val']),'accn':v['accn']})
 by_filing={}
 for r in rows:
  k=(r['fy'],r['filed'],r['accn']);old=by_filing.get(k)
  if old is None or r['end']>old['end']:by_filing[k]=r
 by_fy={}
 for r in sorted(by_filing.values(),key=lambda z:(z['fy'],z['filed'],z['accn'])):by_fy.setdefault(r['fy'],r)
 return by_fy
def evret(rows,sm,bm,filed):
 ds=[r[0] for r in rows];i=bisect.bisect_right(ds,filed);j=i+HOLD-1
 if i>=len(rows) or j>=len(rows):return None
 a,b=rows[i],rows[j]
 if a[0] not in sm or b[0] not in sm or a[0] not in bm or b[0] not in bm:return None
 sa,sb=sm[a[0]],sm[b[0]];ba,bb=bm[a[0]],bm[b[0]];r=b[2]/a[1]-1-COST
 return {'entry_date':a[0],'exit_date':b[0],'stock_after_cost':r,'sector_excess':r-(sb[2]/sa[1]-1),'spy_excess':r-(bb[2]/ba[1]-1)}
def mean(x):return statistics.fmean(x) if x else None
def med(x):return statistics.median(x) if x else None
def folds(ev,k=5):
 a=sorted(ev,key=lambda e:(e['filed'],e['ticker'],e['fy']));n=len(a);o=[]
 for j in range(k):
  p=a[math.floor(j*n/k):math.floor((j+1)*n/k)];x=[e['sector_excess'] for e in p];o.append({'fold':j+1,'n':len(p),'start':p[0]['filed'] if p else None,'end':p[-1]['filed'] if p else None,'mean_sector_excess':mean(x),'positive':bool(x and mean(x)>0)})
 return o
def conc(ev,key):
 b=defaultdict(float);tot=0
 for e in ev:v=max(0,e['sector_excess']);b[e[key]]+=v;tot+=v
 if tot<=0:return 1,None
 w=max(b,key=b.get);return b[w]/tot,w
def main():
 mp=gj('https://www.sec.gov/files/company_tickers.json',True);c={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()};sy=sorted(set(T)|set(T.values())|{SPY});P={}
 for s in sy:P[s]=px(s);time.sleep(.06)
 M={s:{d:(d,o,cl) for d,o,cl in P[s]} for s in sy};all=[];cov=[]
 for t,sec in T.items():
  try:A=annual_shares(c[t])
  except Exception as z:cov.append({'ticker':t,'status':'SEC_ERROR','error':type(z).__name__});continue
  sc=0
  for fy,r in sorted(A.items()):
   p=A.get(fy-1)
   if not p:continue
   change=r['shares']/p['shares']-1;q=evret(P[t],M[sec],M[SPY],r['filed'])
   if not q:continue
   x=dict(r);x.update(q);x.update({'ticker':t,'sector':sec,'year':r['filed'][:4],'prior_shares':p['shares'],'share_change':change});all.append(x);sc+=1
  cov.append({'ticker':t,'status':'OK','annual_facts':len(A),'scored_events':sc});time.sleep(.1)
 pos=[e for e in all if e['share_change']<=TH];neg=[e for e in all if e['share_change']>=NEG];ps=[e['sector_excess'] for e in pos];ns=[e['sector_excess'] for e in neg];sp=[e['spy_excess'] for e in pos];re=[e['sector_excess'] for e in pos if e['filed']>=RECENT];F=folds(pos);ts,tw=conc(pos,'ticker');ys,yw=conc(pos,'year');spread=mean(ps)-mean(ns) if ps and ns else None
 g={'contraction_events_min_60':len(pos)>=60,'mean_after_cost_sector_excess_positive':bool(ps and mean(ps)>0),'median_after_cost_sector_excess_positive':bool(ps and med(ps)>0),'positive_sector_excess_share_at_least_53pct':bool(ps and mean([x>0 for x in ps])>=.53),'chronology_folds_at_least_3_of_5_positive':sum(x['positive'] for x in F)>=3,'recent_2022_plus_sector_excess_positive':bool(re and mean(re)>0),'contraction_beats_expansion':bool(spread is not None and spread>0),'single_ticker_positive_contribution_share_le_25pct':ts<=.25,'single_year_positive_contribution_share_le_30pct':ys<=.30}
 R={'decision':'PIT_NET_SHARE_CONTRACTION_SURVIVES_R1' if all(g.values()) else 'REJECT_NO_PARAMETER_RESCUE','all_scored_events':len(all),'contraction_events':len(pos),'expansion_control_events':len(neg),'mean_after_cost_sector_excess':mean(ps),'median_after_cost_sector_excess':med(ps),'mean_after_cost_spy_excess':mean(sp),'positive_sector_excess_share':mean([x>0 for x in ps]) if ps else None,'recent_since_2022_sector_excess':mean(re),'expansion_mean_sector_excess':mean(ns),'contraction_minus_expansion_sector_excess':spread,'chronology_folds':F,'max_single_ticker_share_of_positive_excess':ts,'max_single_ticker':tw,'max_single_year_share_of_positive_excess':ys,'max_single_year':yw,'gates':g}
 out={'schema':'public_research.pit_net_share_contraction_result.v1','experiment_id':E,'inherited_learning_ids':['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912'],'frozen_specification':{'source':'SEC CompanyFacts dei EntityCommonStockSharesOutstanding','signal':'annual share change <= -2%','negative_control':'annual share change >= +2%','entry':'first trading-session open strictly after filingDate','holding_sessions':HOLD,'round_trip_cost':COST,'ticker_to_sector':T,'broad_control':SPY},'result':R,'source_coverage':cov,'events':all,'limitations':['fixed current liquid panel is a mechanism screen','first non-amended 10-K fact per fiscal year','failure forbids threshold/horizon/cost/ticker/sector/year/control rescue'],'boundaries':{'portfolio_allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 p=Path('research/results/pit_net_share_contraction_r1.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(R,sort_keys=True))
if __name__=='__main__':main()
