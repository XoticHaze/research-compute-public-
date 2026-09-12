import json, statistics, urllib.request
from datetime import datetime, timezone
T=['FCNTX','SPY','QQQ','VTV']; START=915148800; END=1893456000; COST=0.001
G={'full_residual_alpha_pct':1.0,'recent_2022_residual_alpha_pct':1.0,'positive_year_fraction':0.60,'worst_year_residual_pct':-8.0}
def fetch(t):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={START}&period2={END}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'; req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=30) as r:j=json.load(r)
 x=j['chart']['result'][0]; return {datetime.fromtimestamp(a,timezone.utc).date():b for a,b in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if b is not None}
def mr(d):
 o={}
 for k,v in sorted(d.items()):o[(k.year,k.month)]=v
 ks=sorted(o); return {ks[i]:o[ks[i]]/o[ks[i-1]]-1 for i in range(1,len(ks))}
def solve(a,b):
 n=len(b); a=[row[:] + [b[i]] for i,row in enumerate(a)]
 for i in range(n):
  p=max(range(i,n),key=lambda r:abs(a[r][i])); a[i],a[p]=a[p],a[i]
  if abs(a[i][i])<1e-12:return [0.0]*n
  q=a[i][i]; a[i]=[x/q for x in a[i]]
  for r in range(n):
   if r==i:continue
   q=a[r][i]; a[r]=[x-q*y for x,y in zip(a[r],a[i])]
 return [a[i][-1] for i in range(n)]
def fit(rows):
 X=[[1.0,r[2],r[3],r[4]] for r in rows]; y=[r[1] for r in rows]; p=4
 return solve([[sum(x[i]*x[j] for x in X) for j in range(p)] for i in range(p)],[sum(x[i]*z for x,z in zip(X,y)) for i in range(p)])
def main():
 d={t:mr(fetch(t)) for t in T}; months=sorted(set(d['FCNTX'])&set(d['SPY'])&set(d['QQQ'])&set(d['VTV'])); rows=[(m,d['FCNTX'][m]-COST/12,d['SPY'][m],d['QQQ'][m],d['VTV'][m]) for m in months]; years=sorted(set(m[0] for m in months)); held=[]; yr={}
 for y in years:
  train=[r for r in rows if r[0][0]!=y]; test=[r for r in rows if r[0][0]==y]
  if len(train)<120 or len(test)<6:continue
  b=fit(train); vals=[r[1]-(b[0]+b[1]*r[2]+b[2]*r[3]+b[3]*r[4]) for r in test]; yr[y]=100*12*statistics.mean(vals); held += [(r[0],v) for r,v in zip(test,vals)]
 if not held:out={'schema':'cc.market_research.fcntx_active_growth_alpha.r1','decision':'UNSCORED_INSUFFICIENT_CROSSFIT_HISTORY','overlap_months':len(months)}
 else:
  recent=[v for m,v in held if m>=(2022,1)]; metrics={'months':len(held),'years':len(yr),'full_residual_alpha_pct':100*12*statistics.mean(v for _,v in held),'recent_2022_residual_alpha_pct':100*12*statistics.mean(recent),'positive_year_fraction':sum(v>0 for v in yr.values())/len(yr),'positive_years':sum(v>0 for v in yr.values()),'worst_year_residual_pct':min(yr.values())}; passes={k:metrics[k]>=v for k,v in G.items()}; out={'schema':'cc.market_research.fcntx_active_growth_alpha.r1','claim':'FCNTX long-lived active growth stock selection delivers durable after-cost alpha beyond broad, Nasdaq-growth, and value exposures','frozen':{'target':'FCNTX','factors':['SPY','QQQ','VTV'],'leave_one_calendar_year_out':True,'minimum_training_months':120,'cost_annual':COST,'gates':G},'metrics':metrics,'passes':passes,'decision':'PROMOTE' if all(passes.values()) else 'REJECT_NO_RESCUE','year_residual_alpha_pct':yr}
 open('fcntx-active-growth-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__':main()
