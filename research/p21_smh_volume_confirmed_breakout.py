#!/usr/bin/env python3
import hashlib, json, math, os, statistics, time, urllib.request
from datetime import datetime, timezone

SYMS=("SMH","QQQ","SPY")
LOOKBACK_VOL=20
HISTORY=756
BREAKOUT=63
HOLD=20
VOLUME_LOOKBACK=20
COSTS=(10.0,25.0,50.0)
OUT=os.environ.get("P21_C2_OUTPUT","p21_smh_volume_confirmed_breakout_receipt.json")
UA="Mozilla/5.0 research-compute-public p21-c2"

def fetch(sym):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=946684800&period2=1788825600&interval=1d&events=history&includeAdjustedClose=true"
    last=None
    for k in range(5):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA})
            with urllib.request.urlopen(req,timeout=30) as r: raw=r.read()
            obj=json.loads(raw)["chart"]["result"][0]
            ts=obj["timestamp"]
            quote=obj["indicators"]["quote"][0]
            adj=(obj.get("indicators",{}).get("adjclose") or [{}])[0].get("adjclose")
            if not adj: adj=quote["close"]
            vols=quote.get("volume") or [None]*len(ts)
            prices={}
            volumes={}
            for t,p,v in zip(ts,adj,vols):
                if p is None or p<=0: continue
                d=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
                prices[d]=float(p)
                if v is not None and v>=0: volumes[d]=float(v)
            return prices,volumes,{"url":url,"rows":len(prices),"payload_sha256":hashlib.sha256(raw).hexdigest()}
        except Exception as e:
            last=e; time.sleep(2**k)
    raise RuntimeError(f"fetch failed {sym}: {last}")

def pctile(xs,p):
    ys=sorted(xs)
    if not ys:return None
    x=(len(ys)-1)*p; a=int(math.floor(x)); b=int(math.ceil(x))
    return ys[a] if a==b else ys[a]+(ys[b]-ys[a])*(x-a)

def mean(xs): return sum(xs)/len(xs) if xs else None

def fold_split(xs,n=5):
    return [xs[len(xs)*k//n:len(xs)*(k+1)//n] for k in range(n)]

def main():
    data={}; volumes={}; prov={}
    for s in SYMS: data[s],volumes[s],prov[s]=fetch(s)
    dates=sorted(set.intersection(*(set(data[s]) for s in SYMS)))
    px={s:[data[s][d] for d in dates] for s in SYMS}
    smh_vol=[volumes["SMH"].get(d) for d in dates]
    lret=[None]+[math.log(px["SMH"][i]/px["SMH"][i-1]) for i in range(1,len(dates))]
    rvol=[None]*len(dates)
    for i in range(LOOKBACK_VOL,len(dates)):
        w=[x for x in lret[i-LOOKBACK_VOL+1:i+1] if x is not None]
        if len(w)==LOOKBACK_VOL: rvol[i]=statistics.pstdev(w)*math.sqrt(252)

    # Reproduce C1's frozen, non-overlapping event sequence first. C2 only filters this
    # exact event set, so volume confirmation cannot alter C1 event spacing or thresholds.
    c1=[]; next_ok=0
    start=max(HISTORY+LOOKBACK_VOL,BREAKOUT,VOLUME_LOOKBACK)
    for i in range(start,len(dates)-HOLD):
        hist=[v for v in rvol[i-HISTORY:i] if v is not None]
        if len(hist)<HISTORY-5 or i<next_ok: continue
        thr=pctile(hist,0.20)
        if rvol[i] is not None and rvol[i] <= thr and px["SMH"][i] > max(px["SMH"][i-BREAKOUT:i]):
            prior_vol=[v for v in smh_vol[i-VOLUME_LOOKBACK:i] if v is not None]
            if smh_vol[i] is None or len(prior_vol)!=VOLUME_LOOKBACK: continue
            ev={"date":dates[i],"realized_vol":rvol[i],"vol_threshold":thr,
                "event_volume":smh_vol[i],"prior20_volume_median":statistics.median(prior_vol),
                "volume_confirmed":smh_vol[i] > statistics.median(prior_vol)}
            for s in SYMS: ev[s]=px[s][i+HOLD]/px[s][i]-1.0
            c1.append(ev); next_ok=i+HOLD
    if not c1: raise RuntimeError("no frozen C1 events")
    events=[e for e in c1 if e["volume_confirmed"]]
    if not events: raise RuntimeError("no volume-confirmed C2 events")

    first_i=dates.index(c1[0]["date"]); last_i=dates.index(c1[-1]["date"])
    unconditional=[px["SMH"][i+HOLD]/px["SMH"][i]-1.0 for i in range(first_i,last_i+1-HOLD)]
    costs={}; c1_costs={}
    for c in COSTS:
        rt=2*c/10000.0
        def metrics(es):
            net=[e["SMH"]-rt for e in es]
            qex=[(e["SMH"]-rt)-e["QQQ"] for e in es]
            sex=[(e["SMH"]-rt)-e["SPY"] for e in es]
            qfold=[mean([(e["SMH"]-rt)-e["QQQ"] for e in f]) for f in fold_split(es) if f]
            return {"smh_net_mean":mean(net),"smh_net_median":statistics.median(net),"smh_net_win_rate":mean([x>0 for x in net]),
                    "excess_vs_qqq_mean":mean(qex),"excess_vs_spy_mean":mean(sex),
                    "positive_qqq_excess_folds":sum(x>0 for x in qfold),"fold_count":len(qfold)}
        c1m=metrics(c1); c2m=metrics(events)
        c2m["incremental_smh_net_mean_vs_c1"] = c2m["smh_net_mean"]-c1m["smh_net_mean"]
        c2m["incremental_qqq_excess_mean_vs_c1"] = c2m["excess_vs_qqq_mean"]-c1m["excess_vs_qqq_mean"]
        c1_costs[str(c)]=c1m; costs[str(c)]=c2m

    by_year={}
    for e in events: by_year.setdefault(e["date"][:4],[]).append(e)
    year_q=[mean([(e["SMH"]-0.005)-e["QQQ"] for e in es]) for _,es in sorted(by_year.items())]
    primary=costs["25.0"]
    supported=(len(events)>=20 and primary["excess_vs_qqq_mean"]>0 and primary["excess_vs_spy_mean"]>0
               and primary["incremental_qqq_excess_mean_vs_c1"]>0 and primary["positive_qqq_excess_folds"]>=3
               and mean([x>0 for x in year_q])>=0.5 and costs["50.0"]["excess_vs_qqq_mean"]>0)
    decision="P21_VOLUME_CONFIRMED_BREAKOUT_SUPPORTED" if supported else "P21_VOLUME_CONFIRMED_BREAKOUT_NOT_SUPPORTED"
    receipt={
      "schema":"research.p21_smh_volume_confirmed_breakout.v1","parent_id":"P21","child_id":"P21-C2","decision":decision,
      "hypothesis":{"base_event_contract":"UNCHANGED_P21_C1_20D_REALIZED_VOL_BELOW_PRIOR_756D_P20_AND_63D_BREAKOUT_WITH_20D_NONOVERLAP_HOLD",
                    "independent_information":"SMH_EVENT_DAY_VOLUME","volume_confirmation":"event_day_volume_gt_prior_only_20_session_median",
                    "volume_lookback_sessions":VOLUME_LOOKBACK,"cost_bps_per_side":list(COSTS)},
      "source":{"provider":"Yahoo Finance Chart JSON","transport":"query1.finance.yahoo.com/v8/finance/chart","provenance":prov,"research_only_not_mm_canonical":True},
      "matched_window":{"c1_first_event":c1[0]["date"],"c1_last_event":c1[-1]["date"],"c1_events":len(c1),
                        "c2_first_event":events[0]["date"],"c2_last_event":events[-1]["date"],"c2_events":len(events),
                        "last_return_date":dates[dates.index(events[-1]["date"])+HOLD],"common_daily_rows":len(dates)},
      "baselines":{"same_window_unconditional_smh_20d_mean":mean(unconditional),"c1_event_smh_gross_mean":mean([e["SMH"] for e in c1]),
                   "c2_event_smh_gross_mean":mean([e["SMH"] for e in events]),"c2_event_qqq_mean":mean([e["QQQ"] for e in events]),
                   "c2_event_spy_mean":mean([e["SPY"] for e in events])},
      "c1_cost_stress":c1_costs,"c2_cost_stress":costs,
      "calendar_years":{"count":len(year_q),"positive_excess_vs_qqq_years_at_25bps":sum(x>0 for x in year_q),"positive_share":mean([x>0 for x in year_q])},
      "events_digest_fields":[{"date":e["date"],"smh":e["SMH"],"qqq":e["QQQ"],"spy":e["SPY"],"volume_ratio_to_prior_median":e["event_volume"]/e["prior20_volume_median"]} for e in events],
      "protected_boundaries":{"strategy_spec_write":False,"runtime_activation":False,"broker_submit":False,"promotion_authority":False,"live_trading_change":False}
    }
    with open(OUT,"w") as f: json.dump(receipt,f,indent=2,sort_keys=True)
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
