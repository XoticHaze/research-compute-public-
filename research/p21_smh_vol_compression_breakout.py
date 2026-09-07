#!/usr/bin/env python3
import hashlib, json, math, os, statistics, time, urllib.request
from datetime import datetime, timezone

SYMS=("SMH","QQQ","SPY")
LOOKBACK_VOL=20
HISTORY=756
BREAKOUT=63
HOLD=20
COSTS=(10.0,25.0,50.0)
OUT=os.environ.get("P21_OUTPUT","p21_smh_vol_compression_breakout_receipt.json")
UA="Mozilla/5.0 research-compute-public p21"

def fetch(sym):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=946684800&period2=1788825600&interval=1d&events=history&includeAdjustedClose=true"
    last=None
    for k in range(5):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA})
            with urllib.request.urlopen(req,timeout=30) as r: raw=r.read()
            obj=json.loads(raw)["chart"]["result"][0]
            ts=obj["timestamp"]
            adj=(obj.get("indicators",{}).get("adjclose") or [{}])[0].get("adjclose")
            if not adj: adj=obj["indicators"]["quote"][0]["close"]
            rows={datetime.fromtimestamp(t,timezone.utc).date().isoformat():float(p) for t,p in zip(ts,adj) if p is not None and p>0}
            return rows,{"url":url,"rows":len(rows),"payload_sha256":hashlib.sha256(raw).hexdigest()}
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
    out=[]
    for k in range(n):
        a=len(xs)*k//n; b=len(xs)*(k+1)//n; out.append(xs[a:b])
    return out

def main():
    data={}; prov={}
    for s in SYMS:data[s],prov[s]=fetch(s)
    dates=sorted(set.intersection(*(set(data[s]) for s in SYMS)))
    px={s:[data[s][d] for d in dates] for s in SYMS}
    lret=[None]+[math.log(px["SMH"][i]/px["SMH"][i-1]) for i in range(1,len(dates))]
    vols=[None]*len(dates)
    for i in range(LOOKBACK_VOL,len(dates)):
        w=[x for x in lret[i-LOOKBACK_VOL+1:i+1] if x is not None]
        if len(w)==LOOKBACK_VOL: vols[i]=statistics.pstdev(w)*math.sqrt(252)
    events=[]; next_ok=0
    start=max(HISTORY+LOOKBACK_VOL,BREAKOUT)
    for i in range(start,len(dates)-HOLD):
        hist=[v for v in vols[i-HISTORY:i] if v is not None]
        if len(hist)<HISTORY-5 or i<next_ok: continue
        thr=pctile(hist,0.20)
        if vols[i] is not None and vols[i] <= thr and px["SMH"][i] > max(px["SMH"][i-BREAKOUT:i]):
            ev={"date":dates[i],"vol":vols[i],"threshold":thr}
            for s in SYMS: ev[s]=px[s][i+HOLD]/px[s][i]-1.0
            events.append(ev); next_ok=i+HOLD
    if not events: raise RuntimeError("no qualifying events")
    first_i=dates.index(events[0]["date"]); last_i=dates.index(events[-1]["date"])
    unconditional=[]
    for i in range(first_i,last_i+1-HOLD): unconditional.append(px["SMH"][i+HOLD]/px["SMH"][i]-1.0)
    costs={}
    for c in COSTS:
        rt=2*c/10000.0
        net=[e["SMH"]-rt for e in events]
        qex=[(e["SMH"]-rt)-e["QQQ"] for e in events]
        sex=[(e["SMH"]-rt)-e["SPY"] for e in events]
        folds=fold_split(events)
        qfold=[mean([(e["SMH"]-rt)-e["QQQ"] for e in f]) for f in folds if f]
        costs[str(c)]={
            "smh_net_mean":mean(net),"smh_net_median":statistics.median(net),"smh_net_win_rate":mean([x>0 for x in net]),
            "excess_vs_qqq_mean":mean(qex),"excess_vs_spy_mean":mean(sex),
            "positive_qqq_excess_folds":sum(x>0 for x in qfold),"fold_count":len(qfold)
        }
    by_year={}
    for e in events:
        y=e["date"][:4]; by_year.setdefault(y,[]).append(e)
    primary=costs["25.0"]
    year_q=[]
    for y,es in sorted(by_year.items()): year_q.append(mean([(e["SMH"]-0.005)-e["QQQ"] for e in es]))
    decision="P21_VOL_COMPRESSION_BREAKOUT_SUPPORTED" if (len(events)>=40 and primary["excess_vs_qqq_mean"]>0 and primary["excess_vs_spy_mean"]>0 and primary["positive_qqq_excess_folds"]>=3 and mean(year_q)>0 and costs["50.0"]["smh_net_mean"]>0) else "P21_VOL_COMPRESSION_BREAKOUT_NOT_SUPPORTED"
    receipt={
      "schema":"research.p21_smh_vol_compression_breakout.v1","parent_id":"P21","child_id":"P21-C1","decision":decision,
      "hypothesis":{"instrument":"SMH","vol_window_sessions":LOOKBACK_VOL,"causal_history_sessions":HISTORY,"vol_percentile":0.20,"breakout_prior_sessions":BREAKOUT,"hold_sessions":HOLD,"nonoverlap":True,"cost_bps_per_side":list(COSTS)},
      "source":{"provider":"Yahoo Finance Chart JSON","transport":"query1.finance.yahoo.com/v8/finance/chart","provenance":prov,"research_only_not_mm_canonical":True},
      "matched_window":{"first_event":events[0]["date"],"last_event":events[-1]["date"],"last_return_date":dates[dates.index(events[-1]["date"])+HOLD],"events":len(events),"common_daily_rows":len(dates)},
      "baselines":{"same_window_unconditional_smh_20d_mean":mean(unconditional),"event_smh_gross_mean":mean([e["SMH"] for e in events]),"event_qqq_mean":mean([e["QQQ"] for e in events]),"event_spy_mean":mean([e["SPY"] for e in events])},
      "cost_stress":costs,
      "calendar_years":{"count":len(year_q),"positive_excess_vs_qqq_years_at_25bps":sum(x>0 for x in year_q),"positive_share":mean([x>0 for x in year_q])},
      "events_digest_fields":[{"date":e["date"],"smh":e["SMH"],"qqq":e["QQQ"],"spy":e["SPY"]} for e in events],
      "protected_boundaries":{"strategy_spec_write":False,"runtime_activation":False,"broker_submit":False,"promotion_authority":False,"live_trading_change":False}
    }
    with open(OUT,"w") as f: json.dump(receipt,f,indent=2,sort_keys=True)
    print(json.dumps({k:receipt[k] for k in ("decision","matched_window","baselines","cost_stress","calendar_years")},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
