from __future__ import annotations

import json
import runpy
from pathlib import Path

# Fresh execution trigger only: frozen observer semantics remain unchanged.
LEGACY_MODULE = Path(__file__).with_name("p279_p249_p266_forward_shadow_observer_r1.py")
LEGACY_ARTIFACT = Path("artifacts/p279_p249_p266_forward_shadow_observer_r1.json")
OUTPUT = Path("artifacts/forward_p249_p266_shadow_r1.json")
WORKLOAD_ID = "FORWARD_P249_P266_SHADOW_R1"


def current_publication_admitted(payload: dict) -> bool:
    """Fail closed on source gaps before replacing the stable funded-NAV CURRENT."""
    if not isinstance(payload, dict) or any((
        payload.get("schema") != "research.forward_p249_p266_shadow_r1",
        payload.get("parent") != "P249/P266/P278",
        payload.get("workload_id") != WORKLOAD_ID,
        payload.get("status") != "FORWARD_OBSERVING",
    )):
        return False
    source, forward = payload.get("source_health"), payload.get("forward")
    if not isinstance(source, dict) or not isinstance(forward, dict):
        return False
    if "unresolved_forward_gap" not in source or source["unresolved_forward_gap"] is not None:
        return False
    if forward.get("economic_continuity_verified") is not True:
        return False
    rows = forward.get("observations")
    latest = forward.get("latest_close")
    if not isinstance(rows, list) or not rows or not isinstance(rows[-1], dict) or not isinstance(latest, str):
        return False
    core, satellite = forward.get("p249_core_net"), forward.get("p249_plus_p266_net")
    return bool(
        rows[-1].get("date") == latest
        and source.get("latest_scored_common_session") == latest
        and isinstance(core, dict) and core.get("days") == len(rows)
        and isinstance(satellite, dict) and satellite.get("days") == len(rows)
    )


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
