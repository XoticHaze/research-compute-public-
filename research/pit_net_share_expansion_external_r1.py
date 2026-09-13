import json
from pathlib import Path
import pit_net_share_contraction_r1 as m

EXPERIMENT_ID='PIT_NET_SHARE_EXPANSION_EXTERNAL_R1_20260913'
OUT=Path('research/results/pit_net_share_expansion_external_r1.json')
T={'ORCL':'XLK','CRM':'XLK','ADBE':'XLK','CSCO':'XLK','MU':'SMH','QCOM':'SMH','TXN':'SMH','KLAC':'SMH','MS':'XLF','C':'XLF','WFC':'XLF','BLK':'XLF','EOG':'XLE','SLB':'XLE','OXY':'XLE','DE':'XLI','UPS':'XLI','RTX':'XLI','PFE':'XLV','ABBV':'XLV','MRK':'XLV','WMT':'XLP','COST':'XLP','MDLZ':'XLP','LOW':'XLY','SBUX':'XLY','TJX':'XLY','DIS':'XLC','T':'XLC','VZ':'XLC','SO':'XLU','AEP':'XLU','NUE':'XLB','SHW':'XLB','EQIX':'XLRE','O':'XLRE'}

def main():
    m.E=EXPERIMENT_ID
    m.T=T
    m.main()
    p=Path('research/results/pit_net_share_contraction_r1.json')
    base=json.loads(p.read_text())
    events=base['events']
    expansion=[e for e in events if e['share_change']>=0.02]
    neutral=[e for e in events if -0.02<e['share_change']<0.02]
    contraction=[e for e in events if e['share_change']<=-0.02]
    es=[e['sector_excess'] for e in expansion]
    esp=[e['spy_excess'] for e in expansion]
    ns=[e['sector_excess'] for e in neutral]
    cs=[e['sector_excess'] for e in contraction]
    recent=[e['sector_excess'] for e in expansion if e['filed']>=m.RECENT]
    F=m.folds(expansion)
    ts,tw=m.conc(expansion,'ticker');ys,yw=m.conc(expansion,'year')
    en=m.mean(es)-m.mean(ns) if es and ns else None
    ec=m.mean(es)-m.mean(cs) if es and cs else None
    g={
      'expansion_events_min_35':len(expansion)>=35,
      'mean_after_cost_sector_excess_at_least_3pct':bool(es and m.mean(es)>=0.03),
      'mean_after_cost_spy_excess_positive':bool(esp and m.mean(esp)>0),
      'median_after_cost_sector_excess_positive':bool(es and m.med(es)>0),
      'positive_sector_excess_share_at_least_53pct':bool(es and m.mean([x>0 for x in es])>=0.53),
      'chronology_folds_at_least_3_of_5_positive':sum(x['positive'] for x in F)>=3,
      'recent_2022_plus_sector_excess_positive':bool(recent and m.mean(recent)>0),
      'expansion_beats_neutral':bool(en is not None and en>0),
      'expansion_beats_contraction':bool(ec is not None and ec>0),
      'single_ticker_positive_contribution_share_le_25pct':ts<=0.25,
      'single_year_positive_contribution_share_le_30pct':ys<=0.30,
    }
    R={
      'decision':'PIT_NET_SHARE_EXPANSION_EXTERNAL_SURVIVES_R1' if min(g.values()) else 'REJECT_NO_PARAMETER_RESCUE',
      'all_scored_events':len(events),'expansion_events':len(expansion),'neutral_control_events':len(neutral),'contraction_control_events':len(contraction),
      'mean_after_cost_sector_excess':m.mean(es),'median_after_cost_sector_excess':m.med(es),'mean_after_cost_spy_excess':m.mean(esp),
      'positive_sector_excess_share':m.mean([x>0 for x in es]) if es else None,'recent_since_2022_sector_excess':m.mean(recent),
      'neutral_mean_sector_excess':m.mean(ns),'contraction_mean_sector_excess':m.mean(cs),'expansion_minus_neutral_sector_excess':en,'expansion_minus_contraction_sector_excess':ec,
      'chronology_folds':F,'max_single_ticker_share_of_positive_excess':ts,'max_single_ticker':tw,'max_single_year_share_of_positive_excess':ys,'max_single_year':yw,'gates':g
    }
    out={'schema':'public_research.pit_net_share_expansion_external_result.v1','experiment_id':EXPERIMENT_ID,'inherited_learning_ids':['SLP-20260913-PIT-NET-SHARE-CONTRACTION-R1'],'frozen_specification':{'signal':'annual share change >= +2%','neutral_control':'-2% < annual share change < +2%','contraction_control':'annual share change <= -2%','entry':'first trading-session open strictly after filingDate','holding_sessions':126,'round_trip_cost':0.005,'ticker_to_sector':T,'broad_control':'SPY','disjoint_from_discovery_panel':True},'result':R,'source_coverage':base['source_coverage'],'events':events,'limitations':['fixed disjoint current liquid panel is a mechanism transport screen','failure forbids threshold/horizon/cost/ticker/sector/year/control rescue'],'boundaries':{'portfolio_allocation':False,'runtime':False,'broker':False,'live_trading':False}}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(R,sort_keys=True))

if __name__=='__main__':main()
