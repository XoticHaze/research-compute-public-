from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','IDMO','EFA']; COST=0.0025
x=yf.download(T,start='2017-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
# Frozen P305 economic representation and matched control.
p305=0.5*r.SPMO+0.5*r.IJS; p305_ctl=0.5*r.SPY+0.5*r.IJR
idmo=r.IDMO; idmo_ctl=r.EFA
p305_ex=p305-p305_ctl; idmo_ex=idmo-idmo_ctl
idx=p305_ex.dropna().index.intersection(idmo_ex.dropna().index)
p305_ex=p305_ex.loc[idx]; idmo_ex=idmo_ex.loc[idx]
blocks=[]
for a,b in [('2018-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01',None)]:
 aa=p305_ex.loc[a:b]; bb=idmo_ex.loc[a:b]
 corr=float(aa.corr(bb)) if len(aa)>2 else float('nan')
 blocks.append({'start':a,'end':b,'months':int(len(aa)),'residual_excess_corr':corr,'passes_abs_corr_lt_0_4':bool(abs(corr)<0.4)})
overall=float(p305_ex.corr(idmo_ex))
# Frozen 50/50 diagnostic only, not a weight search.
common=r[['SPMO','IJS','SPY','IJR','IDMO','EFA']].dropna().loc['2018-01-01':]
p=charge(0.5*(0.5*common.SPMO+0.5*common.IJS)+0.5*common.IDMO)
ctl=charge(0.5*(0.5*common.SPY+0.5*common.IJR)+0.5*common.EFA)
p305_only=charge(0.5*common.SPMO+0.5*common.IJS)
blend={'months':int(len(p)),'blend_cagr':cagr(p),'control_cagr':cagr(ctl),'matched_excess_pp':100*(cagr(p)-cagr(ctl)),'blend_sharpe':sh(p),'p305_sharpe':sh(p305_only),'blend_max_drawdown':dd(p),'p305_max_drawdown':dd(p305_only)}
pass_gate=abs(overall)<0.4 and sum(z['passes_abs_corr_lt_0_4'] for z in blocks)>=2 and blend['matched_excess_pp']>0 and (blend['blend_sharpe']>=blend['p305_sharpe'] or blend['blend_max_drawdown']>blend['p305_max_drawdown'])
out={'schema':'research.p409_p305_idmo_complementarity.v1','workload_id':'P409_P305_IDMO_COMPLEMENTARITY_R1','parent':'INTERNATIONAL_MOMENTUM','claim':'P407 IDMO contributes a sufficiently distinct residual return source relative to frozen P305 to justify complementarity evidence, without weight search or portfolio allocation authority.','p305_definition':'50% SPMO + 50% IJS; matched control 50% SPY + 50% IJR','idmo_definition':'IDMO; matched control EFA','cost_bps_each_endpoint':25,'overall_residual_excess_corr':overall,'blocks':blocks,'blend_diagnostic_50_50':blend,'decision_rule':'COMPLEMENTARITY_SUPPORTED only if |overall residual-excess corr| <0.4, >=2/3 fixed blocks have |corr|<0.4, fixed 50/50 blend has positive matched after-cost excess, and blend improves either Sharpe or max drawdown versus P305. No weights/products/windows/costs tuned after observation.','decision':'COMPLEMENTARITY_SUPPORTED' if pass_gate else 'COMPLEMENTARITY_NOT_ESTABLISHED','scientific_consequence':('P407 adds scientifically distinct return-source evidence relative to P305 under the fixed diagnostic. This does not rank or allocate capital.' if pass_gate else 'Do not claim P407 diversification against P305 from this test. Preserve P407 standalone survivor evidence and rotate rather than tune weights/products.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p409_p305_idmo_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'overall_corr':round(overall,3),'block_corrs':[round(z['residual_excess_corr'],3) for z in blocks],'blend_excess_pp':round(blend['matched_excess_pp'],3),'blend_sharpe':round(blend['blend_sharpe'],3),'p305_sharpe':round(blend['p305_sharpe'],3),'blend_dd':round(blend['blend_max_drawdown'],3),'p305_dd':round(blend['p305_max_drawdown'],3)},sort_keys=True))
