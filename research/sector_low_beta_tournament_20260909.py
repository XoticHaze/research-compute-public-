import importlib.util, json
import numpy as np
import pandas as pd
SOURCE='/tmp/source.py'; spec=importlib.util.spec_from_file_location('src',SOURCE); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
FAMILIES={'healthcare':('XLV',('LLY','JNJ','UNH','ABBV','MRK','TMO','ABT','AMGN')),'energy':('XLE',('XOM','CVX','COP','EOG','SLB','MPC','PSX','OXY')),'software':('IGV',('MSFT','ORCL','ADBE','CRM','INTU','NOW','ADSK','CDNS')),'aerospace_defense':('ITA',('LMT','NOC','GD','RTX','LHX','HII','TDG','HEI')),'regional_banks':('KRE',('CFG','KEY','FITB','HBAN','RF','ZION','FHN','MTB'))}
LOOKBACK=126; H=20; DELAY=1; STEP=20; COSTS=(25.,50.,100.)
def maxdd(rs):
 w=np.cumprod(1+np.asarray(rs,float)); c=np.r_[1.,w]; return float(np.min(c/np.maximum.accumulate(c)-1))
def cagr(rs,days):
 t=float(np.prod(1+np.asarray(rs,float))); return float(t**(365.25/max(days,1))-1) if t>0 else -1.0
def evaluate(name,bench,stocks):
 syms=(*stocks,bench,'SPY','QQQ'); raw={}
 try:
  for s in syms: raw[s]=src._load(s)
 except Exception as exc: return {'family':name,'decision':'SOURCE_BLOCKED','error':f'{type(exc).__name__}: {exc}'}
 common=set(raw[syms[0]].timestamp)
 for s in syms[1:]: common &= set(raw[s].timestamp)
 cal=pd.DatetimeIndex(sorted(common)); px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in syms}
 if len(cal)<1800 or any(v.isna().any() for v in px.values()): return {'family':name,'decision':'CALENDAR_INSUFFICIENT','calendar_rows':len(cal)}
 br=px[bench].pct_change(); betas={s:px[s].pct_change().rolling(LOOKBACK).cov(br)/br.rolling(LOOKBACK).var() for s in stocks}; ds=[]
 for i in range(LOOKBACK+252,len(cal)-(H+DELAY),STEP):
  scores={s:float(betas[s].iloc[i]) for s in stocks}
  if not all(np.isfinite(list(scores.values()))): continue
  chosen=sorted(scores,key=scores.get)[:3]; e=i+DELAY; x=e+H
  ds.append({'entry':cal[e],'exit':cal[x],'year':int(cal[e].year),'gross':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])),'equal':float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in stocks])),'bench':float(px[bench].iloc[x]/px[bench].iloc[e]-1),'spy':float(px['SPY'].iloc[x]/px['SPY'].iloc[e]-1),'qqq':float(px['QQQ'].iloc[x]/px['QQQ'].iloc[e]-1)})
 if len(ds)<60:return {'family':name,'decision':'SAMPLE_INSUFFICIENT','decisions':len(ds)}
 df=pd.DataFrame(ds); days=int((df.exit.iloc[-1]-df.entry.iloc[0]).days); metrics={}
 for cost in COSTS:
  net=df.gross-cost/10000.; mm={'strategy_cagr':cagr(net,days),'strategy_max_drawdown':maxdd(net),'capital_usage':1.0}
  for k,col in [('benchmark','bench'),('equal','equal'),('SPY','spy'),('QQQ','qqq')]:
   cr=cagr(df[col],days); ys={str(y):float((net[df.year==y]-df.loc[df.year==y,col]).mean()*10000) for y in sorted(df.year.unique())}; mm[k]={'cagr':cr,'max_drawdown':maxdd(df[col]),'excess_cagr':mm['strategy_cagr']-cr,'mean_excess_bps_per_decision':float((net-df[col]).mean()*10000),'positive_years':sum(v>0 for v in ys.values()),'year_count':len(ys)}
  metrics[str(int(cost))]=mm
 p=metrics['50']; checks={'benchmark_excess_positive':p['benchmark']['excess_cagr']>0,'equal_excess_positive':p['equal']['excess_cagr']>0,'benchmark_year_breadth':p['benchmark']['positive_years']>=max(5,(p['benchmark']['year_count']+1)//2),'drawdown_not_worse':p['strategy_max_drawdown']>=p['benchmark']['max_drawdown'] and p['strategy_max_drawdown']>=p['equal']['max_drawdown'],'cost100_benchmark_positive':metrics['100']['benchmark']['excess_cagr']>0}
 return {'family':name,'benchmark':bench,'stocks':stocks,'decisions':len(df),'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.iloc[0].isoformat(),'last_exit':df.exit.iloc[-1].isoformat(),'metrics':metrics,'checks':checks,'decision':'SURVIVES_MATCHED_ALPHA_AND_RISK_GATE' if all(checks.values()) else 'REJECT_OR_ROTATE_EXACT_MODEL'}
results={k:evaluate(k,*v) for k,v in FAMILIES.items()}; survivors=[k for k,v in results.items() if v.get('decision')=='SURVIVES_MATCHED_ALPHA_AND_RISK_GATE']; out={'schema':'sector_low_beta_tournament.v1','contract':{'signal':'lowest rolling126d beta to sector ETF','selection':'bottom3_of8','entry_delay_days':DELAY,'holding_days':H,'rebalance_step_days':STEP,'costs_bps':COSTS,'risk_gate':'strategy max drawdown no worse than sector ETF and equal-stock at 50bps','no_parameter_tuning':True},'results':results,'survivors':survivors,'decision':'HAS_SURVIVOR_REQUIRES_INDEPENDENT_HOLDOUT' if survivors else 'SECTOR_LOW_BETA_NOT_SUPPORTED','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}; open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n'); print('SECTOR_LOW_BETA='+json.dumps(out,sort_keys=True))
