import importlib.util, json
import numpy as np
import pandas as pd
SOURCE='/tmp/source.py'; spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
BENCH='IGV'; STOCKS=('SNPS','PANW','FTNT','VRSN','AKAM','EA','TTWO','CHKP'); LOOKBACK=20; H=20; DELAY=1; STEP=20; COSTS=(25.,50.,100.)
def maxdd(rs):
    w=np.cumprod(1+np.asarray(rs,float)); peak=np.maximum.accumulate(np.r_[1.,w]); curve=np.r_[1.,w]; return float(np.min(curve/peak-1))
def cagr(rs,days):
    total=float(np.prod(1+np.asarray(rs,float))); return float(total**(365.25/max(days,1))-1) if total>0 else -1.0
syms=(*STOCKS,BENCH,'SPY','QQQ'); raw={}
try:
    for s in syms: raw[s]=src._load(s)
except Exception as exc:
    out={'schema':'software_reversal_holdout.v1','decision':'SOURCE_BLOCKED','error':f'{type(exc).__name__}: {exc}','research_only':True,'live_trading_change':False}; open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SOFTWARE_REVERSAL_HOLDOUT='+json.dumps(out,sort_keys=True)); raise SystemExit
common=set(raw[syms[0]].timestamp)
for s in syms[1:]: common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in syms}
if len(cal)<1800 or any(v.isna().any() for v in px.values()):
    out={'schema':'software_reversal_holdout.v1','decision':'CALENDAR_INSUFFICIENT','calendar_rows':len(cal),'research_only':True,'live_trading_change':False}; open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SOFTWARE_REVERSAL_HOLDOUT='+json.dumps(out,sort_keys=True)); raise SystemExit
ds=[]
for i in range(LOOKBACK,len(cal)-(H+DELAY),STEP):
    scores={s:float(px[s].iloc[i]/px[s].iloc[i-LOOKBACK]-px[BENCH].iloc[i]/px[BENCH].iloc[i-LOOKBACK]) for s in STOCKS}
    chosen=sorted(scores,key=scores.get)[:3]; e=i+DELAY; x=e+H
    gross=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])); equal=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in STOCKS]))
    ds.append({'entry':cal[e],'exit':cal[x],'year':int(cal[e].year),'gross':gross,'equal':equal,'bench':float(px[BENCH].iloc[x]/px[BENCH].iloc[e]-1),'spy':float(px['SPY'].iloc[x]/px['SPY'].iloc[e]-1),'qqq':float(px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)})
df=pd.DataFrame(ds); days=int((df.exit.iloc[-1]-df.entry.iloc[0]).days); metrics={}
for cost in COSTS:
    net=df.gross-cost/10000.; mm={'strategy_cagr':cagr(net,days),'strategy_max_drawdown':maxdd(net),'capital_usage':1.0}
    for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
        cr=cagr(df[col],days); yearly={str(y):float((net[df.year==y]-df.loc[df.year==y,col]).mean()*10000) for y in sorted(df.year.unique())}; mm[k]={'cagr':cr,'max_drawdown':maxdd(df[col]),'excess_cagr':mm['strategy_cagr']-cr,'mean_excess_bps_per_decision':float((net-df[col]).mean()*10000),'positive_years':sum(v>0 for v in yearly.values()),'year_count':len(yearly)}
    metrics[str(int(cost))]=mm
p=metrics['50']; checks={'benchmark_excess_positive':p['benchmark']['excess_cagr']>0,'equal_excess_positive':p['equal']['excess_cagr']>0,'benchmark_year_breadth':p['benchmark']['positive_years']>=max(5,(p['benchmark']['year_count']+1)//2),'cost100_benchmark_positive':metrics['100']['benchmark']['excess_cagr']>0}
out={'schema':'software_reversal_holdout.v1','contract':{'parent_signal':'prior20d stock-minus-IGV relative return; select bottom3','holdout_names':STOCKS,'selection':'bottom3_of8','rebalance_step_days':STEP,'entry_delay_days':DELAY,'holding_days':H,'costs_bps':COSTS,'no_parameter_tuning':True},'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.iloc[0].isoformat(),'last_exit':df.exit.iloc[-1].isoformat(),'decisions':len(df),'metrics':metrics,'checks':checks,'decision':'INDEPENDENT_HOLDOUT_SUPPORTED' if all(checks.values()) else 'INDEPENDENT_HOLDOUT_REJECTS_PARENT','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SOFTWARE_REVERSAL_HOLDOUT='+json.dumps(out,sort_keys=True))
