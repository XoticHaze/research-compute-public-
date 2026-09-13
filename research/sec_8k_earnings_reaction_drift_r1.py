import bisect,json,math,statistics,time,urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
E='SEC_8K_EARNINGS_REACTION_DRIFT_R1_20260913'; START='2014-01-01'; RECENT='2022-01-01'; TH=.03; NEG=-.03; HOLD=20; COST=.005; SPY='SPY'
UA='XoticHaze market-research causal-event-study contact@example.com'
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
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=1388534400&period2=1789257600&interval=1d&events=div%2Csplits&includeAdjustedClose=true'; x=gj(u)['chart']['result'][0]; q=x['indicators']['quote'][0]; a=x['indicators']['adjclose'][0]['adjclose']; o=[]
 for ts,op,cl,ac in zip(x['timestamp'],q['open'],q['close'],a):
  if op is None or cl in (None,0) or ac is None:continue
  z=float(ac)/float(cl); o.append((date.fromtimestamp(ts).isoformat(),float(op)*z,float(ac)))
 return o
def filings(cik):
 b=gj(f'https://data.sec.gov/submissions/CIK{cik}.json',True); parts=[b.get('filings',{}).get('recent',{})]
 for m in b.get('filings',{}).get('files',[]):
  try:parts.append(gj('https://data.sec.gov/submissions/'+m['name'],True));time.sleep(.11)
  except Exception:pass
 out={}
 for p in parts:
  f=p.get('form',[])
  for i,form in enumerate(f):
   def v(k):
    a=p.get(k,[]);return a[i] if i<len(a) else None
   d=v('filingDate');it=v('items') or '';acc=v('accessionNumber')
   if form=='8-K' and d and d>=START and '2.02' in it and acc:out.setdefault(acc,{'filing_date':d,'acceptance_datetime':v('acceptanceDateTime'),'items':it,'accession':acc})
 return sorted(out.values(),key=lambda z:(z['filing_date'],z['accession'])),len(parts)
def obs(rows,sm,bm,ev):
 ds=[r[0] for r in rows];d=ev['filing_date'];pre=bisect.bisect_left(ds,d)-1;rc=bisect.bisect_right(ds,d);en=rc+1;ex=en+HOLD-1
 if pre<0 or ex>=len(rows):return None
 a,r,e,x=rows[pre],rows[rc],rows[en],rows[ex]
 if any(k not in sm or k not in bm for k in (a[0],r[0],e[0],x[0])):return None
 sr0,sr1,se,sx=sm[a[0]],sm[r[0]],sm[e[0]],sm[x[0]];br0,br1,be,bx=bm[a[0]],bm[r[0]],bm[e[0]],bm[x[0]]
 rr=r[2]/a[2]-1-(sr1[2]/sr0[2]-1);f=x[2]/e[1]-1-COST
 return {'pre_close_date':a[0],'reaction_close_date':r[0],'entry_date':e[0],'exit_date':x[0],'reaction_sector_excess':rr,'reaction_spy_excess':r[2]/a[2]-1-(br1[2]/br0[2]-1),'sector_excess':f-(sx[2]/se[1]-1),'spy_excess':f-(bx[2]/be[1]-1)}
def mean(x):return statistics.fmean(x) if x else None
def med(x):return statistics.median(x) if x else None
def folds(ev,k=5):
 a=sorted(ev,key=lambda e:(e['filing_date'],e['ticker'],e['accession']));n=len(a);o=[]
 for j in range(k):
  p=a[math.floor(j*n/k):math.floor((j+1)*n/k)];x=[e['sector_excess'] for e in p];o.append({'fold':j+1,'n':len(p),'start':p[0]['filing_date'] if p else None,'end':p[-1]['filing_date'] if p else None,'mean_sector_excess':mean(x),'positive':bool(x and mean(x)>0)})
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
  try:fs,n=filings(c[t]);sc=0
  except Exception as z:cov.append({'ticker':t,'status':'SEC_ERROR','error':type(z).__name__});continue
  for ev in fs:
   q=obs(P[t],M[sec],M[SPY],ev)
   if q:r=dict(ev);r.update(q);r.update({'ticker':t,'sector':sec,'year':ev['filing_date'][:4]});all.append(r);sc+=1
  cov.append({'ticker':t,'status':'OK','filing_parts':n,'item_202_events':len(fs),'scored_events':sc});time.sleep(.1)
 pos=[e for e in all if e['reaction_sector_excess']>=TH];neg=[e for e in all if e['reaction_sector_excess']<=NEG];ps=[e['sector_excess'] for e in pos];ns=[e['sector_excess'] for e in neg];sp=[e['spy_excess'] for e in pos];re=[e['sector_excess'] for e in pos if e['filing_date']>=RECENT];F=folds(pos);ts,tw=conc(pos,'ticker');ys,yw=conc(pos,'year');spread=mean(ps)-mean(ns) if ps and ns else None
 g={'positive_events_min_100':len(pos)>=100,'mean_after_cost_sector_excess_positive':bool(ps and mean(ps)>0),'median_after_cost_sector_excess_positive':bool(ps and med(ps)>0),'positive_sector_excess_share_at_least_53pct':bool(ps and mean([x>0 for x in ps])>=.53),'chronology_folds_at_least_3_of_5_positive':sum(x['positive'] for x in F)>=3,'recent_2022_plus_sector_excess_positive':bool(re and mean(re)>0),'positive_beats_negative_control':bool(spread is not None and spread>0),'single_ticker_positive_contribution_share_le_35pct':ts<=.35,'single_year_positive_contribution_share_le_35pct':ys<=.35}
 R={'decision':'SEC_8K_EARNINGS_REACTION_DRIFT_SURVIVES_R1' if all(g.values()) else 'REJECT_NO_PARAMETER_RESCUE','all_item_202_events':len(all),'positive_events':len(pos),'negative_control_events':len(neg),'mean_after_cost_sector_excess':mean(ps),'median_after_cost_sector_excess':med(ps),'mean_after_cost_spy_excess':mean(sp),'positive_sector_excess_share':mean([x>0 for x in ps]) if ps else None,'recent_since_2022_sector_excess':mean(re),'negative_control_mean_sector_excess':mean(ns),'positive_minus_negative_control_sector_excess':spread,'chronology_folds':F,'max_single_ticker_share_of_positive_excess':ts,'max_single_ticker':tw,'max_single_year_share_of_positive_excess':ys,'max_single_year':yw,'gates':g}
 out={'schema':'public_research.sec_8k_earnings_reaction_drift_result.v1','experiment_id':E,'inherited_learning_ids':['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912'],'frozen_specification':{'start_date':START,'reaction_threshold':TH,'negative_control_threshold':NEG,'hold_sessions':HOLD,'round_trip_cost':COST,'feature_available_at':'first trading close strictly after filingDate','earliest_trade_at':'next trading-session open','event_source':'SEC submissions JSON form=8-K items contains 2.02','ticker_to_sector':T,'broad_control':SPY,'chronology_folds':'five contiguous equal-count folds'},'result':R,'source_coverage':cov,'events':all,'limitations':['fixed current liquid panel is a mechanism screen','failure forbids threshold/horizon/cost/ticker/sector/year/control rescue'],'boundaries':{'portfolio_allocation':False,'runtime':False,'broker':False,'live_trading':False}}
 p=Path('research/results/sec_8k_earnings_reaction_drift_r1.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(R,sort_keys=True))
if __name__=='__main__':main()
