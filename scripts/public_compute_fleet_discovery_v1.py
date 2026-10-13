"""Daily public-only GitHub repository inventory. NEVER admits private compute."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
import re
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

SCHEMA = "commandcenter.public_compute_discovery.v1"
PUBLIC_PATH = "rendezvous/fleet/public-compute-candidates-v1.json"
# A discovered workflow is only a candidate: proof of signed authority and
# the generic invocation/receipt ABI lives OUTSIDE this public inventory.
WORKFLOW_PATH = ".github/workflows/secure-compute-harness-v1.yml"
OWNER = "XoticHaze"
REPO = "XoticHaze/research-compute-public-"


def github_json(path: str, *, method: str = "GET", body: dict | None = None) -> dict | list:
    data = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "public-compute-discovery-v1",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request("https://api.github.com" + path, method=method, data=data, headers=headers)
    with urlopen(request, timeout=20) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def public_only_scan(owner: str, fetch: Callable[[str], dict | list]) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})", owner):
        raise ValueError("invalid_owner")
    rows, seen = [], set()
    for page in range(1, 12):
        batch = fetch("/users/" + quote(owner) + "/repos?per_page=100&page=" + str(page) + "&type=owner")
        if not isinstance(batch, list) or len(batch) > 100:
            raise ValueError("public_inventory_invalid")
        for repo in batch:
            if not isinstance(repo, dict) or repo.get("private") is not False:
                raise ValueError("nonpublic_or_ambiguous_repository")
            ident = repo.get("id")
            name = repo.get("name")
            owner_node = repo.get("owner") or {}
            full = repo.get("full_name")
            branch = repo.get("default_branch")
            if (type(ident) is not int or ident <= 0 or ident in seen
                    or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name)
                    or owner_node.get("login", "").lower() != owner.lower()
                    or full != owner_node["login"] + "/" + name
                    or not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", branch)
                    or ".." in branch or branch.startswith("/")):
                raise ValueError("public_repository_identity_invalid")
            seen.add(ident)
            if repo.get("archived") or repo.get("disabled"):
                continue
            # This request checks a public workflow's exact blob identity;
            # existence is discovery, never security admission.
            api = "/repos/" + quote(owner_node["login"]) + "/" + quote(name)
            api += "/contents/" + WORKFLOW_PATH + "?ref=" + quote(branch, safe="")
            try:
                wf = fetch(api)
            except HTTPError as exc:
                if exc.code != 404:
                    raise
                wf = None
            sha = (wf or {}).get("sha") if isinstance(wf, dict) else None
            if sha is not None and (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)):
                raise ValueError("workflow_blob_sha_invalid")
            rows.append({
                "repository": full,
                "repository_id": ident,
                "default_branch": branch,
                "candidate_workflow": ({"path": WORKFLOW_PATH, "git_blob_sha": sha} if sha else None),
            })
        if len(batch) < 100:
            break
    else:
        raise ValueError("public_inventory_pagination_exceeded")
    return {
        "schema": SCHEMA,
        "owner": owner,
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "admission_authority": "NONE_DISCOVERY_ONLY",
        "repositories": sorted(rows, key=lambda row: row["repository"].lower()),
    }


def publish(manifest: dict, *, fetch: Callable[..., dict | list] = github_json) -> None:
    if (manifest.get("schema") != SCHEMA
            or manifest.get("admission_authority") != "NONE_DISCOVERY_ONLY"
            or manifest.get("owner") != OWNER):
        raise ValueError("publication_not_public_discovery")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN_missing")
    api = "/repos/" + REPO + "/contents/" + PUBLIC_PATH
    existing = None
    try:
        existing = fetch(api + "?ref=main")
    except HTTPError as exc:
        if exc.code != 404:
            raise
    body = {
        "message": "chore: daily public-repository discovery only (no admission)",
        "branch": "main",
        "content": base64.b64encode((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()).decode(),
    }
    if isinstance(existing, dict) and existing.get("sha"):
        body["sha"] = existing["sha"]
    node = fetch(api, method="PUT", body=body)
    if not isinstance(node, dict) or not node.get("commit", {}).get("sha"):
        raise RuntimeError("public_inventory_publication_failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out = public_only_scan(OWNER, lambda path: github_json(path))
    print("PUBLIC_COMPUTE_DISCOVERY=PASS")
    print("PUBLIC_REPO_COUNT=" + str(len(out["repositories"])))
    print("CANDIDATE_HARNESS_COUNT=" + str(sum(bool(r["candidate_workflow"]) for r in out["repositories"])))
    print("AUTOMATIC_PRIVATE_ADMISSION=0")
    if not args.dry_run:
        publish(out)
        print("PUBLIC_COMPUTE_CANDIDATE_SNAPSHOT_PUBLISHED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
