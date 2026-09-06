#!/usr/bin/env python3
"""Robustness gates for the public P10 provider-conditioned bandwidth test.

Public data only. Re-downloads the SHA-pinned OpenComputePrices archives and reports:
- provider/pricing slice support without weighting repeated rows as separate providers;
- distinct date/month and unique price-vector breadth;
- leave-one-generation-out error separately for H100/H200/B200;
- bundle ambiguity diagnostics for instance/vCPU/RAM variation collapsed by the
  provider-level price comparison.

No interpolation, provider blending, private data, promotion, or trading authority.
"""
from __future__ import annotations

import csv, gzip, hashlib, json, math, statistics, tempfile, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

TARGET = ("H100", "H200", "B200")
SCHEMA = "research_compute_public.p10_provider_history_robustness.v1"


def fnum(x):
    try: v=float(x)
    except (TypeError, ValueError): return None
    return v if math.isfinite(v) and v > 0 else None


def inum(x):
    try: v=int(float(x))
    except (TypeError, ValueError): return None
    return v if v > 0 else None


def gpu_name(x):
    u=(x or "").upper().replace("NVIDIA", " ")
    for g in TARGET:
        if g in u: return g
    return None


def gpu_price(row):
    p=fnum(row.get("price_per_gpu_hour"))
    if p is not None: return p
    total=fnum(row.get("price_per_hour")); n=inum(row.get("gpu_count"))
    return total/n if total is not None and n else None


def cv(vals):
    m=statistics.fmean(vals)
    return statistics.pstdev(vals)/m if m else float("nan")


def download(spec, dst):
    h=hashlib.sha256(); size=0
    with urllib.request.urlopen(spec["url"], timeout=180) as r, dst.open("wb") as out:
        while True:
            b=r.read(1024*1024)
            if not b: break
            h.update(b); out.write(b); size += len(b)
    got=h.hexdigest()
    if got != spec["sha256"]:
        raise RuntimeError(f"digest mismatch {got} != {spec['sha256']}")
    return {"url":spec["url"],"sha256":got,"bytes":size}


def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("contract",type=Path); ap.add_argument("output",type=Path)
    ns=ap.parse_args(); c=json.loads(ns.contract.read_text())
    bw={k:float(v) for k,v in c["memory_bandwidth_tb_s"].items()}
    receipts=[]; rows=[]
    with tempfile.TemporaryDirectory() as td:
        for i,spec in enumerate(c["archives"]):
            p=Path(td)/f"a{i}.csv.gz"; receipts.append(download(spec,p))
            with gzip.open(p,"rt",encoding="utf-8",newline="") as fh:
                for r in csv.DictReader(fh):
                    g=gpu_name(r.get("gpu_name")); pt=(r.get("pricing_type") or "").strip().lower()
                    if g not in TARGET or pt not in {"on_demand","spot","reserved"}: continue
                    price=gpu_price(r); provider=(r.get("provider") or r.get("source") or "").strip().lower()
                    date=(r.get("snapshot_date") or "").strip()
                    if price is None or not provider or not date: continue
                    rows.append({
                        "provider":provider,"date":date,"month":date[:7],"pricing_type":pt,"gpu":g,"price":price,
                        "region":(r.get("region") or r.get("geo_group") or r.get("country") or "__unspecified__").strip(),
                        "variant":(r.get("gpu_variant") or r.get("gpu_interconnect") or "__unspecified__").strip().upper(),
                        "gpu_count":inum(r.get("gpu_count")) or 1,
                        "tenancy":(r.get("tenancy") or "__unspecified__").strip().lower(),
                        "commitment":(r.get("commitment_period") or "__none__").strip().lower(),
                        "bundle":(
                            (r.get("instance_type") or "").strip(),
                            (r.get("vcpus") or "").strip(),
                            (r.get("ram_gb") or "").strip(),
                        ),
                    })

    grouped=defaultdict(lambda:defaultdict(list))
    bundles=defaultdict(lambda:defaultdict(set))
    for r in rows:
        key=(r["provider"],r["date"],r["pricing_type"],r["region"],r["variant"],r["gpu_count"],r["tenancy"],r["commitment"])
        grouped[key][r["gpu"]].append(r["price"]); bundles[key][r["gpu"]].add(r["bundle"])

    matched=[]
    for key,pg in grouped.items():
        if set(pg) != set(TARGET): continue
        prices={g:statistics.median(pg[g]) for g in TARGET}
        rawcv=cv([prices[g] for g in TARGET]); normcv=cv([prices[g]/bw[g] for g in TARGET])
        pergen={}
        for held in TARGET:
            oth=[g for g in TARGET if g!=held]; actual=prices[held]
            rawpred=statistics.median([prices[g] for g in oth])
            normpred=statistics.median([prices[g]/bw[g] for g in oth])*bw[held]
            pergen[held]={"raw_ape":abs(rawpred-actual)/actual,"norm_ape":abs(normpred-actual)/actual}
        matched.append({
            "provider":key[0],"date":key[1],"month":key[1][:7],"pricing_type":key[2],
            "raw_cv":rawcv,"norm_cv":normcv,"prices":prices,"per_generation":pergen,
            "max_bundle_variants":max(len(bundles[key][g]) for g in TARGET),
            "bundle_variant_counts":{g:len(bundles[key][g]) for g in TARGET},
        })

    byslice=defaultdict(list)
    for x in matched: byslice[(x["provider"],x["pricing_type"])].append(x)
    slices=[]
    for (provider,pt), xs in sorted(byslice.items()):
        dates=sorted({x["date"] for x in xs}); months=sorted({x["month"] for x in xs})
        vectors={tuple(round(x["prices"][g],8) for g in TARGET) for x in xs}
        disp_n=sum(x["norm_cv"] < x["raw_cv"] for x in xs)
        pergen={}
        for held in TARGET:
            raw=[x["per_generation"][held]["raw_ape"] for x in xs]
            norm=[x["per_generation"][held]["norm_ape"] for x in xs]
            pergen[held]={
                "improved_count":sum(n < rr for n,rr in zip(norm,raw)),
                "tested_count":len(xs),
                "median_raw_ape":statistics.median(raw),
                "median_norm_ape":statistics.median(norm),
                "median_improves":statistics.median(norm) < statistics.median(raw),
            }
        pergen_gate=all(pergen[g]["median_improves"] for g in TARGET)
        cross_gate=(disp_n > len(xs)/2 and pergen_gate and len(dates)>=3)
        temporal_gate=(cross_gate and len(months)>=2)
        slices.append({
            "provider":provider,"pricing_type":pt,"matched_bucket_count":len(xs),
            "distinct_date_count":len(dates),"first_date":dates[0],"last_date":dates[-1],
            "month_count":len(months),"months":months,"unique_price_vector_count":len(vectors),
            "dispersion_improved_count":disp_n,"dispersion_improved_fraction":disp_n/len(xs),
            "median_raw_cv":statistics.median(x["raw_cv"] for x in xs),
            "median_norm_cv":statistics.median(x["norm_cv"] for x in xs),
            "per_generation_loo":pergen,
            "all_held_generations_median_improve":pergen_gate,
            "cross_section_gate":cross_gate,"two_month_temporal_gate":temporal_gate,
            "ambiguous_bundle_bucket_count":sum(x["max_bundle_variants"]>1 for x in xs),
            "max_bundle_variants_in_bucket":max(x["max_bundle_variants"] for x in xs),
        })

    eligible=[s for s in slices if s["matched_bucket_count"]>=3]
    support=[s for s in eligible if s["cross_section_gate"]]
    temporal=[s for s in eligible if s["two_month_temporal_gate"]]
    providers=sorted({s["provider"] for s in eligible})
    provider_state=[]
    for p in providers:
        ps=[s for s in eligible if s["provider"]==p]
        provider_state.append({
            "provider":p,
            "slice_count":len(ps),
            "support_slice_count":sum(s["cross_section_gate"] for s in ps),
            "temporal_support_slice_count":sum(s["two_month_temporal_gate"] for s in ps),
            "all_slices_support":all(s["cross_section_gate"] for s in ps),
            "any_slice_support":any(s["cross_section_gate"] for s in ps),
        })
    result={
        "schema":SCHEMA,"research_only":True,"promotion_authority":False,"private_data_loaded":False,
        "source":{"dataset":"thatkavish/OpenComputePrices","archive_receipts":receipts},
        "matching":{"no_interpolation":True,"no_provider_blending":True,"target_gpus":list(TARGET),"memory_bandwidth_tb_s":bw},
        "target_row_count":len(rows),"strict_matched_bucket_count":len(matched),
        "eligible_slice_count":len(eligible),"cross_section_support_slice_count":len(support),
        "two_month_temporal_support_slice_count":len(temporal),
        "cross_section_support_fraction":len(support)/len(eligible) if eligible else 0,
        "slices":slices,"provider_state":provider_state,
        "classification":(
            "BANDWIDTH_CONDITIONALLY_SUPPORTED_PROVIDER_AND_CONTRACT_STATE_REQUIRED"
            if eligible and len(support)>len(eligible)/2
            else "BANDWIDTH_NOT_SUPPORTED_ACROSS_MAJORITY_PROVIDER_CONTRACT_SLICES"
        ),
    }
    ns.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("P10_ROBUSTNESS_TERMINAL="+json.dumps({
        "classification":result["classification"],"eligible_slice_count":len(eligible),
        "cross_section_support_slice_count":len(support),"two_month_temporal_support_slice_count":len(temporal),
        "cross_section_support_fraction":result["cross_section_support_fraction"],"provider_state":provider_state,
        "slices":slices,
    },sort_keys=True))


if __name__=="__main__": main()
