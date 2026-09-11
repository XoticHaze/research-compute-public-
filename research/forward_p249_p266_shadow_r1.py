from __future__ import annotations

import json
import runpy
from pathlib import Path

# Fresh execution trigger only: frozen observer semantics remain unchanged.
LEGACY_MODULE = Path(__file__).with_name("p279_p249_p266_forward_shadow_observer_r1.py")
LEGACY_ARTIFACT = Path("artifacts/p279_p249_p266_forward_shadow_observer_r1.json")
OUTPUT = Path("artifacts/forward_p249_p266_shadow_r1.json")
WORKLOAD_ID = "FORWARD_P249_P266_SHADOW_R1"


def main() -> None:
    runpy.run_path(str(LEGACY_MODULE), run_name="__main__")
    payload = json.loads(LEGACY_ARTIFACT.read_text())
    payload["schema"] = "research.forward_p249_p266_shadow_r1"
    payload["parent"] = "P249/P266/P278"
    payload["workload_id"] = WORKLOAD_ID
    payload["identity_note"] = "The legacy implementation filename used local alias P279 before a concurrent canonical-parent collision was detected. P279 is not this workload's parent identity."
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
