import json, math, statistics, urllib.request
from datetime import datetime, timezone

TICKERS=['PUTW','SPY','BIL']
START=1451606400
END=1893456000
COST_ANNUAL=0.001
GATES={'full_excess_cagr_pp':1.0,'recent_2022_excess_cagr_pp':0.5,'positive_calendar_years':6,'worst_relative_year_pp':-8.0,'rolling36_positive_fraction':0.60}

def fetch(t):
    u=f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={START}&period2={END}&interval=1d&events=div%2Csplits&includeAdjustedClose=true'
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as r: j=json.load(r)
    x=j['chart']['result'][0]; ts=x['timestamp']; adj=x['indicators']['adjclose'][0]['adjclose']
    return {datetime.fromtimestamp(a,timezone.utc).date():b for a,b in zip(ts,adj) if b is not None}

def month_end(d):
    out={}
    for k,v in sorted(d.items()): out[(k.year,k.month)]=(k,v)
    return {k:v for k,(dt,v) in out.items()}

def rets(m):
    ks=sorted(m); return {ks[i]:m[ks[i]]/m[ks[i-1]]-1 for i in range(1,len(ks))}

def cagr(rs):
    if not rs:return None
    g=math.prod(1+x for x in rs); return g**(12/len(rs))-1

def main():
    data={t:rets(month_end(fetch(t))) for t in TICKERS}
    months=sorted(set(data['PUTW'])&set(data['SPY'])&set(data['BIL']))
    rows=[]
    for i,m in enumerate(months):
        if i<36: continue
        hist=months[i-36:i]
        y=[data['PUTW'][h] for h in hist]; x=[data['SPY'][h] for h in hist]
        vx=statistics.variance(x)
        beta=(sum((a-statistics.mean(x))*(b-statistics.mean(y)) for a,b in zip(x,y))/(len(x)-1))/vx if vx>0 else 0
        beta=max(0,min(1,beta))
        ctrl=beta*data['SPY'][m]+(1-beta)*data['BIL'][m]
        putw=data['PUTW'][m]-COST_ANNUAL/12
        rows.append((m,putw,ctrl,putw-ctrl,beta))
    full=cagr([r[1] for r in rows]); ctrl=cagr([r[2] for r in rows])
    recent=[r for r in rows if r[0]>=(2022,1)]
    years=sorted(set(y for (y,_),*z in rows)); yr=[]
    for y in years:
        q=[r for r in rows if r[0][0]==y]; yr.append((y,cagr([r[1] for r in q])-cagr([r[2] for r in q])))
    roll=[]
    for i in range(35,len(rows)):
        q=rows[i-35:i+1]; roll.append(cagr([r[1] for r in q])-cagr([r[2] for r in q]))
    metrics={
      'months':len(rows),'start':str(rows[0][0]),'end':str(rows[-1][0]),
      'full_putw_cagr':full,'full_control_cagr':ctrl,'full_excess_cagr_pp':100*(full-ctrl),
      'recent_2022_excess_cagr_pp':100*(cagr([r[1] for r in recent])-cagr([r[2] for r in recent])),
      'positive_calendar_years':sum(v>0 for _,v in yr),'calendar_years':len(yr),
      'worst_relative_year_pp':100*min(v for _,v in yr),
      'rolling36_positive_fraction':sum(v>0 for v in roll)/len(roll),
      'median_beta':statistics.median(r[4] for r in rows)
    }
    passes={k:(metrics[k]>=v) for k,v in GATES.items() if k!='worst_relative_year_pp'}
    passes['worst_relative_year_pp']=metrics['worst_relative_year_pp']>=GATES['worst_relative_year_pp']
    out={'schema':'cc.market_research.putw_option_premium_beta_matched.r2','claim':'PUTW delivers durable after-cost option-premium implementation alpha beyond causal equity/cash exposure','frozen':{'cost_annual':COST_ANNUAL,'beta_window_months':36,'beta_clamp':[0,1],'control':'trailing-36m-beta * SPY + remainder BIL','gates':GATES},'metrics':metrics,'passes':passes,'decision':'PROMOTE' if all(passes.values()) else 'REJECT_NO_RESCUE','calendar_year_relative_pp':{str(y):100*v for y,v in yr}}
    open('putw-option-premium-beta-matched-r2-result.json','w').write(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
