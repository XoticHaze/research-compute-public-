#!/usr/bin/env python3
import hashlib, json, math, os, time
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

START='1998-01-01'; END='2026-09-08'; COSTS=(10,25,50)
MODE=os.environ['RESEARCH_MODE'].strip().upper()

def get(url, attempts=5):
    last=None
    for i in range(attempts):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 research-compute'})
            with urlopen(req,timeout=30) as r: raw=r.read()
            if len(raw)<200: raise RuntimeError(f'short_response={len(raw)}')
            return raw,i+1
        except Exception as exc:
            last=exc; time.sleep(min(2**i,8))
    raise RuntimeError(f'source_fetch_failed:{last}')

def yahoo(symbol):
    p1=int(pd.Timestamp(START,tz='UTC').timestamp()); p2=int(pd.Timestamp(END,tz='UTC').timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true'
    raw,attempt=get(url); payload=json.loads(raw)['chart']['result'][0]
    idx=pd.to_datetime(payload['timestamp'],unit='s',utc=True).tz_convert(None)
    vals=payload.get('indicators',{}).get('adjclose',[{}])[0].get('adjclose') or payload['indicators']['quote'][0]['close']
    s=pd.Series(vals,index=idx,dtype=float).dropna().sort_index()
    if len(s)<500: raise RuntimeError(f'{symbol}_insufficient_rows={len(s)}')
    return s,{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'rows':int(len(s)),'attempt':attempt,'first_observation':str(s.index.min().date()),'last_observation':str(s.index.max().date()),'source_class':'YAHOO_CHART_V8_EXTERNAL_RESEARCH_NOT_MM_CANONICAL'}

def cagr(r):
    r=pd.Series(r).dropna(); total=float((1+r).prod()); return total**(12/len(r))-1 if len(r) and total>0 else -1.0

def maxdd(r):
    eq=(1+pd.Series(r).fillna(0)).cumprod(); return float((eq/eq.cummax()-1).min())

def vol(r): return float(pd.Series(r).std(ddof=1)*math.sqrt(12))
def sharpe(r):
    r=pd.Series(r).dropna(); sd=r.std(ddof=1); return float(r.mean()/sd*math.sqrt(12)) if sd>0 else 0.0

def sortino(r):
    r=pd.Series(r).dropna(); dn=r[r<0]; sd=dn.std(ddof=1); return float(r.mean()/sd*math.sqrt(12)) if len(dn)>1 and sd>0 else 0.0

def calmar(r):
    d=abs(maxdd(r)); return float(cagr(r)/d) if d>0 else 0.0

def folds(frame,s,c):
    out=[]
    for n,idx in enumerate(np.array_split(np.arange(len(frame)),5),1):
        p=frame.iloc[idx]; a=cagr(p[s]); b=cagr(p[c]); out.append({'fold':n,'start':str(p.index.min().date()),'end':str(p.index.max().date()),'strategy_cagr':a,'control_cagr':b,'excess_cagr':a-b})
    return out

def completed_monthly(prices):
    common_last=min(s.index.max() for s in prices.values()); terminal=common_last.normalize()+pd.offsets.MonthEnd(0)
    m=pd.concat({k:v.resample('ME').last() for k,v in prices.items()},axis=1)
    if common_last.normalize()<terminal.normalize(): m=m.loc[m.index<terminal]
    return m,common_last

def metrics(r): return {'cagr':cagr(r),'max_drawdown':maxdd(r),'ann_vol':vol(r),'sharpe_rf0':sharpe(r),'sortino_rf0':sortino(r),'calmar':calmar(r)}

def p36():
    prices={}; sources={}
    for s in ['SMH','QQQ','SPY']:
        prices[s],sources[s]=yahoo(s)
    m,last=completed_monthly(prices); m=m.dropna(); rets=m.pct_change()
    sig=(m['SMH'].pct_change(6)-m['QQQ'].pct_change(6)).shift(1)
    f=pd.DataFrame({'smh':rets['SMH'],'qqq':rets['QQQ'],'spy':rets['SPY'],'signal':(sig>0).astype(float)},index=m.index).dropna()
    f['gross']=np.where(f.signal>0,f.smh,f.qqq); f['static']=0.5*f.smh+0.5*f.qqq
    switches=f.signal.diff().abs().fillna(1)
    for b in COSTS: f[f'net{b}']=f.gross-switches*(b/10000)
    break_even=None
    for b in range(0,501):
        if cagr(f.gross-switches*(b/10000)) <= cagr(f.static): break_even=b; break
    primary=metrics(f.net25); control=metrics(f.static); fold=folds(f,'net25','static')
    selected_smh=f.signal>0
    decomposition={
      'smh_selected_months':int(selected_smh.sum()),'qqq_selected_months':int((~selected_smh).sum()),
      'mean_excess_vs_static_when_smh_selected':float((f.loc[selected_smh,'net25']-f.loc[selected_smh,'static']).mean()),
      'mean_excess_vs_static_when_qqq_selected':float((f.loc[~selected_smh,'net25']-f.loc[~selected_smh,'static']).mean())}
    support=(primary['cagr']>control['cagr'] and primary['sharpe_rf0']>control['sharpe_rf0'] and primary['calmar']>control['calmar'] and cagr(f.net50)>cagr(f.static) and sum(x['excess_cagr']>0 for x in fold)>=3)
    out={'schema':'research.p36_capital_risk_attribution.v1','parent':'P36','child':'P36-C4','hypothesis':'The frozen six-month SMH-vs-QQQ relative-momentum allocator must justify its excess on capital/risk efficiency, not CAGR alone.','frozen_contract':{'signal':'prior completed 6-month SMH return minus QQQ return > 0 selects SMH next month, else QQQ','costs_bps_per_switch':list(COSTS),'risk_gate':'25bps CAGR, Sharpe_rf0 and Calmar all exceed exact static 50/50 SMH-QQQ; >=3/5 CAGR-excess folds; 50bps CAGR excess remains positive','parameter_search':False},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'sources':sources,'switches':int(switches.sum()),'break_even_switch_cost_bps_vs_static':break_even,'strategy_25bps':primary,'static_50_50_smh_qqq':control,'controls':{'SMH':metrics(f.smh),'QQQ':metrics(f.qqq),'SPY':metrics(f.spy)},'cost_cases':{str(b):{'cagr':cagr(f[f'net{b}']),'excess_vs_static':cagr(f[f'net{b}'])-cagr(f.static)} for b in COSTS},'folds_25bps':fold,'decomposition':decomposition,'decision':'CAPITAL_RISK_EFFICIENCY_SUPPORTED' if support else 'CAPITAL_RISK_EFFICIENCY_NOT_SUPPORTED','protected_boundaries':{'mm_canonical_claim':False,'strategy_spec_mutation':False,'runtime_authority_change':False,'broker_submission':False,'live_trading_change':False},'evaluation_integrity':{'common_last_daily_observation':str(last.date()),'incomplete_terminal_month_excluded':True,'matched_window_for_all_controls':True}}
    return out,'artifacts/p36_c4_capital_risk_attribution.json'

def p37():
    sectors=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; symbols=sectors+['SPY','QQQ']; prices={}; sources={}
    for s in symbols: prices[s],sources[s]=yahoo(s)
    m,last=completed_monthly(prices); m=m.dropna(); rets=m.pct_change(); mom=m[sectors].pct_change(12).shift(1)
    valid=mom.notna().all(axis=1)&rets[sectors].notna().all(axis=1)&rets[['SPY','QQQ']].notna().all(axis=1)
    idx=m.index[valid]; weights=pd.DataFrame(0.0,index=idx,columns=sectors)
    for dt in idx:
        top=mom.loc[dt].nlargest(3).index; weights.loc[dt,top]=1/3
    sr=rets.loc[idx,sectors]; gross=(weights*sr).sum(axis=1); ew=sr.mean(axis=1); spy=rets.loc[idx,'SPY']; qqq=rets.loc[idx,'QQQ']
    turnover=weights.diff().abs().sum(axis=1)/2; turnover.iloc[0]=1.0
    f=pd.DataFrame({'gross':gross,'sector_ew':ew,'spy':spy,'qqq':qqq,'turnover':turnover},index=idx)
    for b in COSTS: f[f'net{b}']=f.gross-f.turnover*(b/10000)
    fold=folds(f,'net25','sector_ew'); support=cagr(f.net25)>cagr(f.sector_ew) and sum(x['excess_cagr']>0 for x in fold)>=3 and cagr(f.net50)>cagr(f.sector_ew)
    out={'schema':'research.p37_sector_cross_sectional_momentum.v1','parent':'P37','child':'P37-C1','hypothesis':'Classic 12-month cross-sectional sector momentum: monthly equal-weight the top three of the nine long-lived SPDR sectors using only prior completed-month information.','frozen_contract':{'universe':sectors,'lookback_months':12,'top_n':3,'rebalance':'monthly_next_month','costs_bps_per_one_way_turnover':list(COSTS),'support_gate':'25bps CAGR excess_vs_exact_nine_sector_EW > 0 AND >=3/5 positive folds AND 50bps excess remains positive','parameter_search':False},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'sources':sources,'turnover_units':float(f.turnover.sum()),'strategy_25bps':metrics(f.net25),'controls':{'NINE_SECTOR_EW':metrics(f.sector_ew),'SPY':metrics(f.spy),'QQQ':metrics(f.qqq)},'cost_cases':{str(b):{'cagr':cagr(f[f'net{b}']),'excess_vs_sector_ew':cagr(f[f'net{b}'])-cagr(f.sector_ew)} for b in COSTS},'folds_25bps':fold,'decision':'SUPPORTED_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION' if support else 'NOT_SUPPORTED_ROTATE','protected_boundaries':{'mm_canonical_claim':False,'strategy_spec_mutation':False,'runtime_authority_change':False,'broker_submission':False,'live_trading_change':False},'evaluation_integrity':{'common_last_daily_observation':str(last.date()),'incomplete_terminal_month_excluded':True,'matched_window_for_all_controls':True}}
    return out,'artifacts/p37_c1_sector_momentum.json'

def main():
    out,path=p36() if MODE=='P36' else p37() if MODE=='P37' else (_ for _ in ()).throw(SystemExit(f'unsupported RESEARCH_MODE={MODE}'))
    Path(path).parent.mkdir(exist_ok=True); Path(path).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('RESEARCH_RESULT='+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
