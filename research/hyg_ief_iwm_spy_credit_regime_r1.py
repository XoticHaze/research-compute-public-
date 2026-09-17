"""Frozen A discriminator: credit-risk strength -> small-cap selection.
Question: does prior completed-month HYG minus IEF return >= +2pp predict IWM over SPY next month?
Non-alpha explanation: unconditional small-cap beta / risk-on regime coincidence.
Nearest protected distinctions: not UUP regional selection, GLD trend, DBC energy, TLT reversal, sector dispersion, or SPY event reversal.
No threshold/proxy/asset/horizon/cost/date/control/block rescue after terminal result.
"""
import json
import numpy as np
import pandas as pd
import yfinance as yf

START='2011-01-01'; END='2026-09-16'; COST=.001
TICKERS=['HYG','IEF','IWM','SPY']
px=yf.download(TICKERS,start=START,end='2026-09-17',auto_adjust=True,progress=False)['Close'].dropna()
m=px.resample('ME').last(); r=m.pct_change()
# causal information time: only prior completed calendar month
credit=(r.HYG-r.IEF).shift(1)
sig=(credit>=.02).astype(float)
gross=sig*r.IWM+(1-sig)*r.SPY
turn=sig.diff().abs().fillna(sig.iloc[0]); net=gross-turn*COST

def stats(ret):
    ret=ret.dropna(); yrs=len(ret)/12; eq=(1+ret).cumprod()
    return {'cagr':float(eq.iloc[-1]**(1/yrs)-1),'max_drawdown':float((eq/eq.cummax()-1).min()),'months':int(len(ret))}
def evaluate(a,b):
    rr=net.loc[a:b]; ss=sig.loc[a:b]; raw=r.loc[a:b]; p=float(ss.mean())
    matched=p*raw.IWM+(1-p)*raw.SPY
    cs,ms=stats(rr),stats(matched)
    return {'candidate':cs,'matched':ms,'iwm_participation':p,'excess_cagr_pp':100*(cs['cagr']-ms['cagr'])}
windows={'2012_plus':evaluate('2012-01-01',END),'2018_plus':evaluate('2018-01-01',END),'2022_plus':evaluate('2022-01-01',END)}
blocks={'2012_2015':evaluate('2012-01-01','2015-12-31'),'2016_2019':evaluate('2016-01-01','2019-12-31'),'2020_2022':evaluate('2020-01-01','2022-12-31'),'2023_plus':evaluate('2023-01-01',END)}
pos=sum(v['excess_cagr_pp']>0 for v in blocks.values()); w=windows['2012_plus']
support=all(v['excess_cagr_pp']>0 for v in windows.values()) and pos>=3 and w['candidate']['max_drawdown']>=w['matched']['max_drawdown']-.05
out={'schema':'research.hyg_ief_iwm_spy_credit_regime_r1.v1','question':'prior completed-month HYG minus IEF return >= +2pp predicts IWM over SPY next month','causal_information_time':'prior completed calendar month only','cost_one_way':COST,'matched_control':'static IWM/SPY mixture matched to realized IWM participation','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'HYG_IEF_IWM_SPY_CREDIT_REGIME_SUPPORTED' if support else 'HYG_IEF_IWM_SPY_CREDIT_REGIME_REJECTED','protected_boundary':'no threshold/HYG/IEF/IWM/SPY/horizon/cost/date/control/block rescue'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))
