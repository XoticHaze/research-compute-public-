from __future__ import annotations
import json
from pathlib import Path
import runpy

# R2 is a chronology/coverage correction only. R1's fixed 2010-2017 blocks are impossible
# for the full P249 common sample because the small-value ETFs do not span those blocks.
# No P524 performance result was emitted by R1. R2 reuses its frozen reconstruction and costs,
# then applies the established P505 rule: completed common sample, >=54 months, three contiguous blocks.

src=Path('research/p524_p249_primitive_persistence_r1.py')
text=src.read_text()
# Execute only the reconstruction portion before R1's metrics/decision section.
prefix=text.split("def metrics(ret,ctl,start=None,end=None):",1)[0]
ns={'__name__':'p524_r2_reconstruct'}
exec(compile(prefix,str(src),'exec'),ns)
q=ns['q']
OUT=Path('research/artifacts/p524_p249_primitive_persistence_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
import pandas as pd

n=len(q); idx=q.index
if n < 54:
    out={'schema':'research.p524_p249_primitive_persistence_r2.v1','workload_id':'P524_P249_PRIMITIVE_PERSISTENCE_R2','decision':'COMMON_SAMPLE_COVERAGE_NOT_READY','coverage':{'start':str(idx.min().date()) if n else None,'end':str(idx.max().date()) if n else None,'months':n},'minimum_months':54,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True)); raise SystemExit(0)
base=n//3; cuts=[base,2*base,n]; starts=[0,base,2*base]
blocks={f'block_{i+1}':(starts[i],cuts[i]) for i in range(3)}

def metrics(ret,ctl,lo=0,hi=None):
    z=pd.DataFrame({'ret':ret,'ctl':ctl}).dropna().iloc[lo:hi]
    ex=z.ret-z.ctl
    return {'months':int(len(z)),'start':str(z.index.min().date()),'end':str(z.index.max().date()),'annualized_mean_excess':float(ex.mean()*12),'matched_excess_hit_rate':float((ex>0).mean()),'positive_total_excess':bool((1+z.ret).prod()>(1+z.ctl).prod())}

prims={'SMALL_VALUE':('sv','svctl'),'P64':('p64','p64ctl'),'P36':('p36','p36ctl'),'P249':('p249','p249ctl')}
outp={}
for name,(rc,cc) in prims.items():
    full=metrics(q[rc],q[cc]); bs={k:metrics(q[rc],q[cc],lo,hi) for k,(lo,hi) in blocks.items()}
    outp[name]={'full':full,'blocks':bs,'positive_excess_blocks':sum(v['annualized_mean_excess']>0 for v in bs.values())}
primitive_names=['SMALL_VALUE','P64','P36']
robust=[x for x in primitive_names if outp[x]['full']['annualized_mean_excess']>0 and outp[x]['positive_excess_blocks']>=2]
fragile=[x for x in primitive_names if x not in robust]
decision='P249_MULTI_PRIMITIVE_EXCESS_PERSISTENCE_SUPPORTED' if len(robust)>=2 and outp['P249']['positive_excess_blocks']>=2 else 'P249_PRIMITIVE_PERSISTENCE_CONCENTRATED'
out={'schema':'research.p524_p249_primitive_persistence_r2.v1','workload_id':'P524_P249_PRIMITIVE_PERSISTENCE_R2','parent':'P249','claim':'The selected P249 core should derive matched excess from multiple frozen primitives across the exact common-sample chronology rather than from a single primitive.','coverage_correction':{'supersedes_failed_run_id':34556399872,'reason':'R1 predeclared calendar blocks included periods before full P249 common-sample ETF coverage and emitted no performance result; R2 uses the pre-existing P505 common-sample chronology rule without changing reconstruction, costs, products, or primitive definitions.','rule':'completed common sample >=54 months, three contiguous equal-ish chronology blocks'},'coverage':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':n,'block_sizes':[hi-lo for lo,hi in blocks.values()]},'contract':{'reconstruct':'frozen small-value, P64, P36 and equal-third P249 semantics with declared costs','primitive_robust_rule':'full-sample annualized mean matched excess >0 and positive in >=2/3 contiguous chronology blocks','core_support_rule':'at least two of three primitives robust and P249 positive in >=2/3 blocks','no_weight_product_cost_threshold_lookback_or_performance_selected_subset_search':True},'primitives':outp,'robust_primitives':robust,'fragile_primitives':fragile,'decision':decision,'scientific_consequence':'Use primitive persistence only to narrow or strengthen the scientific survivor claim. Do not remove, reweight, or allocate primitives from this diagnostic.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'coverage':out['coverage'],'robust':robust,'fragile':fragile,'primitives':{k:{'full_excess_pp':round(v['full']['annualized_mean_excess']*100,3),'positive_blocks':v['positive_excess_blocks']} for k,v in outp.items()}},sort_keys=True))