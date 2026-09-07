import importlib.util, json
import numpy as np
import pandas as pd
SOURCE='/tmp/source.py'
spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
DEV=('NEM','GOLD','AEM','WPM','FNV','KGC','AU','AGI'); HOLD=('RGLD','HMY','BTG','PAAS'); BASE=('GDX','GLD','SPY','QQQ')
H=20; DELAY=1; STEP=20
raw={s:src._load(s) for s in (*DEV,*BASE)}
common=set(raw[DEV[0]].timestamp)
for s in (*DEV[1:],*BASE): common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in (*DEV,*BASE)}
def mom(x,n): return x/x.shift(n)-1
gdx=px['GDX']; gld=px['GLD']; decisions=[]
for i in range(252,len(cal)-(H+DELAY),STEP):
    gate=(mom(gdx,126).iloc[i]>0) and ((mom(gdx,63)-mom(gld,63)).iloc[i]>0)
    e=i+DELAY; x=e+H
    rec={'signal':cal[i].isoformat(),'entry':cal[e].isoformat(),'exit':cal[x].isoformat(),'year':int(cal[e].year),'gate':bool(gate)}
    for b in BASE: rec[f'{b}_bps']=float((px[b].iloc[x]/px[b].iloc[e]-1)*10000)
    rec['equal_dev_bps']=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in DEV])*10000)
    decisions.append(rec)
df=pd.DataFrame(decisions); admitted=df[df.gate].copy()
if len(admitted)<30: raise RuntimeError(f'insufficient admitted sector decisions={len(admitted)}')
metrics={}
for cost in (10.,25.,50.):
    gdx_net=admitted.GDX_bps-cost; mm={}
    for name,col in [('GLD','GLD_bps'),('SPY','SPY_bps'),('QQQ','QQQ_bps'),('EQUAL_DEV','equal_dev_bps')]:
        ex=gdx_net-admitted[col]; yrs={str(y):float(ex[admitted.year==y].mean()) for y in sorted(admitted.year.unique())}
        mm[name]={'excess_bps_per_decision':float(ex.mean()),'positive_years':sum(v>0 for v in yrs.values()),'year_count':len(yrs),'year_excess_bps':yrs}
    mm['GDX_NET_BPS_PER_DECISION']=float(gdx_net.mean()); metrics[str(int(cost))]=mm
# Opportunity-value discriminator: does the gate improve GDX's own forward return vs its rejected states on the same cadence?
rejected=df[~df.gate].copy(); gate_delta={}
for cost in (10.,25.,50.):
    gate_delta[str(int(cost))]={'admitted_GDX_net_bps':float((admitted.GDX_bps-cost).mean()),'rejected_GDX_net_bps':float((rejected.GDX_bps-cost).mean()),'admitted_minus_rejected_bps':float(admitted.GDX_bps.mean()-rejected.GDX_bps.mean())}
p=metrics['25']; checks={'admitted_decisions_30plus':len(admitted)>=30,'gdx_gate_improves_own_return':gate_delta['25']['admitted_minus_rejected_bps']>0,'beats_GLD':p['GLD']['excess_bps_per_decision']>0,'beats_SPY':p['SPY']['excess_bps_per_decision']>0,'year_breadth_vs_GLD':p['GLD']['positive_years']>=max(4,(p['GLD']['year_count']+1)//2),'cost50_beats_GLD':metrics['50']['GLD']['excess_bps_per_decision']>0}
decision='GOLD_SECTOR_OPPORTUNITY_SURVIVES' if all(checks.values()) else 'GOLD_SECTOR_OPPORTUNITY_NOT_SUPPORTED'
out={'schema':'gold_miner_sector_opportunity.v1','contract':{'development':DEV,'sealed_holdout':HOLD,'holdouts_loaded':False,'sector_gate':'GDX_126d_return>0 AND (GDX_63d_return-GLD_63d_return)>0','horizon_sessions':H,'decision_step_sessions':STEP,'costs_bps':[10,25,50],'primary_cost_bps':25},'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.min(),'last_exit':df.exit.max(),'all_decisions':len(df),'admitted_decisions':len(admitted),'rejected_decisions':len(rejected)},'metrics':metrics,'gate_delta':gate_delta,'checks':checks,'decision':decision,'research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/sector-opportunity.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('GOLD_SECTOR_OPPORTUNITY='+json.dumps(out,sort_keys=True))
