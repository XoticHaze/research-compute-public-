from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['AVDV','VSS','IDMO','EFA']; COST=0.0025
x=yf.download(T,start='2019-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
val_ex=r.AVDV-r.VSS; mom_ex=r.IDMO-r.EFA
idx=val_ex.dropna().index.intersection(mom_ex.dropna().index); val_ex=val_ex.loc[idx]; mom_ex=mom_ex.loc[idx]
blocks=[]
for a,b in [('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 a1=val_ex.loc[a:b]; b1=mom_ex.loc[a:b]; corr=float(a1.corr(b1)); blocks.append({'start':a,'end':b,'months':len(a1),'residual_excess_corr':corr,'passes_abs_corr_lt_0_4':abs(corr)<0.4})
overall=float(val_ex.loc['2020-01-01':].corr(mom_ex.loc['2020-01-01':]))
q=r.loc['2020-01-01':].dropna(); blend=charge(0.5*q.AVDV+0.5*q.IDMO); ctl=charge(0.5*q.VSS+0.5*q.EFA); avdv=charge(q.AVDV); idmo=charge(q.IDMO)
diag={'months':len(q),'blend_cagr':cagr(blend),'control_cagr':cagr(ctl),'matched_excess_pp':100*(cagr(blend)-cagr(ctl)),'blend_sharpe':sh(blend),'avdv_sharpe':sh(avdv),'idmo_sharpe':sh(idmo),'blend_max_drawdown':dd(blend),'avdv_max_drawdown':dd(avdv),'idmo_max_drawdown':dd(idmo)}
passed=abs(overall)<0.4 and sum(x['passes_abs_corr_lt_0_4'] for x in blocks)>=2 and diag['matched_excess_pp']>0 and diag['blend_sharpe']>=min(diag['avdv_sharpe'],diag['idmo_sharpe'])
out={'schema':'research.p412_avdv_idmo_complementarity.v1','workload_id':'P412_AVDV_IDMO_COMPLEMENTARITY_R1','parent':'INTERNATIONAL_FACTOR_COMBINATION','claim':'The independently supported AVDV international-small-value and IDMO international-momentum sleeves provide complementary after-cost residual return sources under one frozen 50/50 diagnostic, without weight search.','controls':'AVDV-VSS residual and IDMO-EFA residual; blend control 50% VSS + 50% EFA','cost_bps_each_endpoint':25,'overall_residual_excess_corr':overall,'blocks':blocks,'blend_diagnostic_50_50':diag,'decision_rule':'COMPLEMENTARITY_SUPPORTED only if |overall residual corr|<0.4, >=2/3 fixed blocks pass |corr|<0.4, blend matched excess >0, and blend Sharpe >= weaker standalone Sharpe. No weight/product/window tuning.','decision':'COMPLEMENTARITY_SUPPORTED' if passed else 'COMPLEMENTARITY_NOT_ESTABLISHED','scientific_consequence':('International small value and momentum show complementary return-source evidence under the frozen diagnostic; this is scientific combination evidence, not allocation/ranking authority.' if passed else 'Do not claim AVDV-IDMO complementarity from this test. Preserve standalone survivor evidence and do not tune weights/products.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p412_avdv_idmo_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'overall_corr':round(overall,3),'block_corrs':[round(x['residual_excess_corr'],3) for x in blocks],'blend_excess_pp':round(diag['matched_excess_pp'],3),'blend_sharpe':round(diag['blend_sharpe'],3),'avdv_sharpe':round(diag['avdv_sharpe'],3),'idmo_sharpe':round(diag['idmo_sharpe'],3)},sort_keys=True))
