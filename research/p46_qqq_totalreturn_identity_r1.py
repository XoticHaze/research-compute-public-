from __future__ import annotations
import json,urllib.request
from pathlib import Path

BASE='https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/'
STANDARD=BASE+'performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF'
ROLLING=BASE+'performance/rolling?idType=ticker&variationType=1M&productType=ETF'
TOL=1e-6
HORIZONS={'y3':'lineChart3YData','y5':'lineChart5YData','y10':'lineChart10YData'}

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'application/json,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=45) as r: return json.loads(r.read().decode('utf-8'))

def shareclass_end(obj,key):
    for s in obj.get(key,[]):
        if str(s.get('type','')).lower()=='shareclass':
            data=s.get('data') or []
            if data: return s.get('label'),data[0],data[-1],len(data)
    raise KeyError(key)

def main():
    standard=fetch(STANDARD); rolling=fetch(ROLLING)
    fund=next(x for x in standard['cumulativePerformance'] if x.get('displayLabel')=='Fund NAV')
    checks={}
    for sk,rk in HORIZONS.items():
        label,start,end,points=shareclass_end(rolling,rk)
        err=abs(float(fund[sk])-float(end['returnPercent']))
        checks[sk]={'standard_fund_nav_pct':fund[sk],'rolling_shareclass_pct':end['returnPercent'],'abs_error_pp':err,'tolerance_pp':TOL,'pass':err<=TOL,'label':label,'start':start,'end':end,'points':points}
    one_label,one_start,one_end,one_points=shareclass_end(rolling,'lineChart1YData')
    one_err=abs(float(fund['y1'])-float(one_end['returnPercent']))
    decision='P46_QQQ_ISSUER_TOTAL_RETURN_IDENTITY_VALIDATED' if all(v['pass'] for v in checks.values()) else 'P46_QQQ_ISSUER_TOTAL_RETURN_IDENTITY_NOT_VALIDATED'
    out={'schema':'research.p46_qqq_totalreturn_identity_r1','parent':'P46','contract':{'predeclared_horizons':['y3','y5','y10'],'tolerance_pp':TOL,'rule':'standard Fund NAV cumulative return must equal rolling growthOf10K Shareclass cumulative return at each horizon; 1y reported diagnostically but excluded because monthly chart start date need not equal standard daily lookback anchor','no_model_parameter_or_cost_changes':True},'effective_date':standard.get('effectiveDate'),'checks':checks,'diagnostic_y1':{'standard_fund_nav_pct':fund['y1'],'rolling_shareclass_pct':one_end['returnPercent'],'abs_error_pp':one_err,'start':one_start,'end':one_end,'points':one_points,'label':one_label},'decision':decision,'replay_readiness':'ADMITTED_DIRECT_ISSUER_TOTAL_RETURN_MONTHLY_SERIES' if decision.endswith('VALIDATED') else 'NOT_ADMITTED'}
    Path('results').mkdir(exist_ok=True); Path('results/p46_qqq_totalreturn_identity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
