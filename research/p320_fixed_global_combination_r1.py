from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

MODEL=['SPMO','IJS','IMTM','PIE']; MATCHED=['SPY','IJR','IEFA','EEM']; US_MODEL=['SPMO','IJS']; US_MATCHED=['SPY','IJR']
SYMS=MODEL+MATCHED; START='2015-01-01'; END='2026-09-10'; COST_BPS=25
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna()

def ew_rebalanced(cols):
    rr=r[cols].dropna(); n=len(cols); target=np.repeat(1/n,n); prev=target.copy(); out=[]
    for i,(_,row) in enumerate(rr.iterrows()):
        turnover=float(np.abs(target-prev).sum()) if i>0 else 1.0
        gross=float(np.dot(target,row.values)); net=gross-turnover*COST_BPS/10000
        out.append(net)
        post=target*(1+row.values); prev=post/post.sum()
    return pd.Series(out,index=rr.index)

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}

m=ew_rebalanced(MODEL); b=ew_rebalanced(MATCHED); u=ew_rebalanced(US_MODEL); ub=ew_rebalanced(US_MATCHED)
z=pd.concat({'model':m,'matched':b,'us_model':u,'us_matched':ub},axis=1).dropna()
results={}
for name,start in {'2016_plus':'2016-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
    q=z.loc[start:]; ms,bs,us,ubs=(stats(q[c]) for c in ['model','matched','us_model','us_matched'])
    results[name]={'global_model':ms,'matched_global_control':bs,'us_model':us,'us_matched_control':ubs,'global_matched_excess_cagr':ms['cagr']-bs['cagr'],'us_matched_excess_cagr':us['cagr']-ubs['cagr'],'incremental_cagr_vs_us_model':ms['cagr']-us['cagr'],'incremental_sharpe_vs_us_model':ms['sharpe']-us['sharpe'],'drawdown_delta_vs_us_model':ms['max_drawdown']-us['max_drawdown']}
base=z.loc['2016-01-01':,['model','matched']].dropna(); folds=[]
for f in np.array_split(base,5): folds.append(stats(f.model)['cagr']-stats(f.matched)['cagr'])
matched_pass=all(results[k]['global_matched_excess_cagr']>0 for k in results) and sum(x>0 for x in folds)>=3
utility_blocks=sum((v['incremental_cagr_vs_us_model']>0) or (v['incremental_sharpe_vs_us_model']>0 and v['drawdown_delta_vs_us_model']>=0) for v in results.values())
passed=matched_pass and utility_blocks>=2
decision='P320_FIXED_GLOBAL_COMBINATION_SUPPORTED' if passed else 'P320_FIXED_GLOBAL_COMBINATION_NOT_SUPPORTED'
out={'schema':'research.p320_fixed_global_combination_r1','parent':'P320','claim':'Test one frozen equal-sleeve combination implied by P318: monthly equal-weight SPMO/IJS/IMTM/PIE versus exact equal-weight SPY/IJR/IEFA/EEM matched controls, with identical monthly rebalancing and 25bp turnover friction. Compare against the already-supported fixed US SPMO/IJS sleeve without optimizing weights, geography, windows, or products.','model':MODEL,'matched_control':MATCHED,'cost_bps':COST_BPS,'results':results,'chronology_fold_global_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if global after-cost matched excess CAGR is positive in all fixed windows, >=3/5 chronology folds are positive, and adding the fixed global sleeves improves either CAGR or Sharpe-with-no-drawdown-worsening versus the fixed US sleeve in >=2/3 windows. Failure rejects only this frozen combination, not the underlying survivor evidence.','utility_blocks':utility_blocks,'decision':decision,'limitations':['scientific combination utility test, not portfolio ranking or allocation authority','equal weights are predeclared and not optimized','same adjusted-price provider','no product/geography/weight/window rescue','no runtime, broker, or live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p320_fixed_global_combination_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
