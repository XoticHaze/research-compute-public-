import json
from pathlib import Path
import numpy as np,pandas as pd
from p160_fixed_p46_p47_combo_r1 import build,met
SEED=160161; REPS=5000; BLOCK=6; COST=50

def series(z):
 a=z.a-z.ta*COST/10000; b=z.b-z.tb*COST/10000
 return pd.DataFrame({'combo':.5*a+.5*b,'matched':.5*z.ma+.5*z.mb,'spy':z.spy,'qqq':z.qqq}).dropna()
def boot(x):
 rng=np.random.default_rng(SEED); n=len(x); starts=np.arange(max(1,n-BLOCK+1)); vals=[]
 for _ in range(REPS):
  idx=[]
  while len(idx)<n:
   s=int(rng.choice(starts)); idx.extend(range(s,min(s+BLOCK,n)))
  y=x.iloc[idx[:n]]; c=met(y.combo)['cagr']; vals.append((c-met(y.matched)['cagr'],c-met(y.spy)['cagr'],c-met(y.qqq)['cagr']))
 a=np.asarray(vals); return {'reps':REPS,'block_months':BLOCK,'prob_nonpositive_matched':float((a[:,0]<=0).mean()),'matched_excess_ci95':[float(x) for x in np.quantile(a[:,0],[.025,.975])],'prob_nonpositive_spy':float((a[:,1]<=0).mean()),'spy_excess_ci95':[float(x) for x in np.quantile(a[:,1],[.025,.975])],'prob_nonpositive_qqq':float((a[:,2]<=0).mean()),'qqq_excess_ci95':[float(x) for x in np.quantile(a[:,2],[.025,.975])]}
def main():
 q,_,_=build(); out={'schema':'research.p161_p160_block_bootstrap_r1','parent':'P160','adjudicator':'P161','contract':{'p160_weight':'frozen 50/50','cost_bps':COST,'block_months':BLOCK,'replications':REPS,'seed':SEED,'windows':['2015','2020'],'no_search':True},'tests':{}}
 for w,s in {'2015':'2015-01-01','2020':'2020-01-01'}.items():
  x=series(q.loc[pd.Timestamp(s):]); point={'matched':met(x.combo)['cagr']-met(x.matched)['cagr'],'spy':met(x.combo)['cagr']-met(x.spy)['cagr'],'qqq':met(x.combo)['cagr']-met(x.qqq)['cagr']}; out['tests'][w]={'point_excess':point,'bootstrap':boot(x),'months':len(x)}
 a=out['tests']['2015']['bootstrap']; b=out['tests']['2020']['bootstrap']; out['decision']='P160_MATCHED_ALPHA_STATISTICALLY_SUPPORTED' if a['prob_nonpositive_matched']<.10 and b['prob_nonpositive_matched']<.10 else 'P160_MATCHED_ALPHA_STATISTICALLY_FRAGILE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p161_p160_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
