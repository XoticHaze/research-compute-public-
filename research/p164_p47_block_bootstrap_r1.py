import json
from pathlib import Path
import numpy as np,pandas as pd
from p47_industry_fund_utility_r1 import build,metrics
SEED=47164; REPS=5000; BLOCK=6; COST=50
def boot(x):
 rng=np.random.default_rng(SEED); n=len(x); starts=np.arange(max(1,n-BLOCK+1)); out=[]
 for _ in range(REPS):
  idx=[]
  while len(idx)<n:
   s=int(rng.choice(starts)); idx.extend(range(s,min(s+BLOCK,n)))
  y=x.iloc[idx[:n]]; net=y.gross-y.turnover*COST/10000; c=metrics(net)['cagr']; out.append((c-metrics(y.equal_weight)['cagr'],c-metrics(y.spy)['cagr'],c-metrics(y.qqq)['cagr']))
 a=np.asarray(out); return {'prob_nonpositive_matched':float((a[:,0]<=0).mean()),'matched_ci95':[float(v) for v in np.quantile(a[:,0],[.025,.975])],'prob_nonpositive_spy':float((a[:,1]<=0).mean()),'spy_ci95':[float(v) for v in np.quantile(a[:,1],[.025,.975])],'prob_nonpositive_qqq':float((a[:,2]<=0).mean()),'qqq_ci95':[float(v) for v in np.quantile(a[:,2],[.025,.975])]}
def main():
 q,_,_=build(); tests={}
 for w,s in {'2015':'2015-01-01','2020':'2020-01-01'}.items():
  z=q.loc[pd.Timestamp(s):]; net=z.gross-z.turnover*COST/10000; tests[w]={'point':{'matched':metrics(net)['cagr']-metrics(z.equal_weight)['cagr'],'spy':metrics(net)['cagr']-metrics(z.spy)['cagr'],'qqq':metrics(net)['cagr']-metrics(z.qqq)['cagr']},'bootstrap':boot(z),'months':len(z)}
 a=tests['2015']['bootstrap']; b=tests['2020']['bootstrap']; dec='P47_MATCHED_ALPHA_STATISTICALLY_SUPPORTED' if a['prob_nonpositive_matched']<.10 and b['prob_nonpositive_matched']<.10 else 'P47_MATCHED_ALPHA_STATISTICALLY_FRAGILE'; o={'schema':'research.p164_p47_block_bootstrap_r1','parent':'P47','adjudicator':'P164','contract':{'selector':'frozen P47','cost_bps':COST,'block_months':BLOCK,'replications':REPS,'seed':SEED,'windows':['2015','2020'],'no_search':True},'tests':tests,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p164_p47_block_bootstrap_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()
