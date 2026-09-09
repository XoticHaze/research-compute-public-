import importlib.util, json
import numpy as np
import pandas as pd
SOURCE='/tmp/source.py'; spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
BENCH='IGV'; STOCKS=('MSFT','ORCL','ADBE','CRM','INTU','NOW','ADSK','CDNS'); LOOKBACK=20; H=20; DELAY=1; STEP=20; COSTS=(25.,50.,100.); HOLDOUT=pd.Timestamp('2022-01-03',tz='UTC')
def maxdd(rs):
    w=np.cumprod(1+np.asarray(rs,float)); curve=np.r_[1.,w]; peak=np.maximum.accumulate(curve); return float(np.min(curve/peak-1))
def cagr(rs,days):
    total=float(np.prod(1+np.asarray(rs,float))); return float(total**(365.25/max(days,1))-1) if total>0 else -1.0
syms=(*STOCKS,BENCH,'SPY','QQQ'); raw={s:src._load(s) for s in syms}; common=set(raw[syms[0]].timestamp)
for s in syms[1:]: common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in syms}; ds=[]
for i in range(LOOKBACK+252,len(cal)-(H+DELAY),STEP):
    e=i+DELAY; x=e+H
    if cal[e] < HOLDOUT: continue
    rel={s:float((px[s].iloc[i]/px[s].iloc[i-LOOKBACK]-1)-(px[BENCH].iloc[i]/px[BENCH].iloc[i-LOOKBACK]-1)) for s in STOCKS}; chosen=sorted(rel,key=rel.get)[:3]
    ds.append({'entry':cal[e],'exit':cal[x],'year':int(cal[e].year),'gross':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])),'equal':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in STOCKS])),'bench':float(px[BENCH].iloc[x]/px[BENCH].iloc[e]-1),'spy':float(px['SPY'].iloc[x]/px['SPY'].iloc[e]-1),'qqq':float(px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)})
if len(ds)<40:
    out={'schema':'software_reversal_temporal_holdout.v1','decision':'SAMPLE_INSUFFICIENT','decisions':len(ds),'research_only':True,'live_trading_change':False}; open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SOFTWARE_REVERSAL_TEMPORAL='+json.dumps(out,sort_keys=True)); raise SystemExit
df=pd.DataFrame(ds); days=int((df.exit.iloc[-1]-df.entry.iloc[0]).days); metrics={}
for cost in COSTS:
    net=df.gross-cost/10000.; mm={'strategy_cagr':cagr(net,days),'strategy_max_drawdown':maxdd(net),'capital_usage':1.0}
    for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
        cr=cagr(df[col],days); ys={str(y):float((net[df.year==y]-df.loc[df.year==y,col]).mean()*10000) for y in sorted(df.year.unique())}; mm[k]={'cagr':cr,'max_drawdown':maxdd(df[col]),'excess_cagr':mm['strategy_cagr']-cr,'mean_excess_bps_per_decision':float((net-df[col]).mean()*10000),'positive_years':sum(v>0 for v in ys.values()),'year_count':len(ys)}
    metrics[str(int(cost))]=mm
p=metrics['50']; checks={'benchmark_excess_positive':p['benchmark']['excess_cagr']>0,'equal_excess_positive':p['equal']['excess_cagr']>0,'benchmark_year_breadth':p['benchmark']['positive_years']>=max(2,(p['benchmark']['year_count']+1)//2),'cost100_benchmark_positive':metrics['100']['benchmark']['excess_cagr']>0}
out={'schema':'software_reversal_temporal_holdout.v1','contract':{'parent_signal':'prior20d stock-minus-IGV relative return; select bottom3','holdout_start':'2022-01-03','selection':'bottom3_of8','entry_delay_days':DELAY,'holding_days':H,'rebalance_step_days':STEP,'costs_bps':COSTS,'no_parameter_tuning':True},'first_entry':df.entry.iloc[0].isoformat(),'last_exit':df.exit.iloc[-1].isoformat(),'decisions':len(df),'metrics':metrics,'checks':checks,'decision':'TEMPORAL_HOLDOUT_SUPPORTED' if all(checks.values()) else 'TEMPORAL_HOLDOUT_REJECTS_PARENT','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SOFTWARE_REVERSAL_TEMPORAL='+json.dumps(out,sort_keys=True))
