import json
import numpy as np
import pandas as pd
import yfinance as yf

START='2011-11-01'; COST=0.001
px=yf.download(['UUP','EFA','SPY'],start=START,auto_adjust=True,progress=False,group_by='ticker')
def s(t,c): return px[(t,c)].dropna()
close=pd.concat({t:s(t,'Close') for t in ['UUP','EFA','SPY']},axis=1).dropna()
daily=close.pct_change().dropna()
monthly_close=close.resample('ME').last()
monthly_ret=monthly_close.pct_change()
# Prior completed calendar-month UUP return is known at month end. Strong-dollar months (>=2%) allocate the following month to SPY; otherwise EFA.
month_sig=(monthly_ret['UUP']>=0.02).shift(1).dropna()
sig=pd.Series(month_sig.reindex(daily.index.to_period('M').to_timestamp('M')).to_numpy(),index=daily.index).fillna(False).astype(bool)
raw=np.where(sig,daily.SPY,daily.EFA)
turn=sig.astype(int).diff().abs().fillna(0)*COST
cand=pd.Series(raw,index=daily.index)-turn

def stats(r):
    if len(r)<2:return {'cagr':None,'max_drawdown':None}
    eq=(1+r).cumprod(); yrs=len(r)/252
    return {'cagr':float(eq.iloc[-1]**(1/yrs)-1),'max_drawdown':float((eq/eq.cummax()-1).min())}
def eval_slice(start,end=None):
    m=daily.index>=pd.Timestamp(start)
    if end:m &= daily.index<=pd.Timestamp(end)
    idx=daily.index[m]; part=float(sig.loc[idx].mean())
    ctrl=part*daily.loc[idx,'SPY']+(1-part)*daily.loc[idx,'EFA']
    a=stats(cand.loc[idx]); b=stats(ctrl)
    return {'days':len(idx),'spy_participation':part,'candidate':a,'matched':b,'excess_cagr_pp':100*(a['cagr']-b['cagr'])}
windows={k:eval_slice(v) for k,v in {'2012_plus':'2012-01-01','2018_plus':'2018-01-01','2022_plus':'2022-01-01'}.items()}
blocks={k:eval_slice(a,b) for k,(a,b) in {'2012_2015':('2012-01-01','2015-12-31'),'2016_2019':('2016-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}.items()}
pos=sum(x['excess_cagr_pp']>0 for x in blocks.values())
w=windows['2012_plus']; support=all(x['excess_cagr_pp']>0 for x in windows.values()) and pos>=3 and w['candidate']['max_drawdown']>=w['matched']['max_drawdown']-0.05
out={'schema':'research.uup_efa_dollar_regime_r1.v1','claim':'A strong completed-month US-dollar shock predicts next-month US equity outperformance versus developed ex-US equities beyond matched static regional exposure after costs.','mechanism':'if prior completed calendar-month UUP return >= +2%, hold SPY next month; otherwise EFA.','causal_information_time':'UUP monthly return is known only after the completed month; allocation applies to the following month.','strongest_non_alpha_explanation':'dollar strength merely tags persistent US growth/style beta or regime luck; a static SPY/EFA mixture matched to realized SPY participation explains the return.','nearest_prior_art_and_distinction':'Orthogonal to P186 equity momentum, sector dispersion, GLD absolute trend, equity gap/volume/calendar/VIX, DBC-to-XLE commodity timing, and TLT shock reversal: causal state is prior-month USD strength and target is next-month US-versus-developed-ex-US regional selection.','cost_one_way':COST,'matched_control':'static SPY/EFA mixture matched to realized SPY participation in each evaluation slice','support_rule':'positive after-cost excess in 2012+, 2018+, 2022+; >=3/4 positive chronology blocks; 2012+ drawdown no worse than matched control by >5pp','protected_boundary':'no UUP threshold/dollar proxy/regional ETF/horizon/cost/date/control/block rescue','opportunity_cost':'one A child; reject releases dollar-regime regional-selection lineage','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'UUP_EFA_DOLLAR_REGIME_SUPPORTED' if support else 'UUP_EFA_DOLLAR_REGIME_REJECTED','scientific_consequence':'Support advances only to independent replication; reject releases lineage without nearby rescue.'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))