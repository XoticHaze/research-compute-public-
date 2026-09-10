from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['HEFA','IEFA','DBEF','EFA','UUP']; START='2013-01-01'; END='2026-09-11'; EP=.0025
OUT=Path('research/artifacts/p436_currency_hedge_regime_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=c[T].resample('ME').last().dropna(how='all')
r=m.pct_change(fill_method=None)
# Dollar state is fully causal: prior completed 12-month UUP return, shifted one month before the evaluated month.
uup12=m.UUP.pct_change(12).shift(1)
q=pd.DataFrame({'hefa_spread':r.HEFA-r.IEFA,'dbef_spread':r.DBEF-r.EFA,'uup12':uup12}).dropna()
q=q.loc['2015-01-31':'2026-08-31']
q['state']=np.where(q.uup12>0,'strong_dollar','weak_dollar')

def stats(x):
    a=np.asarray(x,dtype=float)
    return {'months':int(len(a)),'annualized_mean_pp':float(1200*np.mean(a)),'positive_month_fraction':float(np.mean(a>0)),'monthly_median_pp':float(100*np.median(a))}
state={}
for s,g in q.groupby('state'):
    state[s]={'HEFA_minus_IEFA':stats(g.hefa_spread),'DBEF_minus_EFA':stats(g.dbef_spread),'implementation_mean':stats(.5*(g.hefa_spread+g.dbef_spread))}
need={'strong_dollar','weak_dollar'}
coverage=need.issubset(state) and all(state[s]['implementation_mean']['months']>=24 for s in need)
structural=coverage and all(state[s]['HEFA_minus_IEFA']['annualized_mean_pp']>0 and state[s]['DBEF_minus_EFA']['annualized_mean_pp']>0 for s in need)
if structural: decision='CURRENCY_HEDGE_EDGE_CROSSES_DOLLAR_REGIMES'
elif coverage: decision='CURRENCY_HEDGE_EDGE_REGIME_CONDITIONAL'
else: decision='CURRENCY_HEDGE_REGIME_COVERAGE_NOT_READY'
out={'schema':'research.p436_currency_hedge_regime_r1.v1','workload_id':'P436_CURRENCY_HEDGE_REGIME_R1','parent':'DEVELOPED_EXUS_CURRENCY_HEDGE','claim':'The independently replicated developed-ex-US currency-hedge edge should be tested in prospectively defined strong- versus weak-dollar months using only the prior completed 12-month UUP return; structural support requires both HEFA-IEFA and DBEF-EFA to remain positive in both states with at least 24 months per state.','sample':{'start':str(q.index.min().date()),'end':str(q.index.max().date()),'months':int(len(q))},'state_rule':'strong_dollar iff prior completed 12-month UUP return > 0; otherwise weak_dollar','friction_bps_each_endpoint_context':25,'states':state,'decision_rule':'CROSS_REGIMES only if both implementations have positive annualized mean hedge spread in both states and each state has >=24 months; otherwise REGIME_CONDITIONAL when coverage is sufficient. No state threshold/lookback/product/date rescue.','decision':decision,'scientific_consequence':('Treat currency hedging as a more structural developed-ex-US mechanism if CROSS_REGIMES.' if structural else 'Preserve P426/P428 survivor evidence but treat hedge benefit as context-dependent if REGIME_CONDITIONAL; do not kill on this one orthogonal stress.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'sample_months':len(q),'states':{s:{k:round(v['annualized_mean_pp'],3) for k,v in d.items()}|{'months':d['implementation_mean']['months']} for s,d in state.items()}},sort_keys=True))
