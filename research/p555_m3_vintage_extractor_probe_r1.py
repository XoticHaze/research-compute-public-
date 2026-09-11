from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
from pypdf import PdfReader

UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
BASE = "https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/{year}/{mon}{yy}prel.pdf"
SAMPLES = [(2020,"jan"),(2020,"jun"),(2020,"dec"),(2021,"jan"),(2021,"jun"),(2021,"dec")]
NEEDLES = ["industrial machinery", "unfilled orders", "value of shipments", "table 3", "table 7"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_pypdf(data: bytes) -> str:
    import io
    reader = PdfReader(io.BytesIO(data))
    return "\n\f\n".join((p.extract_text() or "") for p in reader.pages)


def extract_pdftotext(data: bytes) -> tuple[str, str | None]:
    exe = shutil.which("pdftotext")
    if not exe:
        return "", "pdftotext_missing"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "release.pdf"
        p.write_bytes(data)
        cp = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, text=True, timeout=90)
        if cp.returncode != 0:
            return cp.stdout or "", f"rc={cp.returncode}: {cp.stderr[-600:]}"
        return cp.stdout, None


def inspect(text: str) -> dict:
    low = text.lower()
    positions = [m.start() for m in re.finditer("industrial machinery", low)]
    contexts = [normalize(text[max(0,p-700):p+1500]) for p in positions[:8]]
    return {
        "chars": len(text),
        "needle_hits": {n: low.count(n) for n in NEEDLES},
        "industrial_contexts": contexts,
        "formfeed_pages": text.count("\f") + (1 if text else 0),
    }


def main() -> None:
    rows = []
    for year, mon in SAMPLES:
        url = BASE.format(year=year, mon=mon, yy=str(year)[2:])
        item = {"year": year, "month": mon, "url": url}
        try:
            r = requests.get(url, headers=UA, timeout=(20,90))
            item.update({"status": r.status_code, "bytes": len(r.content), "content_type": r.headers.get("content-type"), "sha256": hashlib.sha256(r.content).hexdigest()})
            r.raise_for_status()
            pypdf_text = extract_pypdf(r.content)
            native_text, native_error = extract_pdftotext(r.content)
            item["pypdf"] = inspect(pypdf_text)
            item["pdftotext"] = inspect(native_text)
            item["pdftotext_error"] = native_error
            item["usable_native"] = item["pdftotext"]["needle_hits"]["industrial machinery"] > 0 and item["pdftotext"]["needle_hits"]["unfilled orders"] > 0
        except Exception as exc:
            item["exception"] = repr(exc)
            item["usable_native"] = False
        rows.append(item)
    usable = sum(bool(x.get("usable_native")) for x in rows)
    out = {
        "schema": "research.p555_m3_vintage_extractor_probe_r1",
        "parent": "P555",
        "decision": "NATIVE_EXTRACTION_VIABLE" if usable >= 5 else "NATIVE_EXTRACTION_NOT_YET_VIABLE",
        "sample_count": len(rows),
        "required_usable": 5,
        "usable_native": usable,
        "samples": rows,
        "boundaries": {"scientific_alpha_claim": False, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p555_m3_vintage_extractor_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
