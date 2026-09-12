import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

C = json.loads(Path('research/semiconductor-stock-specific-residual-r1.json').read_text())
START = dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
SYMS = C['universe'] + [C['benchmark_symbol'], C['broad_market_symbol']]


def fetch(sym):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(START.timestamp())}'
           f'&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true')
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        o = json.load(r)['chart']['result'][0]
    a = o['indicators'].get('adjclose',[{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat():float(p) for t,p in zip(o['timestamp'],a) if p is not None}


def beta(xs, ys):
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    den=sum((x-mx)**2 for x in xs)
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den>1e-18 else 1.0


def maxdd(rs):
    eq=peak=1.0; worst=0.0
    for r in rs:
        eq*=1+r; peak=max(peak,eq); worst=min(worst,eq/peak-1)
    return worst


def cagr(rs, years):
    eq=1.0
    for r in rs: eq*=1+r
    return eq**(1/years)-1 if eq>0 else -1.0

px={s:fetch(s) for s in SYMS}
dates=sorted(set.intersection(*(set(px[s]) for s in SYMS)))
L=C['lookback_sessions']
month_last=[]
for i,d in enumerate(dates):
    if i+1<len(dates) and dates[i+1][:7]!=d[:7]: month_last.append(i)
periods=[]
for pos in month_last:
    if pos<L or pos+1>=len(dates): continue
    exit_pos=next((j for j in month_last if j>pos),None)
    if exit_pos is None or exit_pos+1>=len(dates): continue
    signal=dates[pos]; entry=dates[pos+1]; exitd=dates[exit_pos+1]
    smh_daily=[]
    for k in range(pos-L+1,pos+1): smh_daily.append(math.log(px[C['benchmark_symbol']][dates[k]]/px[C['benchmark_symbol']][dates[k-1]]))
    smh_cum=math.log(px[C['benchmark_symbol']][signal]/px[C['benchmark_symbol']][dates[pos-L]])
    scores=[]
    for s in C['universe']:
        sd=[math.log(px[s][dates[k]]/px[s][dates[k-1]]) for k in range(pos-L+1,pos+1)]
        b=beta(smh_daily,sd)
        raw=math.log(px[s][signal]/px[s][dates[pos-L]])
        scores.append((s,raw-b*smh_cum,raw,b))
    resid_sel=[x[0] for x in sorted(scores,key=lambda z:z[1],reverse=True)[:C['top_n']]]
    raw_sel=[x[0] for x in sorted(scores,key=lambda z:z[2],reverse=True)[:C['top_n']]]
    def basket(sel): return sum(px[s][exitd]/px[s][entry]-1 for s in sel)/len(sel)
    periods.append({'signal':signal,'entry':entry,'exit':exitd,'year':int(entry[:4]),'resid_sel':resid_sel,'raw_sel':raw_sel,
                    'resid_gross':basket(resid_sel),'raw_gross':basket(raw_sel),
                    'ew_gross':basket(C['universe']),
                    'smh':px[C['benchmark_symbol']][exitd]/px[C['benchmark_symbol']][entry]-1,
                    'qqq':px[C['broad_market_symbol']][exitd]/px[C['broad_market_symbol']][entry]-1})

def apply_cost(kind,bps):
    prev=set(); out=[]
    for p in periods:
        sel=set(p[kind+'_sel']); turnover=len(sel.symmetric_difference(prev))/(2*C['top_n']) if prev else 1.0
        out.append(p[kind+'_gross']-bps/10000*turnover)
        prev=sel
    return out

years=(dt.date.fromisoformat(periods[-1]['exit'])-dt.date.fromisoformat(periods[0]['entry'])).days/365.25
smh=[p['smh'] for p in periods]; qqq=[p['qqq'] for p in periods]; ew=[p['ew_gross'] for p in periods]
results={}
for bps in C['cost_scenarios_bps_per_turnover']:
    rr=apply_cost('resid',bps); raw=apply_cost('raw',bps)
    results[str(bps)]={'residual_cagr':cagr(rr,years),'raw_cagr':cagr(raw,years),'smh_cagr':cagr(smh,years),'qqq_cagr':cagr(qqq,years),'equal_weight_cagr':cagr(ew,years),
                       'residual_minus_raw_cagr_pp':(cagr(rr,years)-cagr(raw,years))*100,
                       'residual_minus_smh_cagr_pp':(cagr(rr,years)-cagr(smh,years))*100,
                       'residual_max_drawdown':maxdd(rr),'raw_max_drawdown':maxdd(raw)}
primary=results[str(C['primary_cost_bps_per_turnover'])]
yr=[]
for y in sorted(set(p['year'] for p in periods)):
    idx=[i for i,p in enumerate(periods) if p['year']==y]
    if len(idx)<10: continue
    rr=apply_cost('resid',C['primary_cost_bps_per_turnover'])
    a=1.0; b=1.0
    for i in idx: a*=1+rr[i]; b*=1+smh[i]
    yr.append({'year':y,'residual_return':a-1,'smh_return':b-1,'excess':a-b,'positive':a>b})
posfrac=sum(x['positive'] for x in yr)/len(yr)
g=C['gates']
passed=(primary['residual_minus_raw_cagr_pp']>=g['min_residual_minus_raw_cagr_pp'] and primary['residual_minus_smh_cagr_pp']>=g['min_residual_minus_smh_cagr_pp'] and posfrac>=g['min_positive_smh_excess_year_fraction'] and results['50']['residual_minus_smh_cagr_pp']>=g['min_50bps_residual_minus_smh_cagr_pp'] and (primary['residual_max_drawdown']-primary['raw_max_drawdown'])*100>=-g['max_drawdown_worsening_vs_raw_pp'])
out={'schema':'semiconductor_stock_specific_residual_result.v1','experiment_id':C['experiment_id'],'periods':len(periods),'first_entry':periods[0]['entry'],'last_exit':periods[-1]['exit'],'years':years,'cost_results':results,'positive_smh_excess_year_fraction':posfrac,'calendar_years':yr,'gates':g,'passes_frozen_economic_gate':passed,'promotion_blocked_by_static_universe':True,'research_only':True}
Path('semiconductor-stock-specific-residual-r1-result.json').write_text(json.dumps(out,sort_keys=True,indent=2))
print(json.dumps(out,sort_keys=True))
