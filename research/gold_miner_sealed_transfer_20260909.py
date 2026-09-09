import importlib.util, json, math
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
ALL=(*DEV,*HOLD,*CTX)
raw={s:src._load(s) for s in ALL}
common=set(raw[ALL[0]].timestamp)
for s in ALL[1:]: common &= set(raw[s].timestamp)
cal=pd.DatetimeIndex(sorted(common))
px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in ALL}
if any(v.isna().any() for v in px.values()): raise RuntimeError('matched calendar contains missing price rows')

def mom(x,n): return x/x.shift(n)-1

gdx=px['GDX']; gld=px['GLD']; gdxr=gdx.pct_change()
def build_panel(symbols, with_target):
    rows=[]
    for s in symbols:
        p=px[s]; r=p.pct_change(); f=pd.DataFrame(index=cal); f['i']=np.arange(len(cal))
        for n in (20,60,126): f[f'rs{n}']=mom(p,n)-mom(gdx,n)
        beta=r.rolling(126).cov(gdxr)/gdxr.rolling(126).var(); f['beta126']=beta
        resid=r-beta*gdxr; f['resid_vol20']=resid.rolling(20).std(ddof=0); f['resid_vol60']=resid.rolling(60).std(ddof=0)
        f['rel_dd60']=(p/p.rolling(60).max()-1)-(gdx/gdx.rolling(60).max()-1)
        f['rs_accel']=f['rs20']-f['rs60']
        if with_target:
            f['target']=((p.shift(-(DELAY+H))/p.shift(-DELAY)-1)-(gdx.shift(-(DELAY+H))/gdx.shift(-DELAY)-1))*10000
        f['symbol']=s; rows.append(f.reset_index(names='timestamp'))
    return pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan)

dev_panel=build_panel(DEV,True)
hold_panel=build_panel(HOLD,False)
decisions=[]; eligible_dates=0
for i in range(756,len(cal)-(H+DELAY),STEP):
    gate=(mom(gdx,126).iloc[i]>0) and ((mom(gdx,63)-mom(gld,63)).iloc[i]>0)
    if not gate: continue
    eligible_dates += 1
    train=dev_panel[(dev_panel['i'] < i-(H+DELAY)) & (dev_panel['i'] % 5 == 0)].dropna(subset=[*FEATURES,'target'])
    test=hold_panel[hold_panel['i']==i].dropna(subset=[*FEATURES])
    if len(train)<3000 or len(test)!=len(HOLD): continue
    m=Pipeline([('s',StandardScaler()),('r',Ridge(alpha=10.0))]); m.fit(train[list(FEATURES)],train['target'])
    test=test.copy(); test['pred']=m.predict(test[list(FEATURES)])
    chosen=test.nlargest(2,'pred')['symbol'].tolist(); e=i+DELAY; x=e+H
    gross=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in chosen])*10000)
    equal=float(np.mean([px[s].iloc[x]/px[s].iloc[e]-1 for s in HOLD])*10000)
    rec={'signal':cal[i].isoformat(),'entry':cal[e].isoformat(),'exit':cal[x].isoformat(),'year':int(cal[e].year),'chosen':chosen,'gross_bps':gross,'equal_hold_bps':equal}
    for b in CTX: rec[f'{b}_bps']=float((px[b].iloc[x]/px[b].iloc[e]-1)*10000)
    decisions.append(rec)

contract={'development':DEV,'sealed_holdout':HOLD,'holdouts_loaded':True,'sector_gate':'GDX_126d_return>0 AND (GDX_63d_return-GLD_63d_return)>0','model':'expanding pooled StandardScaler+Ridge(alpha=10) trained only on DEV','target':'forward20_stock_minus_GDX','features':FEATURES,'holdout_selection':'top2_of_4_by_frozen_score','costs_bps':[25,50,100],'no_parameter_tuning':True}
if len(decisions)<25:
    out={'schema':'gold_miner_sealed_transfer.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'eligible_dates':eligible_dates,'decisions':len(decisions)},'metrics':{},'checks':{'minimum_25_decisions':False},'decision':'SEALED_TRANSFER_SAMPLE_INSUFFICIENT','research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
else:
    df=pd.DataFrame(decisions); metrics={}
    for cost in (25.,50.,100.):
        net=df['gross_bps']-cost; mm={}
        for b,col in [('GDX','GDX_bps'),('GLD','GLD_bps'),('EQUAL_HOLD','equal_hold_bps'),('SPY','SPY_bps'),('QQQ','QQQ_bps')]:
            ex=net-df[col]; yrs={str(y):float(ex[df.year==y].mean()) for y in sorted(df.year.unique())}
            mm[b]={'excess_bps_per_decision':float(ex.mean()),'positive_years':sum(v>0 for v in yrs.values()),'year_count':len(yrs),'year_excess_bps':yrs}
        metrics[str(int(cost))]=mm
    p=metrics['50']; checks={'minimum_25_decisions':True,'gdx_positive':p['GDX']['excess_bps_per_decision']>0,'equal_hold_positive':p['EQUAL_HOLD']['excess_bps_per_decision']>0,'gdx_year_breadth':p['GDX']['positive_years']>=max(4,(p['GDX']['year_count']+1)//2),'cost100_gdx_positive':metrics['100']['GDX']['excess_bps_per_decision']>0}
    decision='SEALED_TICKER_TRANSFER_SUPPORTED' if all(checks.values()) else 'SEALED_TICKER_TRANSFER_NOT_SUPPORTED'
    out={'schema':'gold_miner_sealed_transfer.v1','contract':contract,'window':{'calendar_first':cal[0].isoformat(),'calendar_last':cal[-1].isoformat(),'first_entry':df.entry.min(),'last_exit':df.exit.max(),'eligible_dates':eligible_dates,'decisions':len(df)},'metrics':metrics,'checks':checks,'decision':decision,'research_only':True,'promotion_authority':False,'allocation_authority':False,'live_trading_change':False}
open('/tmp/result.json','w').write(json.dumps(out,sort_keys=True,indent=2)+'\n')
print('GOLD_MINER_SEALED_TRANSFER='+json.dumps(out,sort_keys=True))
