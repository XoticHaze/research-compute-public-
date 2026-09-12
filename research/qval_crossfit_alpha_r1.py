import json, statistics, urllib.request
from datetime import datetime, timezone
T=['QVAL','SPY','VTV']; START=1412121600; END=1893456000; COST=0.001
G={'full_residual_alpha_pct':1.0,'recent_2022_residual_alpha_pct':1.0,'positive_year_fraction':0.60,'worst_year_residual_pct':-8.0}
def fetch(t):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={START}&period2={END}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'; req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=30) as r:j=json.load(r)
 x=j['chart']['result'][0]; return {datetime.fromtimestamp(a,timezone.utc).date():b for a,b in zip(x['timestamp'],x['indicators']['adjclose'][0]['adjclose']) if b is not None}
def mr(d):
 o={}
 for k,v in sorted(d.items()):o[(k.year,k.month)]=v
 ks=sorted(o); return {ks[i]:o[ks[i]]/o[ks[i-1]]-1 for i in range(1,len(ks))}
def fit(rows):
 y=[r[1] for r in rows]; x1=[r[2] for r in rows]; x2=[r[3] for r in rows]; my,m1,m2=map(statistics.mean,[y,x1,x2]); n=len(rows)-1
 c11=sum((x-m1)**2 for x in x1)/n; c22=sum((x-m2)**2 for x in x2)/n; c12=sum((a-m1)*(b-m2) for a,b in zip(x1,x2))/n; cy1=sum((a-my)*(b-m1) for a,b in zip(y,x1))/n; cy2=sum((a-my)*(b-m2) for a,b in zip(y,x2))/n; det=c11*c22-c12*c12
 if abs(det)<1e-12:return my,0,0
 b1=(cy1*c22-cy2*c12)/det; b2=(cy2*c11-cy1*c12)/det; return my-b1*m1-b2*m2,b1,b2
def main():
 d={t:mr(fetch(t)) for t in T}; months=sorted(set(d['QVAL'])&set(d['SPY'])&set(d['VTV'])); rows=[(m,d['QVAL'][m]-COST/12,d['SPY'][m],d['VTV'][m]) for m in months]; years=sorted(set(m[0] for m in months)); held=[]; yr={}
 for y in years:
  train=[r for r in rows if r[0][0]!=y]; test=[r for r in rows if r[0][0]==y]
  if len(train)<60 or len(test)<6:continue
  a,b1,b2=fit(train); vals=[r[1]-(a+b1*r[2]+b2*r[3]) for r in test]; yr[y]=100*12*statistics.mean(vals); held += [(r[0],v) for r,v in zip(test,vals)]
 if not held:out={'decision':'UNSCORED_INSUFFICIENT_CROSSFIT_HISTORY','months':len(months)}
 else:
  recent=[v for m,v in held if m>=(2022,1)]; metrics={'months':len(held),'years':len(yr),'full_residual_alpha_pct':100*12*statistics.mean(v for _,v in held),'recent_2022_residual_alpha_pct':100*12*statistics.mean(recent),'positive_year_fraction':sum(v>0 for v in yr.values())/len(yr),'positive_years':sum(v>0 for v in yr.values()),'worst_year_residual_pct':min(yr.values())}; passes={k:metrics[k]>=v for k,v in G.items()}; out={'schema':'cc.market_research.qval_crossfit_alpha.r1','claim':'QVAL concentrated systematic value delivers durable after-cost implementation alpha beyond broad and value exposures','frozen':{'target':'QVAL','factors':['SPY','VTV'],'leave_one_calendar_year_out':True,'cost_annual':COST,'gates':G},'metrics':metrics,'passes':passes,'decision':'PROMOTE' if all(passes.values()) else 'REJECT_NO_RESCUE','year_residual_alpha_pct':yr}
 open('qval-crossfit-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__':main()
