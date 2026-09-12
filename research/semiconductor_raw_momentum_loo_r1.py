import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

C=json.loads(Path('research/semiconductor-raw-momentum-loo-r1.json').read_text())
START=dt.datetime(2018,1,1,tzinfo=dt.timezone.utc); END=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)
SYMS=C['universe']+[C['benchmark']]

def fetch(s):
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={int(START.timestamp())}&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true'
    r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(r,timeout=30) as h:o=json.load(h)['chart']['result'][0]
    a=o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}

def cagr(rs,years):
    e=1.0
    for r in rs:e*=1+r
    return e**(1/years)-1 if e>0 else -1

px={s:fetch(s) for s in SYMS}; dates=sorted(set.intersection(*(set(px[s]) for s in SYMS))); L=C['lookback_sessions']
ml=[i for i,d in enumerate(dates[:-1]) if dates[i+1][:7]!=d[:7]]
periods=[]
for p in ml:
    if p<L or p+1>=len(dates):continue
    q=next((j for j in ml if j>p),None)
    if q is None or q+1>=len(dates):continue
    periods.append((p,p+1,q+1))
years=(dt.date.fromisoformat(dates[periods[-1][2]])-dt.date.fromisoformat(dates[periods[0][1]])).days/365.25
bench=[px[C['benchmark']][dates[x]]/px[C['benchmark']][dates[e]]-1 for _,e,x in periods]

def eval_universe(u,cost):
    prev=set(); rs=[]
    for p,e,x in periods:
        ranked=sorted(u,key=lambda s:px[s][dates[p]]/px[s][dates[p-L]],reverse=True)[:C['top_n']]
        sel=set(ranked); turn=len(sel.symmetric_difference(prev))/(2*C['top_n']) if prev else 1.0
        gross=sum(px[s][dates[x]]/px[s][dates[e]]-1 for s in ranked)/len(ranked)
        rs.append(gross-cost/10000*turn); prev=sel
    return cagr(rs,years)

bc=cagr(bench,years); rows=[]
for omitted in C['universe']:
    u=[s for s in C['universe'] if s!=omitted]
    p=eval_universe(u,C['cost_bps_per_turnover']); s=eval_universe(u,C['stress_cost_bps_per_turnover'])
    rows.append({'omitted':omitted,'primary_cagr':p,'primary_excess_vs_smh_pp':(p-bc)*100,'stress_cagr':s,'stress_excess_vs_smh_pp':(s-bc)*100})
vals=sorted(r['primary_excess_vs_smh_pp'] for r in rows); med=(vals[4]+vals[5])/2
pos=sum(r['primary_excess_vs_smh_pp']>0 for r in rows)/len(rows); spos=sum(r['stress_excess_vs_smh_pp']>0 for r in rows)/len(rows); worst=min(vals)
g=C['gates']; passed=pos>=g['min_positive_loo_fraction'] and med>=g['min_median_excess_cagr_pp'] and worst>=g['min_worst_excess_cagr_pp'] and spos>=g['min_stress_positive_loo_fraction']
out={'schema':'semiconductor_raw_momentum_loo_result.v1','experiment_id':C['experiment_id'],'periods':len(periods),'smh_cagr':bc,'primary_positive_loo_fraction':pos,'stress_positive_loo_fraction':spos,'median_primary_excess_cagr_pp':med,'worst_primary_excess_cagr_pp':worst,'rows':rows,'gates':g,'passes_frozen_concentration_gate':passed,'promotion_blocked_by_static_universe':True,'research_only':True}
Path('semiconductor-raw-momentum-loo-r1-result.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
