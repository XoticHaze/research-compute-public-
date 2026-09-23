from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "mmibkr.selected_runtime_maintenance_hold.v1"


def read_maintenance_hold(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema": SCHEMA,
            "enabled": False,
            "reason": "not_configured",
            "broker_mutation_authority": False,
            "live_execution_allowed": False,
        }

    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, Mapping):
        raise ValueError("maintenance_hold_not_object")
    if node.get("schema") != SCHEMA:
        raise ValueError("maintenance_hold_schema_mismatch")
    enabled = node.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("maintenance_hold_enabled_not_boolean")
    reason = str(node.get("reason") or "").strip()
    if enabled and not reason:
        raise ValueError("maintenance_hold_reason_required")
    if node.get("broker_mutation_authority") is not False:
        raise ValueError("maintenance_hold_broker_authority_rejected")
    if node.get("live_execution_allowed") is not False:
        raise ValueError("maintenance_hold_live_authority_rejected")

    return {
        "schema": SCHEMA,
        "enabled": enabled,
        "reason": reason or "disabled",
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    args = parser.parse_args()
    node = read_maintenance_hold(Path(args.path))
    print("true" if node["enabled"] else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
