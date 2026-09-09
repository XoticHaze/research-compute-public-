import importlib.util,json
import numpy as np,pandas as pd
SOURCE='/tmp/source.py'; spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
F={'healthcare':('XLV',('LLY','JNJ','UNH','ABBV','MRK','TMO','ABT','AMGN')),'energy':('XLE',('XOM','CVX','COP','EOG','SLB','MPC','PSX','OXY')),'software':('IGV',('MSFT','ORCL','ADBE','CRM','INTU','NOW','ADSK','CDNS')),'aerospace_defense':('ITA',('LMT','NOC','GD','RTX','LHX','HII','TDG','HEI')),'regional_banks':('KRE',('CFG','KEY','FITB','HBAN','RF','ZION','FHN','MTB'))}; L=252;H=20;D=1;STEP=20;C=(25.,50.,100.)
def dd(r): w=np.cumprod(1+np.asarray(r,float)); q=np.r_[1.,w]; return float(np.min(q/np.maximum.accumulate(q)-1))
def cg(r,d): t=float(np.prod(1+np.asarray(r,float))); return float(t**(365.25/max(d,1))-1) if t>0 else -1.
def ev(n,b,ss):
 sy=(*ss,b,'SPY','QQQ'); raw={}
 try:
  for s in sy: raw[s]=src._load(s)
 except Exception as e:return {'family':n,'decision':'SOURCE_BLOCKED','error':f'{type(e).__name__}: {e}'}
 common=set(raw[sy[0]].timestamp)
 for s in sy[1:]:common&=set(raw[s].timestamp)
 cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in sy}; rows=[]
 if len(cal)<1800:return {'family':n,'decision':'CALENDAR_INSUFFICIENT','calendar_rows':len(cal)}
 for i in range(L,len(cal)-(H+D),STEP):
  sc={s:float(px[s].iloc[i]/px[s].iloc[i-L:i+1].max()) for s in ss}; pick=sorted(sc,key=sc.get)[:3]; e=i+D;x=e+H
  rows.append({'entry':cal[e],'exit':cal[x],'year':int(cal[e].year),'gross':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in pick])),'equal':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in ss])),'bench':float(px[b].iloc[x]/px[b].iloc[e]-1),'spy':float(px['SPY'].iloc[x]/px['SPY'].iloc[e]-1),'qqq':float(px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)})
 df=pd.DataFrame(rows); days=int((df.exit.iloc[-1]-df.entry.iloc[0]).days); m={}
 for cost in C:
  net=df.gross-cost/10000.; mm={'strategy_cagr':cg(net,days),'strategy_max_drawdown':dd(net),'capital_usage':1.0}
  for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
   cr=cg(df[col],days); ys=[float((net[df.year==y]-df.loc[df.year==y,col]).mean()*10000) for y in sorted(df.year.unique())]; mm[k]={'cagr':cr,'max_drawdown':dd(df[col]),'excess_cagr':mm['strategy_cagr']-cr,'positive_years':sum(v>0 for v in ys),'year_count':len(ys),'mean_excess_bps_per_decision':float((net-df[col]).mean()*10000)}
  m[str(int(cost))]=mm
 p=m['50']; chk={'benchmark_excess_positive':p['benchmark']['excess_cagr']>0,'equal_excess_positive':p['equal']['excess_cagr']>0,'benchmark_year_breadth':p['benchmark']['positive_years']>=max(5,(p['benchmark']['year_count']+1)//2),'cost100_benchmark_positive':m['100']['benchmark']['excess_cagr']>0}
 return {'family':n,'benchmark':b,'decisions':len(df),'first_entry':df.entry.iloc[0].isoformat(),'last_exit':df.exit.iloc[-1].isoformat(),'metrics':m,'checks':chk,'decision':'SURVIVES_MATCHED_ALPHA_GATE' if all(chk.values()) else 'REJECT_OR_ROTATE_EXACT_MODEL'}
r={k:ev(k,*v) for k,v in F.items()}; surv=[k for k,v in r.items() if v.get('decision')=='SURVIVES_MATCHED_ALPHA_GATE']; out={'schema':'sector_drawdown_recovery_tournament.v1','contract':{'signal':'current adjusted price / trailing252d adjusted-price maximum; select lowest3','selection':'bottom3_of8','entry_delay_days':D,'holding_days':H,'rebalance_step_days':STEP,'costs_bps':C,'no_parameter_tuning':True},'results':r,'survivors':surv,'decision':'HAS_SURVIVOR_REQUIRES_INDEPENDENT_HOLDOUT' if surv else 'SECTOR_DRAWDOWN_RECOVERY_NOT_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False};open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n');print('SECTOR_DRAWDOWN_RECOVERY='+json.dumps(out,sort_keys=True))