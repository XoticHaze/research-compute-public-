from __future__ import annotations

import json
import urllib.request
from pathlib import Path

BASE = "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/"
STANDARD_URL = BASE + "performance/standard?idType=ticker&performanceSubType=cumulative&productType=ETF"
ROLLING_URL = BASE + "performance/rolling?idType=ticker&variationType=1M&productType=ETF"


def fetch_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CC-Market-Research/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def shareclass_endpoint(payload, key):
    if not isinstance(payload, dict):
        return None
    for series in payload.get(key, []):
        if str(series.get("type", "")).lower() != "shareclass":
            continue
        data = series.get("data") or []
        if data:
            return {
                "label": series.get("label"),
                "start": data[0],
                "end": data[-1],
                "points": len(data),
            }
    return None


def main():
    standard = fetch_json(STANDARD_URL)
    rolling = fetch_json(ROLLING_URL)
    keys = ("lineChart1YData", "lineChart3YData", "lineChart5YData", "lineChart10YData")
    endpoints = {key: shareclass_endpoint(rolling, key) for key in keys}
    standard_profile = {
        "type": type(standard).__name__,
        "cumulativePerformance": standard.get("cumulativePerformance") if isinstance(standard, dict) else None,
        "raw_scalar": standard if isinstance(standard, (str, int, float, bool)) or standard is None else None,
    }
    output = {
        "schema": "research.p46_dbc_totalreturn_checkpoint_r1",
        "parent": "P46",
        "effective_date": rolling.get("effectiveDate") if isinstance(rolling, dict) else None,
        "standard_profile": standard_profile,
        "rolling_shareclass_endpoints": endpoints,
        "decision": (
            "DBC_DIRECT_TOTAL_RETURN_CHECKPOINTS_EXTRACTED"
            if any(endpoints.values())
            else "DBC_DIRECT_TOTAL_RETURN_NOT_EXPOSED"
        ),
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/p46_dbc_totalreturn_checkpoint_r1.json").write_text(json.dumps(output, indent=2, sort_keys=True))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
