import json,time
from collections import defaultdict
from datetime import date
from pathlib import Path
import pit_net_share_contraction_r1 as m

E='PIT_LOW_ASSET_GROWTH_R1_20260913'; FRESH=550; MINPEERS=20; RECENT='2022-01-01'

def annual_assets(cik):
    d=m.gj(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json',True)
    u=d.get('facts',{}).get('us-gaap',{}).get('Assets',{}).get('units',{}).get('USD',[])
    rows=[]
    for v in u:
        if v.get('form')!='10-K' or not all(v.get(k) is not None for k in ('filed','end','fy','val','accn')):continue
        if v['filed']<m.START or float(v['val'])<=0:continue
        try:fy=int(v['fy'])
        except:continue
        rows.append({'fy':fy,'filed':v['filed'],'end':v['end'],'assets':float(v['val']),'accn':v['accn']})
    by_filing={}
    for r in rows:
        k=(r['fy'],r['filed'],r['accn']); old=by_filing.get(k)
        if old is None or r['end']>old['end']:by_filing[k]=r
    by_fy={}
    for r in sorted(by_filing.values(),key=lambda z:(z['fy'],z['filed'],z['accn'])):by_fy.setdefault(r['fy'],r)
    return by_fy

def mean(x):return m.mean(x)
def med(x):return m.med(x)

def main():
    mp=m.gj('https://www.sec.gov/files/company_tickers.json',True)
    c={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}
    sy=sorted(set(m.T)|set(m.T.values())|{m.SPY}); P={}
    for s in sy:P[s]=m.px(s);time.sleep(.05)
    M={s:{d:(d,o,cl) for d,o,cl in P[s]} for s in sy}
    raw=[];cov=[]
    for t,sec in m.T.items():
        try:A=annual_assets(c[t])
        except Exception as z:cov.append({'ticker':t,'status':'SEC_ERROR','error':type(z).__name__});continue
        n=0
        for fy,r in sorted(A.items()):
            p=A.get(fy-1)
            if not p:continue
            growth=r['assets']/p['assets']-1
            raw.append({'ticker':t,'sector':sec,'fy':fy,'filed':r['filed'],'year':r['filed'][:4],'assets':r['assets'],'prior_assets':p['assets'],'asset_growth':growth,'accn':r['accn']});n+=1
        cov.append({'ticker':t,'status':'OK','annual_assets_facts':len(A),'growth_events':n});time.sleep(.08)
    raw.sort(key=lambda e:(e['filed'],e['ticker'],e['fy']))
    latest={}; scored=[]
    for e in raw:
        latest[e['ticker']]=e
        asof=date.fromisoformat(e['filed'])
        peers=[]
        for q in latest.values():
            age=(asof-date.fromisoformat(q['filed'])).days
            if 0<=age<=FRESH:peers.append(q)
        if len(peers)<MINPEERS:continue
        vals=sorted(q['asset_growth'] for q in peers)
        less=sum(v<e['asset_growth'] for v in vals); equal=sum(v==e['asset_growth'] for v in vals)
        pct=(less+0.5*equal)/len(vals)
        ret=m.evret(P[e['ticker']],M[e['sector']],M[m.SPY],e['filed'])
        if not ret:continue
        x=dict(e);x.update(ret);x.update({'peer_count':len(peers),'asset_growth_percentile':pct});scored.append(x)
    low=[e for e in scored if e['asset_growth_percentile']<=.25]
    high=[e for e in scored if e['asset_growth_percentile']>=.75]
    ls=[e['sector_excess'] for e in low]; hs=[e['sector_excess'] for e in high]; lsp=[e['spy_excess'] for e in low]; recent=[e['sector_excess'] for e in low if e['filed']>=RECENT]
    F=m.folds(low);ts,tw=m.conc(low,'ticker');ys,yw=m.conc(low,'year');spread=mean(ls)-mean(hs) if ls and hs else None
    g={'low_growth_events_min_60':len(low)>=60,'mean_after_cost_sector_excess_at_least_1pct':bool(ls and mean(ls)>=.01),'mean_after_cost_spy_excess_positive':bool(lsp and mean(lsp)>0),'median_after_cost_sector_excess_positive':bool(ls and med(ls)>0),'positive_sector_excess_share_at_least_53pct':bool(ls and mean([x>0 for x in ls])>=.53),'chronology_folds_at_least_3_of_5_positive':sum(x['positive'] for x in F)>=3,'recent_2022_plus_sector_excess_positive':bool(recent and mean(recent)>0),'low_beats_high_growth':bool(spread is not None and spread>0),'single_ticker_positive_contribution_share_le_25pct':ts<=.25,'single_year_positive_contribution_share_le_30pct':ys<=.30}
    R={'decision':'PIT_LOW_ASSET_GROWTH_SURVIVES_R1' if min(g.values()) else 'REJECT_NO_PARAMETER_RESCUE','all_scored_events':len(scored),'low_growth_events':len(low),'high_growth_control_events':len(high),'mean_after_cost_sector_excess':mean(ls),'median_after_cost_sector_excess':med(ls),'mean_after_cost_spy_excess':mean(lsp),'positive_sector_excess_share':mean([x>0 for x in ls]) if ls else None,'recent_since_2022_sector_excess':mean(recent),'high_growth_mean_sector_excess':mean(hs),'low_minus_high_growth_sector_excess':spread,'chronology_folds':F,'max_single_ticker_share_of_positive_excess':ts,'max_single_ticker':tw,'max_single_year_share_of_positive_excess':ys,'max_single_year':yw,'gates':g}
    out={'schema':'public_research.pit_low_asset_growth_result.v1','experiment_id':E,'inherited_learning_ids':['PIT_QUARTERLY_EARNINGS_ACCELERATION_R1_REJECT_20260912','SLP-20260913-PIT-NET-SHARE-EXPANSION-EXTERNAL-R1'],'frozen_specification':{'source':'SEC CompanyFacts us-gaap Assets','feature':'annual asset growth','peer_freshness_days':FRESH,'minimum_contemporaneous_peers':MINPEERS,'signal':'PIT asset-growth percentile <=25%','negative_control':'PIT asset-growth percentile >=75%','entry':'first trading-session open strictly after filingDate','holding_sessions':126,'round_trip_cost':.005,'ticker_to_sector':m.T,'broad_control':'SPY'},'result':R,'source_coverage':cov,'events':scored,'limitations':['fixed current liquid panel is a mechanism screen','PIT cross-section uses only latest already-filed annual growth within 550 days','failure forbids quartile/freshness/horizon/cost/ticker/sector/year/control rescue'],'boundaries':{'portfolio_allocation':False,'runtime':False,'broker':False,'live_trading':False}}
    p=Path('research/results/pit_low_asset_growth_r1.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(R,sort_keys=True))
if __name__=='__main__':main()
