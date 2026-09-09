from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/performance/rolling"
VARIANTS = ("1D", "1W", "1M")


def fetch(variation: str):
    url = f"{BASE}?idType=ticker&variationType={variation}&productType=ETF"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CC-Market-Research/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return url, response.status, json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return url, exc.code, None, repr(exc)
    except Exception as exc:
        return url, None, None, repr(exc)


def shareclass_profile(payload):
    if not isinstance(payload, dict):
        return None
    output = {"effectiveDate": payload.get("effectiveDate")}
    for key in ("lineChart1YData", "lineChart3YData", "lineChart5YData", "lineChart10YData"):
        found = None
        for series in payload.get(key, []):
            if str(series.get("type", "")).lower() != "shareclass":
                continue
            data = series.get("data") or []
            if data:
                found = {
                    "label": series.get("label"),
                    "points": len(data),
                    "start": data[0],
                    "end": data[-1],
                }
                break
        output[key] = found
    return output


def main():
    variants = {}
    for variation in VARIANTS:
        url, status, payload, error = fetch(variation)
        variants[variation] = {
            "url": url,
            "status": status,
            "error": error,
            "profile": shareclass_profile(payload),
        }
    day = variants["1D"].get("profile") or {}
    day_10y = day.get("lineChart10YData") or {}
    month = variants["1M"].get("profile") or {}
    month_10y = month.get("lineChart10YData") or {}
    daily_points = int(day_10y.get("points") or 0)
    monthly_points = int(month_10y.get("points") or 0)
    if daily_points > monthly_points and daily_points >= 2000:
        decision = "QQQ_DAILY_ISSUER_TOTAL_RETURN_ROUTE_FOUND"
    else:
        decision = "QQQ_DAILY_ISSUER_TOTAL_RETURN_ROUTE_NOT_FOUND"
    output = {
        "schema": "research.p46_qqq_daily_totalreturn_route_r1",
        "parent": "P46",
        "contract": {
            "frozen_variants": list(VARIANTS),
            "daily_admission_rule": "1D Shareclass 10Y series must materially exceed the 1M point count and contain at least 2000 observations",
            "no_model_parameter_or_cost_changes": True,
        },
        "variants": variants,
        "daily_10y_points": daily_points,
        "monthly_10y_points": monthly_points,
        "decision": decision,
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/p46_qqq_daily_totalreturn_route_r1.json").write_text(
        json.dumps(output, indent=2, sort_keys=True)
    )
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
