#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

SCHEMA = "mmibkr.b1_serialization_freeze.v1"
BLOCKED_EXIT = 42


def load_control(path: Path) -> dict:
    node = json.loads(path.read_text(encoding="utf-8"))
    if node.get("schema") != SCHEMA:
        raise SystemExit("b1 serialization freeze schema rejected")
    if not isinstance(node.get("enabled"), bool):
        raise SystemExit("b1 serialization freeze enabled must be boolean")
    blocked = node.get("blocked_push_channels")
    if not isinstance(blocked, list) or any(not isinstance(x, str) or not x.strip() for x in blocked):
        raise SystemExit("b1 serialization freeze blocked_push_channels invalid")
    if node.get("broker_mutation_authority") is not False:
        raise SystemExit("b1 serialization freeze cannot grant broker mutation authority")
    if node.get("runtime_activation_authority") is not False:
        raise SystemExit("b1 serialization freeze cannot grant runtime activation authority")
    if node.get("promotion_authority") is not False:
        raise SystemExit("b1 serialization freeze cannot grant promotion authority")
    if node.get("live_execution_allowed") is not False:
        raise SystemExit("b1 serialization freeze cannot grant live execution")
    return node


def evaluate(control: dict, *, event: str, channel: str) -> tuple[bool, str]:
    event = str(event or "").strip()
    channel = str(channel or "").strip()
    blocked = {str(x).strip() for x in control["blocked_push_channels"]}
    if not control["enabled"]:
        return True, "B1_SERIALIZATION_FREEZE_DISABLED"
    if event == "workflow_dispatch":
        if control.get("workflow_dispatch_allowed") is not True:
            return False, "B1_SERIALIZATION_DISPATCH_REJECTED"
        return True, "B1_SERIALIZATION_DISPATCH_ALLOWED"
    if event == "pull_request":
        return True, "B1_SERIALIZATION_VALIDATION_ALLOWED"
    if event == "push" and channel in blocked:
        return False, "B1_SERIALIZATION_PUSH_BLOCKED"
    return True, "B1_SERIALIZATION_EVENT_NOT_BLOCKED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", default="rendezvous/control/mmibkr-b1-serialization-freeze-r1.json")
    parser.add_argument("--event", required=True)
    parser.add_argument("--channel", required=True)
    args = parser.parse_args()

    control = load_control(Path(args.control))
    allowed, reason = evaluate(control, event=args.event, channel=args.channel)
    print(f"B1_SERIALIZATION_GUARD={reason}")
    print(f"B1_SERIALIZATION_CHANNEL={args.channel}")
    print(f"B1_SERIALIZATION_EVENT={args.event}")
    if not allowed:
        return BLOCKED_EXIT
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
