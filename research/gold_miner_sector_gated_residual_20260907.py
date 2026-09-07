import importlib.util, json, sys
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SOURCE='/tmp/source.py'
spec=importlib.util.spec_from_file_location('src',SOURCE)
src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
DEV=('NEM','GOLD','AEM','WPM','FNV','KGC','AU','AGI')
HOLD=('RGLD','HMY','BTG','PAAS')
CTX=('GDX','GLD','SPY','QQQ')
H=20; DELAY=1; STEP=20
FEATURES=('rs20','rs60','rs126','beta126','resid_vol20','resid_vol60','rel_dd60','rs_accel')
raw={s:src._load(s) for s in (*DEV,*CTX)}
common=set(raw[DEV[0]].timestamp)
for s in (*DEV[1:],*CTX): common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common))
px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in (*DEV,*CTX)}
if any(v.isna().any() for v in px.values()): raise RuntimeError('matched calendar contains missing price rows')
def mom(x,n): return x/x.shift(n)-1

gdx=px['GDX']; gld=px['GLD']; gdxr=gdx.pct_change(); rows=[]
for s in DEV:
    p=px[s]; r=p.pct_change(); f=pd.DataFrame(index=cal); f['i']=np.arange(len(cal))
    for n in (20,60,126): f[f'rs{n}']=mom(p,n)-mom(gdx,n)
    beta=r.rolling(126).cov(gdxr)/gdxr.rolling(126).var(); f['beta126']=beta
    resid=r-beta*gdxr; f['resid_vol20']=resid.rolling(20).std(ddof=0); f['resid_vol60']=resid.rolling(60).std(ddof=0)
    f['rel_dd60']=(p/p.rolling(60).max()-1)-(gdx/gdx.rolling(60).max()-1)
    f['rs_accel']=f['rs20']-f['rs60']
    f['target']=((p.shift(-(DELAY+H))/p.shift(-DELAY)-1)-(gdx.shift(-(DELAY+H))/gdx.shift(-DELAY)-1))*10000
    f['symbol']=s; rows.append(f.reset_index(names='timestamp'))
panel=pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan)

decisions=[]; eligible_dates=0
for i in range(756,len(cal)-(H+DELAY),STEP):
    gate=(mom(gdx,126).iloc[i]>0) and ((mom(gdx,63)-mom(gld,63)).iloc[i]>0)
    if not gate: continue
    eligible_dates += 1
    train=panel[(panel['i'] < i-(H+DELAY)) & (panel['i'] % 5 == 0)].dropna(subset=[*FEATURES,'target'])
    test=panel[panel['i']==i].dropna(subset=[*FEATURES])
    if len(train)<3000 or len(test)!=len(DEV): continue
    m=Pipeline([('s',StandardScaler()),('r',Ridge(alpha=10.0))]); m.fit(train[list(FEATURES)],train['target'])
    test=test.copy(); test['pred']=m.predict(test[list(FEATURES)])
    chosen=test.nlargest(3,'pred')['symbol'].tolist(); e=i+DELAY; x=e+H
    gross=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])*10000)
    equal=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in DEV])*10000)
    rec={'signal':cal[i].isoformat(),'entry':cal[e].isoformat(),'exit':cal[x].isoformat(),'year':int(cal[e].year),'chosen':chosen,'gross_bps':gross,'equal_dev_bps':equal}
    for b in CTX: rec[f'{b}_bps']=float((px[b].iloc[x]/px[b].iloc[e]-1)*10000)
    decisions.append(rec)

contract={'development':DEV,'sealed_holdout':HOLD,'holdouts_loaded':False,'sector_gate':'GDX_126d_return>0 AND (GDX_63d_return-GLD_63d_return)>0','within_sector_model':'expanding pooled StandardScaler+Ridge(alpha=10)','target':'forward20_stock_minus_GDX','features':FEATURES,'selection':'top3','costs_bps':[25,50,100]}
if len(decisions)<25:
    out={'schema':'gold_miner_sector_gated_residual.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'eligible_dates':eligible_dates,'decisions':len(decisions)},'metrics':{},'checks':{'minimum_25_decisions':False},'decision':'SECTOR_GATE_SAMPLE_INSUFFICIENT','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
else:
    df=pd.DataFrame(decisions); metrics={}
    for cost in (25.,50.,100.):
        net=df['gross_bps']-cost; mm={}
        for b,col in [('GDX','GDX_bps'),('GLD','GLD_bps'),('EQUAL_DEV','equal_dev_bps'),('SPY','SPY_bps'),('QQQ','QQQ_bps')]:
            ex=net-df[col]; yrs={str(y):float(ex[df.year==y].mean()) for y in sorted(df.year.unique())}
            mm[b]={'excess_bps_per_decision':float(ex.mean()),'positive_years':sum(v>0 for v in yrs.values()),'year_count':len(yrs),'year_excess_bps':yrs}
        metrics[str(int(cost))]=mm
    p=metrics['50']; checks={'minimum_25_decisions':True,'gdx_positive':p['GDX']['excess_bps_per_decision']>0,'equal_dev_positive':p['EQUAL_DEV']['excess_bps_per_decision']>0,'gdx_year_breadth':p['GDX']['positive_years']>=max(4,(p['GDX']['year_count']+1)//2),'cost100_gdx_positive':metrics['100']['GDX']['excess_bps_per_decision']>0}
    decision='ELIGIBLE_FOR_SEALED_TRANSFER' if all(checks.values()) else 'SECTOR_GATED_RESIDUAL_NOT_SUPPORTED'
    out={'schema':'gold_miner_sector_gated_residual.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.min(),'last_exit':df.exit.max(),'eligible_dates':eligible_dates,'decisions':len(df)},'metrics':metrics,'checks':checks,'decision':decision,'research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n')
print('SECTOR_GATED_GOLD='+json.dumps(out,sort_keys=True))
