from __future__ import annotations
import json, math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import requests

SEMANTIC_ID='VIX_CURVE_FUND_STRESS_GATE_R1'
FUNDS=['QQQ','IWM','HYG']; MARKET='SPY'; COST=0.0005; RECENT=date(2022,1,1)

def prices(sym,start=date(2011,1,1),end=date.today()):
    p1=int(datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc).timestamp()); p2=int(datetime.combine(end+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc).timestamp())
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym,safe="")}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true'
    r=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=(10,45)); r.raise_for_status(); x=r.json()['chart']['result'][0]
    a=x['indicators'].get('adjclose',[{}])[0].get('adjclose') or x['indicators']['quote'][0]['close']
    return {datetime.fromtimestamp(t,tz=timezone.utc).date():float(v) for t,v in zip(x['timestamp'],a) if v is not None}

def rets(p):
    d=sorted(p); return {b:p[b]/p[a]-1 for a,b in zip(d,d[1:]) if p[a]>0}

def cagr(xs):
    nav=1
    for _,r in xs: nav*=1+r
    y=max((xs[-1][0]-xs[0][0]).days/365.25,1/365.25); return nav**(1/y)-1

def dd(xs):
    nav=peak=1.; worst=0.
    for _,r in xs:
        nav*=1+r; peak=max(peak,nav); worst=min(worst,nav/peak-1)
    return worst

def ann(xs):
    z={}
    for d,r in xs:z.setdefault(d.year,[]).append(r)
    return {y:math.prod(1+r for r in rs)-1 for y,rs in z.items()}

def sub(xs,cut): return [(d,r) for d,r in xs if d>=cut]

def main():
    syms=FUNDS+[MARKET,'^VIX','^VIX3M']; p={s:prices(s) for s in syms}; r={s:rets(p[s]) for s in FUNDS+[MARKET]}
    days=sorted(set.intersection(*(set(r[s]) for s in FUNDS+[MARKET]),set(p['^VIX']),set(p['^VIX3M'])))
    model=[]; basket=[]; spy=[]; applied_stress=None; prior_applied_stress=None; stress_days=0
    for d in days:
        close_stress=p['^VIX'][d]>=p['^VIX3M'][d]
        if applied_stress is None:
            applied_stress=close_stress
            prior_applied_stress=applied_stress
            continue
        if applied_stress: stress_days+=1
        switch=applied_stress!=prior_applied_stress
        m=sum((0 if applied_stress else r[s][d]) for s in FUNDS)/len(FUNDS) - (COST if switch else 0)
        b=sum(r[s][d] for s in FUNDS)/len(FUNDS)
        model.append((d,m)); basket.append((d,b)); spy.append((d,r[MARKET][d]))
        prior_applied_stress=applied_stress
        applied_stress=close_stress
    my,by=ann(model),ann(basket); ys=sorted(set(my)&set(by)); yex={str(y):my[y]-by[y] for y in ys}; pos=sum(v>0 for v in yex.values())/len(yex)
    mc,bc,sc=cagr(model),cagr(basket),cagr(spy); recent=cagr(sub(model,RECENT))-cagr(sub(basket,RECENT))
    metrics={'model_cagr':mc,'matched_basket_cagr':bc,'spy_cagr':sc,'excess_cagr_vs_matched':mc-bc,'excess_cagr_vs_spy':mc-sc,'model_max_drawdown':dd(model),'matched_max_drawdown':dd(basket),'spy_max_drawdown':dd(spy),'recent_excess_vs_matched':recent,'positive_calendar_year_fraction':pos,'calendar_year_excess':yex,'stress_day_fraction':stress_days/len(model)}
    gates={'matched_excess_gte_1pct':mc-bc>=.01,'recent_excess_gte_0_5pct':recent>=.005,'positive_year_fraction_gte_60pct':pos>=.60,'drawdown_not_worse':dd(model)>=dd(basket)}
    decision='PROMOTE_FOR_INDEPENDENT_VALIDATION' if all(gates.values()) else 'REJECT_NO_PARAMETER_RESCUE'
    out={'schema':'research.vix_curve_fund_stress_gate.v1','semantic_id':SEMANTIC_ID,'claim_tested':'A structurally inverted VIX/VIX3M curve identifies stress periods strongly enough that moving a frozen QQQ/IWM/HYG basket to cash during inversion creates durable after-cost excess return.','inheritance':{'unresolved_uncertainty':'whether options-implied market stress contains fund-level timing information after corporate-event and price-only stock-selection families failed'},'frozen_spec':{'funds':FUNDS,'stress_rule':'VIX >= VIX3M observed at close, applied beginning next common trading session','portfolio':'equal-weight QQQ/IWM/HYG when prior-session curve is not inverted; cash when inverted','cost_per_state_switch_bps':5,'chronology':'strict next-session application; no same-day close lookahead','forbidden_parameter_rescue':['curve threshold','fund panel','start date','cost','recent cutoff','post-hoc year exclusions']},'metrics':metrics,'promotion_gates':gates,'decision':decision,'strongest_competing_explanation':'VIX-curve inversion is contemporaneous risk information whose avoided losses are offset by missed rebounds and switching opportunity cost.','forward_eligibility':decision.startswith('PROMOTE'),'generated_at_utc':datetime.now(timezone.utc).isoformat()}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/vix_curve_fund_stress_gate_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
