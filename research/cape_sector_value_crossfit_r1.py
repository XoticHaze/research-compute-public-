import datetime as dt,json,urllib.request
from pathlib import Path
C=json.loads(Path('research/cape-sector-value-crossfit-r1.json').read_text()); START=dt.datetime.fromisoformat(C['start']+'T00:00:00+00:00'); END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)
def fetch(s):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={int(START.timestamp())}&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true'; req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=30) as r:o=json.load(r)['chart']['result'][0]
 a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']; return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}
def solve(A,b):
 n=len(b); m=[list(map(float,A[i]))+[float(b[i])] for i in range(n)]
 for c in range(n):
  p=max(range(c,n),key=lambda r:abs(m[r][c]));m[c],m[p]=m[p],m[c];d=m[c][c]
  if abs(d)<1e-12:raise RuntimeError('singular')
  m[c]=[x/d for x in m[c]]
  for r in range(n):
   if r!=c:
    f=m[r][c];m[r]=[m[r][j]-f*m[c][j] for j in range(n+1)]
 return [m[i][-1] for i in range(n)]
def ols(rs):
 p=4;xx=[[0.0]*p for _ in range(p)];xy=[0.0]*p
 for r in rs:
  x=[1,r['SPY'],r['VTV'],r['RSP']];y=r['CAPE']
  for i in range(p):
   xy[i]+=x[i]*y
   for j in range(p):xx[i][j]+=x[i]*x[j]
 for i in range(1,p):xx[i][i]+=1e-8
 return solve(xx,xy)
def ann(v):
 if not v:return None
 w=1
 for x in v:w*=1+x
 return w**(12/len(v))-1
def comp(v):
 w=1
 for x in v:w*=1+x
 return w-1
px={s:fetch(s) for s in C['symbols']};common=sorted(set.intersection(*(set(px[s]) for s in C['symbols'])));ms={}
for d in common:ms.setdefault(d[:7],[]).append(d)
rows=[]
for m,ds in sorted(ms.items()):
 if len(ds)<10 or m+'-01'<C['evaluation_start']:continue
 f,l=ds[0],ds[-1];rows.append({'month':m,**{s:px[s][l]/px[s][f]-1 for s in C['symbols']}})
cost=C['incremental_cost_bps_per_year']/10000/12;held=[]
for y in sorted({r['month'][:4] for r in rows}):
 tr=[r for r in rows if r['month'][:4]!=y];te=[r for r in rows if r['month'][:4]==y]
 if len(tr)<60 or len(te)<6:continue
 b=ols(tr)
 for r in te:held.append({'month':r['month'],'residual':r['CAPE']-(b[0]+b[1]*r['SPY']+b[2]*r['VTV']+b[3]*r['RSP'])-cost})
yr={}
for r in held:yr.setdefault(r['month'][:4],[]).append(r['residual'])
yc={y:comp(v) for y,v in yr.items()};res=[r['residual'] for r in held];rec=[r['residual'] for r in held if r['month']+'-01'>=C['recent_start']];net=[r['CAPE']-cost for r in rows]
m={'months':len(rows),'full_cape_net_cagr':ann(net),'full_spy_cagr':ann([r['SPY'] for r in rows]),'full_excess_vs_spy':ann(net)-ann([r['SPY'] for r in rows]),'full_crossfit_residual_annualized':ann(res),'recent_crossfit_residual_annualized':ann(rec),'positive_heldout_year_fraction':sum(v>0 for v in yc.values())/len(yc),'worst_heldout_year_residual':min(yc.values()),'heldout_year_residuals':yc};g=C['gates'];ch={'full':m['full_crossfit_residual_annualized']>=g['min_full_residual'],'recent':m['recent_crossfit_residual_annualized']>=g['min_recent_residual'],'years':m['positive_heldout_year_fraction']>=g['min_positive_year_fraction'],'worst':m['worst_heldout_year_residual']>=g['min_worst_year'],'spy':m['full_excess_vs_spy']>=g['min_full_excess_vs_spy']};out={'schema':'cape_sector_value_crossfit_result.v1','experiment_id':C['experiment_id'],'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Yahoo Finance chart adjusted-close public endpoint','metrics':m,'checks':ch,'decision':'PASS_IMPLEMENTATION_DISCRIMINATOR' if all(ch.values()) else 'REJECT_IMPLEMENTATION_CLAIM','research_only':True};Path('cape-sector-value-crossfit-r1-result.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))
