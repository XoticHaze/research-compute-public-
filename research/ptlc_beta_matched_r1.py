import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

C=json.loads(Path('research/ptlc-beta-matched-r1.json').read_text())
START=dt.datetime.fromisoformat(C['start']+'T00:00:00+00:00')
END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)

def fetch(sym):
    u=(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(START.timestamp())}'
       f'&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true')
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as r:o=json.load(r)['chart']['result'][0]
    a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}

px={s:fetch(s) for s in C['symbols']}
common=sorted(set.intersection(*(set(px[s]) for s in C['symbols'])))
months={}
for d in common: months.setdefault(d[:7],[]).append(d)
rows=[]
for m,ds in sorted(months.items()):
    if len(ds)<10: continue
    f,l=ds[0],ds[-1]
    rows.append({'month':m,**{s:px[s][l]/px[s][f]-1 for s in C['symbols']}})

def beta(hist):
    x=[r['SPY']-r['BIL'] for r in hist]; y=[r['PTLC']-r['BIL'] for r in hist]
    mx=sum(x)/len(x); my=sum(y)/len(y)
    den=sum((v-mx)**2 for v in x)
    b=0.0 if den<1e-12 else sum((a-mx)*(b-my) for a,b in zip(x,y))/den
    lo,hi=C['beta_clip']; return max(lo,min(hi,b))

lb=C['beta_lookback_months']; cost=C['incremental_ptlc_cost_bps_per_year']/10000/12
obs=[]
for i in range(lb,len(rows)):
    r=rows[i]
    if r['month']+'-01' < C['evaluation_start']: continue
    b=beta(rows[i-lb:i])
    ctrl=b*r['SPY']+(1-b)*r['BIL']
    ex=r['PTLC']-ctrl-cost
    obs.append({'month':r['month'],'beta':b,'ptlc':r['PTLC'],'control':ctrl,'after_cost_excess':ex})

def ann(xs): return sum(xs)/len(xs)*12 if xs else None
annual=[]
for y in sorted({o['month'][:4] for o in obs}):
    z=[o['after_cost_excess'] for o in obs if o['month'].startswith(y+'-')]
    if len(z)>=11: annual.append({'year':int(y),'months':len(z),'annualized_excess':ann(z),'positive':ann(z)>0})
full=ann([o['after_cost_excess'] for o in obs])
recent=ann([o['after_cost_excess'] for o in obs if o['month']+'-01'>=C['recent_start']])
w=C['rolling_months']; rolls=[]
for i in range(w-1,len(obs)):
    z=[x['after_cost_excess'] for x in obs[i-w+1:i+1]]; rolls.append(ann(z))
pos_year=sum(x['positive'] for x in annual)/len(annual)
pos_roll=sum(x>0 for x in rolls)/len(rolls)
worst=min(x['annualized_excess'] for x in annual)
avg_beta=sum(o['beta'] for o in obs)/len(obs)
g=C['gates']
passed=(full>=g['min_full_after_cost_annualized_excess'] and recent>=g['min_recent_after_cost_annualized_excess'] and pos_year>=g['min_positive_year_fraction'] and pos_roll>=g['min_rolling_positive_fraction'] and worst>=g['min_worst_year_after_cost_excess'])
out={'schema':'ptlc_beta_matched_result.v1','experiment_id':C['experiment_id'],'months':len(obs),'average_causal_beta':avg_beta,'full_after_cost_annualized_excess':full,'recent_after_cost_annualized_excess':recent,'positive_year_fraction':pos_year,'rolling_36m_positive_fraction':pos_roll,'worst_year_after_cost_excess':worst,'annual':annual,'gates':g,'supported':passed,'research_only':True}
Path('ptlc-beta-matched-r1-result.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
