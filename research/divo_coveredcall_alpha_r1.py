import json, math, statistics, urllib.request
from datetime import datetime, timezone
TARGET='DIVO'; BENCH='SPY'; CASH='BIL'; START=1470009600; END=1893456000; COST_ANNUAL=0.001
GATES={'full_excess_cagr_pp':1.0,'recent_2022_excess_cagr_pp':0.5,'positive_calendar_year_fraction':0.60,'worst_relative_year_pp':-8.0,'rolling36_positive_fraction':0.60}
def fetch(t):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={START}&period2={END}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'; req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 try:
  with urllib.request.urlopen(req,timeout=30) as r:j=json.load(r)
  x=j['chart']['result'][0]; return {datetime.fromtimestamp(a,timezone.utc).date():b for a,b in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if b is not None}
 except Exception as e:return {'__error__':f'{type(e).__name__}: {e}'}
def me(d):
 if '__error__' in d:return {}
 o={}
 for k,v in sorted(d.items()):o[(k.year,k.month)]=v
 return o
def rets(m):
 ks=sorted(m); return {ks[i]:m[ks[i]]/m[ks[i-1]]-1 for i in range(1,len(ks))}
def cagr(rs):return None if not rs else math.prod(1+x for x in rs)**(12/len(rs))-1
def main():
 raw={t:fetch(t) for t in [TARGET,BENCH,CASH]}; counts={t:(0 if '__error__' in raw[t] else len(raw[t])) for t in raw}; errors={t:raw[t].get('__error__') for t in raw if '__error__' in raw[t]}; data={t:rets(me(raw[t])) for t in raw}; months=sorted(set(data[TARGET])&set(data[BENCH])&set(data[CASH]))
 if len(months)<48:
  out={'schema':'cc.market_research.divo_coveredcall_alpha.r1','decision':'UNSCORED_INSUFFICIENT_HISTORY','source_counts':counts,'source_errors':errors,'overlap_months':len(months),'gates':GATES}; open('divo-coveredcall-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2)); return
 rows=[]
 for i,m in enumerate(months):
  if i<36:continue
  h=months[i-36:i]; x=[data[BENCH][z] for z in h]; y=[data[TARGET][z] for z in h]; mx,my=statistics.mean(x),statistics.mean(y); vx=statistics.variance(x); beta=(sum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-1))/vx if vx>0 else 0; beta=max(0,min(1,beta)); ctrl=beta*data[BENCH][m]+(1-beta)*data[CASH][m]; tgt=data[TARGET][m]-COST_ANNUAL/12; rows.append((m,tgt,ctrl,beta))
 years=sorted(set(r[0][0] for r in rows)); yr=[]
 for y in years:
  q=[r for r in rows if r[0][0]==y]; yr.append((y,cagr([r[1] for r in q])-cagr([r[2] for r in q])))
 roll=[]
 for i in range(35,len(rows)):
  q=rows[i-35:i+1]; roll.append(cagr([r[1] for r in q])-cagr([r[2] for r in q]))
 recent=[r for r in rows if r[0]>=(2022,1)]; ft,fc=cagr([r[1] for r in rows]),cagr([r[2] for r in rows]); metrics={'months':len(rows),'full_target_cagr':ft,'full_control_cagr':fc,'full_excess_cagr_pp':100*(ft-fc),'recent_2022_excess_cagr_pp':100*(cagr([r[1] for r in recent])-cagr([r[2] for r in recent])),'positive_calendar_year_fraction':sum(v>0 for _,v in yr)/len(yr),'positive_calendar_years':sum(v>0 for _,v in yr),'calendar_years':len(yr),'worst_relative_year_pp':100*min(v for _,v in yr),'rolling36_positive_fraction':sum(v>0 for v in roll)/len(roll),'median_beta':statistics.median(r[3] for r in rows)}; passes={k:metrics[k]>=v for k,v in GATES.items()}; out={'schema':'cc.market_research.divo_coveredcall_alpha.r1','claim':'DIVO active equity plus covered-call implementation delivers durable after-cost alpha beyond causal equity/cash exposure','frozen':{'cost_annual':COST_ANNUAL,'beta_window_months':36,'control':'trailing-36m beta * SPY + remainder BIL','gates':GATES},'source_counts':counts,'metrics':metrics,'passes':passes,'decision':'PROMOTE' if all(passes.values()) else 'REJECT_NO_RESCUE','calendar_year_relative_pp':{str(y):100*v for y,v in yr}}; open('divo-coveredcall-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__':main()
