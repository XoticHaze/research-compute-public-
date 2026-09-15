import datetime as dt,json,urllib.request
from pathlib import Path
SYMS=['PFF','HYG','IEF','SPY']; START=dt.datetime(2008,1,1,tzinfo=dt.timezone.utc); END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1); COST=0.0010/12

def fetch(s):
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={int(START.timestamp())}&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true';q=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(q,timeout=30) as r:o=json.load(r)['chart']['result'][0]
 a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close'];return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}
def solve(A,b):
 n=len(b);m=[A[i][:]+[b[i]] for i in range(n)]
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
  x=[1,r['HYG'],r['IEF'],r['SPY']];y=r['PFF']-COST
  for i in range(p):
   xy[i]+=x[i]*y
   for j in range(p):xx[i][j]+=x[i]*x[j]
 for i in range(1,p):xx[i][i]+=1e-8
 return solve(xx,xy)
def ann(v):
 w=1
 for x in v:w*=1+x
 return w**(12/len(v))-1 if v else None
def dd(v):
 w=peak=1;d=0
 for x in v:w*=1+x;peak=max(peak,w);d=min(d,w/peak-1)
 return d
px={s:fetch(s) for s in SYMS}; common=sorted(set.intersection(*(set(px[s]) for s in SYMS))); ms={}
for d in common:ms.setdefault(d[:7],[]).append(d)
rows=[]
for m,ds in sorted(ms.items()):
 if len(ds)<10:continue
 f,l=ds[0],ds[-1];rows.append({'month':m,**{s:px[s][l]/px[s][f]-1 for s in SYMS}})
rows=[r for r in rows if r['month']>='2008-05']; held=[]
for y in sorted({r['month'][:4] for r in rows}):
 tr=[r for r in rows if r['month'][:4]!=y];te=[r for r in rows if r['month'][:4]==y]
 if len(tr)<72 or len(te)<6:continue
 b=ols(tr)
 for r in te:held.append((r['month'],(r['PFF']-COST)-(b[0]+b[1]*r['HYG']+b[2]*r['IEF']+b[3]*r['SPY'])))
yrs={}
for m,x in held:yrs.setdefault(m[:4],[]).append(x)
yann={y:ann(v) for y,v in yrs.items()}; full=[r['PFF']-COST for r in rows]; recent=[x for m,x in held if m>='2020-01']; resid=[x for _,x in held]
metrics={'months':len(rows),'pff_after_cost_cagr':ann(full),'spy_cagr':ann([r['SPY'] for r in rows]),'after_cost_excess_vs_spy':ann(full)-ann([r['SPY'] for r in rows]),'crossfit_residual_ann':ann(resid),'recent_2020_crossfit_residual_ann':ann(recent),'positive_year_fraction':sum(v>0 for v in yann.values())/len(yann),'worst_year_residual':min(yann.values()),'max_drawdown':dd(full),'heldout_year_residuals':yann}
checks={'full_residual':metrics['crossfit_residual_ann']>=0.01,'recent_residual':metrics['recent_2020_crossfit_residual_ann']>=0.005,'breadth':metrics['positive_year_fraction']>=0.60,'worst_year':metrics['worst_year_residual']>=-0.08,'spy_excess':metrics['after_cost_excess_vs_spy']>0}
out={'schema':'preferred_carry_residual_r1.v1','claim':'Preferred-stock carry provides durable after-cost residual return beyond high-yield credit, duration, and broad equity beta.','information_time':'month-end total returns; investable wrapper observed contemporaneously','universe':SYMS,'cost':'10 bp annualized wrapper drag charged monthly to PFF only','matched_control':'leave-one-calendar-year-out OLS on HYG, IEF, SPY monthly returns','strongest_non_alpha_explanation':'PFF return is compensated credit, duration, and equity beta rather than independent carry alpha','protected_boundary':'No symbol, factor, date, cost, threshold, or heldout-unit rescue after result.','metrics':metrics,'checks':checks,'decision':'PREFERRED_CARRY_RESIDUAL_SUPPORTED' if all(checks.values()) else 'PREFERRED_CARRY_RESIDUAL_REJECTED','research_only':True,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat()};Path('preferred-carry-residual-r1-result.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))