import json
import numpy as np
import pandas as pd
import yfinance as yf

START='2011-12-01'; COST=0.001
px=yf.download(['TLT','BIL'],start=START,auto_adjust=True,progress=False,group_by='ticker')
def s(t,c): return px[(t,c)].dropna()
close=pd.concat({'TLT':s('TLT','Close'),'BIL':s('BIL','Close')},axis=1).dropna()
ret=close.pct_change().dropna()
# Information is available only after the completed TLT session. A <=-2% TLT day triggers TLT for the following close-to-close session; otherwise BIL.
sig=(ret['TLT']<=-0.02).shift(1).fillna(False).reindex(ret.index,fill_value=False)
raw=np.where(sig,ret.TLT,ret.BIL)
turn=sig.astype(int).diff().abs().fillna(sig.astype(int))*COST
cand=pd.Series(raw,index=ret.index)-turn

def stats(r):
    if len(r)<2:return {'cagr':None,'max_drawdown':None}
    eq=(1+r).cumprod(); yrs=len(r)/252
    return {'cagr':float(eq.iloc[-1]**(1/yrs)-1),'max_drawdown':float((eq/eq.cummax()-1).min())}
def eval_slice(start,end=None):
    m=ret.index>=pd.Timestamp(start)
    if end:m &= ret.index<=pd.Timestamp(end)
    idx=ret.index[m]; part=float(sig.loc[idx].mean())
    # matched static beta: same realized TLT participation, rebalanced daily between TLT/BIL; no timing information.
    ctrl=part*ret.loc[idx,'TLT']+(1-part)*ret.loc[idx,'BIL']
    a=stats(cand.loc[idx]); b=stats(ctrl)
    return {'days':len(idx),'tlt_participation':part,'candidate':a,'matched':b,'excess_cagr_pp':100*(a['cagr']-b['cagr'])}
windows={k:eval_slice(v) for k,v in {'2012_plus':'2012-01-01','2018_plus':'2018-01-01','2022_plus':'2022-01-01'}.items()}
blocks={k:eval_slice(a,b) for k,(a,b) in {'2012_2015':('2012-01-01','2015-12-31'),'2016_2019':('2016-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}.items()}
pos=sum(x['excess_cagr_pp']>0 for x in blocks.values())
w=windows['2012_plus']; support=all(x['excess_cagr_pp']>0 for x in windows.values()) and pos>=3 and w['candidate']['max_drawdown']>=w['matched']['max_drawdown']-0.05
out={'schema':'research.tlt_rate_shock_reversal_r1.v1','claim':'A completed-session long-duration Treasury selloff predicts next-session bond reversal beyond matched static duration exposure after costs.','mechanism':'if prior completed TLT close-to-close return <= -2%, hold TLT next session; otherwise BIL.','causal_information_time':'TLT shock is known only after completed session close; allocation applies to following session.','strongest_non_alpha_explanation':'large TLT down days identify persistent rate repricing or volatility clustering, not reversal information; matched static TLT/BIL exposure explains any return.','nearest_prior_art_and_distinction':'Orthogonal to GLD trend, equity gap/volume/calendar/VIX, sector dispersion, commodity-to-energy timing and P186 equity momentum: causal state is a long-duration Treasury rate shock and target is next-session bond reversal.','cost_one_way':COST,'matched_control':'static TLT/BIL mixture matched to realized TLT participation in each evaluation slice','support_rule':'positive after-cost excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no shock threshold/duration ETF/horizon/cost/date/control/block rescue','opportunity_cost':'one A child; reject releases rate-shock reversal lineage','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'TLT_RATE_SHOCK_REVERSAL_SUPPORTED' if support else 'TLT_RATE_SHOCK_REVERSAL_REJECTED','scientific_consequence':'Support advances only to independent replication; reject releases lineage without nearby rescue.'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
