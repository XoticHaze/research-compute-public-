from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SYMS=['SPMO','IJS','CALF','SPY','IJR']; START='2017-01-01'; END='2026-09-10'; COST_BPS=25
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna()

def weighted_rebalanced(weights):
    cols=list(weights); target=np.array([weights[c] for c in cols],dtype=float); rr=r[cols].dropna(); prev=target.copy(); out=[]
    for i,(_,row) in enumerate(rr.iterrows()):
        turnover=float(np.abs(target-prev).sum()) if i>0 else 1.0
        gross=float(np.dot(target,row.values)); out.append(gross-turnover*COST_BPS/10000)
        post=target*(1+row.values); prev=post/post.sum()
    return pd.Series(out,index=rr.index)

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.,'max_drawdown':float((w/w.cummax()-1).min())}

model=weighted_rebalanced({'SPMO':1/3,'IJS':1/3,'CALF':1/3}); matched=weighted_rebalanced({'SPY':1/3,'IJR':2/3}); us=weighted_rebalanced({'SPMO':0.5,'IJS':0.5}); usmatched=weighted_rebalanced({'SPY':0.5,'IJR':0.5}); z=pd.concat({'model':model,'matched':matched,'us':us,'usmatched':usmatched},axis=1).dropna()
results={}
for name,start in {'2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
    q=z.loc[start:]; ms,bs,us,ubs=(stats(q[c]) for c in ['model','matched','us','usmatched'])
    results[name]={'calf_combo':ms,'matched_control':bs,'us_combo':us,'us_matched':ubs,'matched_excess_cagr':ms['cagr']-bs['cagr'],'us_matched_excess_cagr':us['cagr']-ubs['cagr'],'incremental_cagr_vs_us':ms['cagr']-us['cagr'],'incremental_sharpe_vs_us':ms['sharpe']-us['sharpe'],'drawdown_delta_vs_us':ms['max_drawdown']-us['max_drawdown']}
base=z.loc['2018-01-01':,['model','matched']].dropna(); folds=[stats(f.model)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(base,5)]; matched_pass=all(v['matched_excess_cagr']>0 for v in results.values()) and sum(x>0 for x in folds)>=3; utility=sum((v['incremental_cagr_vs_us']>0) or (v['incremental_sharpe_vs_us']>0 and v['drawdown_delta_vs_us']>=0) for v in results.values()); passed=matched_pass and utility>=2; decision='P322_CALF_US_COMBINATION_SUPPORTED' if passed else 'P322_CALF_US_COMBINATION_NOT_SUPPORTED'
out={'schema':'research.p322_calf_us_combination_r1','parent':'P322','claim':'Test one frozen equal-sleeve SPMO/IJS/CALF combination after P319 and P321, versus exact factor-matched 1/3 SPY + 2/3 IJR control with identical monthly rebalance and 25bp turnover friction, and compare with the simpler fixed SPMO/IJS survivor. No weight, product, factor-definition, or window search.','cost_bps':COST_BPS,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'utility_blocks':utility,'decision_rule':'Support only if matched excess CAGR is positive in all fixed windows, >=3/5 chronology folds are positive, and adding CALF improves CAGR or improves Sharpe with no drawdown worsening versus the fixed US sleeve in >=2/3 windows. Failure rejects this combination only and does not erase CALF standalone conditional evidence.','decision':decision,'limitations':['scientific combination utility, not portfolio ranking/allocation','equal weights fixed before run','CALF remains representation-conditional from P319','same adjusted-price provider','no runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p322_calf_us_combination_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))