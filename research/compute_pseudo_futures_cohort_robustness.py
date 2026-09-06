#!/usr/bin/env python3
"""Paired-provider robustness for the first compute pseudo-futures forecast.

This specifically tests whether the H100 6m survivor from the broad generation index
persists when origin and realized prices use the same provider cohort. Cross-generation
fair value is also restricted to those paired target providers at the origin.
"""
from __future__ import annotations

import argparse, csv, gzip, hashlib, json, math, statistics, tempfile, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA="research_compute_public.p10_pseudo_futures_cohort_robustness.v1"


def fnum(x):
    try: v=float(x)
    except (TypeError,ValueError): return None
    return v if math.isfinite(v) and v>0 else None


def inum(x):
    try: v=int(float(x))
    except (TypeError,ValueError): return None
    return v if v>0 else None


def gpu_name(x,allowed):
    u=(x or "").upper().replace("NVIDIA"," ")
    for g in sorted(allowed,key=len,reverse=True):
        if g in u: return g
    return None


def gpu_price(r):
    p=fnum(r.get("price_per_gpu_hour"))
    if p is not None: return p
    total=fnum(r.get("price_per_hour")); n=inum(r.get("gpu_count"))
    return total/n if total is not None and n else None


def download(spec,dst):
    h=hashlib.sha256(); size=0
    with urllib.request.urlopen(spec["url"],timeout=180) as src,dst.open("wb") as out:
        while True:
            b=src.read(1024*1024)
            if not b: break
            h.update(b); out.write(b); size+=len(b)
    got=h.hexdigest()
    if got!=spec["sha256"]: raise RuntimeError(f"digest mismatch {got} != {spec['sha256']}")
    return {"url":spec["url"],"sha256":got,"bytes":size}


def mord(month):
    y,m=map(int,month.split("-")); return y*12+m-1


def addm(month,n):
    o=mord(month)+n; return f"{o//12:04d}-{o%12+1:02d}"


def ols_slope(series):
    if len(series)<2: return None
    xs=[float(mord(m)) for m,p in series]; ys=[math.log(p) for m,p in series]
    xm=statistics.fmean(xs); ym=statistics.fmean(ys); den=sum((x-xm)**2 for x in xs)
    if den<=0: return None
    return sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den


def metrics(rows,model):
    vals=[r for r in rows if r.get(model) is not None]
    if not vals: return {"n":0,"mape":None,"median_ape":None,"mae":None}
    ae=[abs(r[model]-r["realized"]) for r in vals]; ape=[e/r["realized"] for e,r in zip(ae,vals)]
    return {"n":len(vals),"mape":statistics.fmean(ape),"median_ape":statistics.median(ape),"mae":statistics.fmean(ae)}


def improve(ch,b):
    return None if ch is None or b is None or b<=0 else (b-ch)/b


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("contract",type=Path); ap.add_argument("output",type=Path)
    ns=ap.parse_args(); c=json.loads(ns.contract.read_text())
    targets=list(c["target_generations"]); pool=list(c["cross_generation_pool"]); allowed=set(pool)
    bw={k:float(v) for k,v in c["memory_bandwidth_tb_s"].items()}; pt=c["pricing_type"]
    receipts=[]; seen=set(); by_provider_date=defaultdict(list); raw_count=0
    with tempfile.TemporaryDirectory() as td:
        for i,spec in enumerate(c["archives"]):
            p=Path(td)/f"a{i}.csv.gz"; receipts.append(download(spec,p))
            with gzip.open(p,"rt",encoding="utf-8",newline="") as fh:
                for r in csv.DictReader(fh):
                    if (r.get("pricing_type") or "").strip().lower()!=pt: continue
                    g=gpu_name(r.get("gpu_name",""),allowed)
                    if g is None: continue
                    provider=(r.get("provider") or r.get("source") or "").strip().lower(); date=(r.get("snapshot_date") or "").strip(); price=gpu_price(r)
                    if not provider or not date or price is None: continue
                    raw_count+=1; ident=(provider,date,g,round(price,10))
                    if ident in seen: continue
                    seen.add(ident); by_provider_date[(provider,date,g)].append(price)

    # provider/date/generation median, then last date per provider/month/generation
    pdate={(p,d,g):statistics.median(v) for (p,d,g),v in by_provider_date.items()}
    monthly={}  # (provider, month, generation) -> {date,price}
    for (p,d,g),price in pdate.items():
        key=(p,d[:7],g); prev=monthly.get(key)
        if prev is None or d>prev["date"]: monthly[key]={"date":d,"price":price}

    providers_by_mg=defaultdict(set)
    for p,m,g in monthly: providers_by_mg[(m,g)].add(p)
    months_by_gen={g:sorted({m for p,m,gg in monthly if gg==g}) for g in pool}

    forecasts=[]; min_common=int(c["minimum_common_target_providers"]); min_cross_g=int(c["minimum_cross_generation_sources"]); min_cross_p=int(c["minimum_providers_per_cross_generation"]); min_prior=int(c["minimum_prior_months_for_depreciation"])
    for target in targets:
        for origin_m in months_by_gen[target]:
            for h in [int(x) for x in c["horizon_months"]]:
                realized_m=addm(origin_m,h)
                common=sorted(providers_by_mg[(origin_m,target)] & providers_by_mg[(realized_m,target)])
                if len(common)<min_common: continue
                origin_prices=[monthly[(p,origin_m,target)]["price"] for p in common]
                realized_prices=[monthly[(p,realized_m,target)]["price"] for p in common]
                origin=statistics.median(origin_prices); realized=statistics.median(realized_prices)

                # Cohort-specific past target index through origin.
                hist=[]
                for m in months_by_gen[target]:
                    if mord(m)>mord(origin_m): break
                    vals=[monthly[(p,m,target)]["price"] for p in common if (p,m,target) in monthly]
                    if len(vals)>=min_common: hist.append((m,statistics.median(vals)))
                slope=ols_slope(hist) if len(hist)>=min_prior else None
                dep=origin*math.exp(min(0.0,slope)*h) if slope is not None else None

                levels=[]; cross_detail={}
                for g in pool:
                    if g==target: continue
                    cp=[p for p in common if (p,origin_m,g) in monthly]
                    if len(cp)<min_cross_p: continue
                    px=statistics.median([monthly[(p,origin_m,g)]["price"] for p in cp])
                    levels.append(px/bw[g]); cross_detail[g]={"provider_count":len(cp),"median_price":px,"providers":cp}
                cross=statistics.median(levels)*bw[target] if len(levels)>=min_cross_g else None
                forecasts.append({
                    "generation":target,"horizon_months":h,"origin_month":origin_m,"realized_month":realized_m,
                    "common_target_provider_count":len(common),"common_target_providers":common,
                    "origin":origin,"realized":realized,"changed_outcome":origin!=realized,
                    "random_walk":origin,"depreciation":dep,"bandwidth_cross_generation":cross,
                    "depreciation_log_slope":slope,"cross_generation_detail":cross_detail,
                })

    min_changed=int(c["minimum_changed_origins_for_supported_result"]); mat=float(c["material_improvement_fraction"])
    results=[]
    for g in targets:
        for h in [int(x) for x in c["horizon_months"]]:
            rows=[r for r in forecasts if r["generation"]==g and r["horizon_months"]==h]
            changed=[r for r in rows if r["changed_outcome"]]
            mm={m:metrics(changed,m) for m in ("random_walk","depreciation","bandwidth_cross_generation")}
            ch=mm["bandwidth_cross_generation"]["mape"]; rw=mm["random_walk"]["mape"]; dep=mm["depreciation"]["mape"]
            irw=improve(ch,rw); idep=improve(ch,dep)
            supported=all(mm[m]["n"]>=min_changed for m in mm)
            passes=bool(supported and irw is not None and idep is not None and irw>=mat and idep>=mat)
            results.append({"generation":g,"horizon_months":h,"origin_count":len(rows),"changed_origin_count":len(changed),"changed_metrics":mm,"improve_rw":irw,"improve_dep":idep,"supported":supported,"passes":passes,"common_provider_count_median":statistics.median([r["common_target_provider_count"] for r in rows]) if rows else None})

    focus=c["focus_survivor"]; focus_row=next((r for r in results if r["generation"]==focus["generation"] and r["horizon_months"]==int(focus["horizon_months"])),None)
    if focus_row and focus_row["supported"]:
        classification="H100_6M_SURVIVES_PAIRED_PROVIDER_COHORT" if focus_row["passes"] else "H100_6M_FAILS_PAIRED_PROVIDER_COHORT"
    else:
        classification="INSUFFICIENT_PAIRED_PROVIDER_COHORT_FOR_H100_6M"

    result={"schema":SCHEMA,"research_only":True,"promotion_authority":False,"private_data_loaded":False,
            "source":{"dataset":c["dataset"],"archive_receipts":receipts},"cohort_policy":c["cohort_policy"],
            "counts":{"raw_target_rows":raw_count,"exact_dedup_rows":len(seen),"provider_date_generation_rows":len(pdate),"provider_month_generation_rows":len(monthly),"forecast_rows":len(forecasts)},
            "coverage":{"months_by_generation":months_by_gen},"results":results,"focus_result":focus_row,"classification":classification,
            "focus_examples":[r for r in forecasts if r["generation"]==focus["generation"] and r["horizon_months"]==int(focus["horizon_months"]) and r["changed_outcome"]][:80]}
    ns.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("P10_COHORT_TERMINAL="+json.dumps({"classification":classification,"counts":result["counts"],"focus_result":focus_row,"results":results},sort_keys=True))

if __name__=="__main__": main()
