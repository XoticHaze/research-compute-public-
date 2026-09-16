from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p498_rwj_factor_residual_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['RWJ','IJR','IWN']; HURDLE=.0025
WINDOWS={'2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}
BLOCKS={'2010_2014':('2010-01-01','2014-12-31'),'2015_2019':('2015-01-01','2019-12-31'),'2020_plus':('2020-01-01',None)}
raw=yf.download(T,start='2010-01-01',auto_adjust=True,progress=False,threads=False)
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=c[T].resample('ME').last().pct_change().dropna()
def fit(start,end=None):
 z=m.loc[m.index>=pd.Timestamp(start)].copy()
 if end:z=z.loc[z.index<=pd.Timestamp(end)]
 y=(z.RWJ-z.IJR).to_numpy(); x=(z.IWN-z.IJR).to_numpy(); X=np.column_stack([np.ones(len(x)),x]); b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
 n=len(y);k=2;s2=float(resid@resid/max(1,n-k));cov=s2*np.linalg.inv(X.T@X);se=float(np.sqrt(cov[0,0]));ann=float(b[0]*12);ann_se=float(se*np.sqrt(12));after=ann-HURDLE
 return {'months':n,'monthly_alpha':float(b[0]),'annualized_alpha':ann,'annualized_alpha_after_25bp_hurdle':after,'beta_to_iwn_minus_ijr':float(b[1]),'approx_alpha_t':float(b[0]/se) if se>0 else None,'annualized_alpha_se_approx':ann_se}
w={k:fit(v) for k,v in WINDOWS.items()};q={k:fit(a,b) for k,(a,b) in BLOCKS.items()}
wp=sum(v['annualized_alpha_after_25bp_hurdle']>0 for v in w.values());bp=sum(v['annualized_alpha_after_25bp_hurdle']>0 for v in q.values())
supported=wp==3 and bp>=2
decision='RWJ_REVENUE_FACTOR_RESIDUAL_SUPPORTED' if supported else 'RWJ_REVENUE_FACTOR_RESIDUAL_NOT_SUPPORTED'
out={'schema':'research.p498_rwj_factor_residual_r1.v1','parent':'REVENUE_WEIGHTING_FUND_FAMILY','workload_id':'P498_RWJ_FACTOR_RESIDUAL_R1','claim':'Formalized residual falsifier after P497: regress monthly RWJ-IJR excess on the conventional small-value spread IWN-IJR. The intercept is the candidate revenue-specific residual. Apply a fixed 25 bp annual hurdle and require positive residual in every fixed window plus >=2/3 fixed chronology blocks. No alternate factors, window movement, or parameter rescue.','contract':{'dependent':'RWJ monthly return - IJR monthly return','factor':'IWN monthly return - IJR monthly return','annual_residual_hurdle_bps':25,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'support_rule':'after-hurdle annualized intercept > 0 in all 3 fixed windows and >=2/3 chronology blocks'},'windows':w,'blocks':q,'summary':{'positive_fixed_windows':wp,'positive_chronology_blocks':bp},'decision':decision,'scientific_consequence':'Support only the revenue-specific residual hypothesis if the predeclared residual gate passes; otherwise retain prior matched-small-cap evidence but reject distinct revenue-factor attribution. Statistical t values are descriptive OLS diagnostics, not a separate promotion gate.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':out['summary'],'windows':{k:{'alpha_after_hurdle_pp':round(v['annualized_alpha_after_25bp_hurdle']*100,3),'beta':round(v['beta_to_iwn_minus_ijr'],3),'t':round(v['approx_alpha_t'],2)} for k,v in w.items()},'blocks':{k:round(v['annualized_alpha_after_25bp_hurdle']*100,3) for k,v in q.items()}},sort_keys=True))
