import json, math, statistics, urllib.request
from datetime import datetime, timezone

TARGET='FTLS'; BENCH='SPY'; CASH='BIL'; START=1388534400; END=1893456000
COST_ANNUAL=0.001
GATES={'full_excess_cagr_pp':1.0,'recent_2022_excess_cagr_pp':0.5,'positive_calendar_year_fraction':0.60,'worst_relative_year_pp':-8.0,'rolling36_positive_fraction':0.60}

def fetch(t):
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={START}&period2={END}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as r: j=json.load(r)
    x=j['chart']['result'][0]; ts=x['timestamp']; adj=x['indicators']['adjclose'][0]['adjclose']
    return {datetime.fromtimestamp(a,timezone.utc).date():b for a,b in zip(ts,adj) if b is not None}

def month_end(d):
    out={}
    for k,v in sorted(d.items()): out[(k.year,k.month)]=v
    return out

def rets(m):
    ks=sorted(m); return {ks[i]:m[ks[i]]/m[ks[i-1]]-1 for i in range(1,len(ks))}

def cagr(rs):
    if not rs:return None
    return math.prod(1+x for x in rs)**(12/len(rs))-1

def main():
    raw={t:fetch(t) for t in [TARGET,BENCH,CASH]}
    data={t:rets(month_end(raw[t])) for t in raw}
    months=sorted(set(data[TARGET])&set(data[BENCH])&set(data[CASH]))
    source_counts={t:len(raw[t]) for t in raw}
    if len(months)<48:
        out={'schema':'cc.market_research.ftls_longshort_alpha.r1','decision':'UNSCORED_INSUFFICIENT_HISTORY','source_counts':source_counts,'overlap_months':len(months),'gates':GATES}
        open('ftls-longshort-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2)); return
    rows=[]
    for i,m in enumerate(months):
        if i<36: continue
        hist=months[i-36:i]; x=[data[BENCH][h] for h in hist]; y=[data[TARGET][h] for h in hist]
        mx,my=statistics.mean(x),statistics.mean(y); vx=statistics.variance(x)
        beta=(sum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-1))/vx if vx>0 else 0
        beta=max(0,min(1,beta)); ctrl=beta*data[BENCH][m]+(1-beta)*data[CASH][m]
        tgt=data[TARGET][m]-COST_ANNUAL/12
        rows.append((m,tgt,ctrl,tgt-ctrl,beta))
    full_t,full_c=cagr([r[1] for r in rows]),cagr([r[2] for r in rows])
    recent=[r for r in rows if r[0]>=(2022,1)]
    years=sorted(set(r[0][0] for r in rows)); yr=[]
    for y in years:
        q=[r for r in rows if r[0][0]==y]; yr.append((y,cagr([r[1] for r in q])-cagr([r[2] for r in q])))
    roll=[]
    for i in range(35,len(rows)):
        q=rows[i-35:i+1]; roll.append(cagr([r[1] for r in q])-cagr([r[2] for r in q]))
    metrics={'months':len(rows),'full_target_cagr':full_t,'full_control_cagr':full_c,'full_excess_cagr_pp':100*(full_t-full_c),'recent_2022_excess_cagr_pp':100*(cagr([r[1] for r in recent])-cagr([r[2] for r in recent])),'positive_calendar_year_fraction':sum(v>0 for _,v in yr)/len(yr),'positive_calendar_years':sum(v>0 for _,v in yr),'calendar_years':len(yr),'worst_relative_year_pp':100*min(v for _,v in yr),'rolling36_positive_fraction':sum(v>0 for v in roll)/len(roll),'median_beta':statistics.median(r[4] for r in rows)}
    passes={k:(metrics[k]>=v) for k,v in GATES.items()}
    out={'schema':'cc.market_research.ftls_longshort_alpha.r1','claim':'FTLS delivers durable after-cost stock-selection alpha beyond causal equity/cash exposure','frozen':{'cost_annual':COST_ANNUAL,'beta_window_months':36,'control':'trailing-36m beta * SPY + remainder BIL','gates':GATES},'source_counts':source_counts,'metrics':metrics,'passes':passes,'decision':'PROMOTE' if all(passes.values()) else 'REJECT_NO_RESCUE','calendar_year_relative_pp':{str(y):100*v for y,v in yr}}
    open('ftls-longshort-alpha-r1-result.json','w').write(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
