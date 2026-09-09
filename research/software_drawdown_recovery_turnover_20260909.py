import importlib.util,json
import numpy as np,pandas as pd
SOURCE='/tmp/source.py';spec=importlib.util.spec_from_file_location('src',SOURCE);src=importlib.util.module_from_spec(spec);spec.loader.exec_module(src)
B='IGV';S=('MSFT','ORCL','ADBE','CRM','INTU','NOW','ADSK','CDNS');L=252;H=20;D=1;STEP=20;C=(25.,50.,100.)
def cg(r,d):
 t=float(np.prod(1+np.asarray(r,float)));return float(t**(365.25/max(d,1))-1) if t>0 else -1.
def dd(r):
 q=np.r_[1.,np.cumprod(1+np.asarray(r,float))];return float(np.min(q/np.maximum.accumulate(q)-1))
sy=(*S,B,'SPY','QQQ');raw={s:src._load(s) for s in sy};common=set(raw[sy[0]].timestamp)
for s in sy[1:]:common&=set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common));px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in sy};rows=[];prev=set()
for i in range(L,len(cal)-(H+D),STEP):
 sc={s:float(px[s].iloc[i]/px[s].iloc[i-L:i+1].max()) for s in S};pick=set(sorted(sc,key=sc.get)[:3]);e=i+D;x=e+H;turn=1.0 if not prev else 1-len(prev&pick)/3.0
 rows.append({'entry':cal[e],'exit':cal[x],'year':int(cal[e].year),'gross':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in pick])),'turnover':turn,'equal':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in S])),'bench':float(px[B].iloc[x]/px[B].iloc[e]-1),'spy':float(px['SPY'].iloc[x]/px['SPY'].iloc[e]-1),'qqq':float(px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)});prev=pick
df=pd.DataFrame(rows);days=int((df.exit.iloc[-1]-df.entry.iloc[0]).days);m={}
for cost in C:
 net=df.gross-(cost/10000.)*df.turnover;mm={'strategy_cagr':cg(net,days),'strategy_max_drawdown':dd(net),'mean_turnover':float(df.turnover.mean()),'annualized_turnover_approx':float(df.turnover.mean()*252/STEP),'capital_usage':1.0}
 for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
  cr=cg(df[col],days);ys=[float((net[df.year==y]-df.loc[df.year==y,col]).mean()*10000) for y in sorted(df.year.unique())];mm[k]={'cagr':cr,'excess_cagr':mm['strategy_cagr']-cr,'max_drawdown':dd(df[col]),'positive_years':sum(v>0 for v in ys),'year_count':len(ys),'mean_excess_bps_per_decision':float((net-df[col]).mean()*10000)}
 m[str(int(cost))]=mm
p=m['50'];checks={'benchmark_excess_positive':p['benchmark']['excess_cagr']>0,'equal_excess_positive':p['equal']['excess_cagr']>0,'qqq_excess_positive':p['QQQ']['excess_cagr']>0,'benchmark_year_breadth':p['benchmark']['positive_years']>=max(5,(p['benchmark']['year_count']+1)//2),'cost100_benchmark_positive':m['100']['benchmark']['excess_cagr']>0,'cost100_equal_positive':m['100']['equal']['excess_cagr']>0}
out={'schema':'software_drawdown_recovery_turnover.v1','contract':{'signal':'price/trailing252d high; select lowest3 of original software8','cost_model':'one-way turnover = 1 - overlap(previous,current)/3; initial deployment=1','costs_bps':C,'entry_delay_days':D,'holding_days':H,'rebalance_step_days':STEP,'no_parameter_tuning':True},'first_entry':df.entry.iloc[0].isoformat(),'last_exit':df.exit.iloc[-1].isoformat(),'decisions':len(df),'metrics':m,'checks':checks,'decision':'TURNOVER_AWARE_SOFTWARE_DRAWDOWN_SUPPORTED' if all(checks.values()) else 'TURNOVER_AWARE_SOFTWARE_DRAWDOWN_NOT_FULLY_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False};open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n');print('SOFTWARE_DRAWDOWN_TURNOVER='+json.dumps(out,sort_keys=True))