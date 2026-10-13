"""Bounded pure tests for discovery; must not run real GitHub calls."""
import importlib.util
from pathlib import Path
import unittest
from urllib.error import HTTPError

script = Path(__file__).resolve().parents[1] / "scripts/public_compute_fleet_discovery_v1.py"
spec = importlib.util.spec_from_file_location("fleet_discovery", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def item(name, ident, **updates):
    repo = {"id": ident, "name": name, "full_name": "XoticHaze/" + name,
            "default_branch": "main", "private": False, "archived": False,
            "disabled": False, "owner": {"login": "XoticHaze"}}
    repo.update(updates)
    return repo

class PublicFleetDiscoveryTests(unittest.TestCase):
    def fetcher(self, items, sha=None):
        calls = []
        def fetch(path):
            calls.append(path)
            if path.startswith("/users/"):
                return items
            if sha is None:
                raise HTTPError(path, 404, "Not found", None, None)
            return {"sha": sha}
        return fetch, calls

    def test_only_public_data_and_no_admission(self):
        fetch, calls = self.fetcher([item("alpha", 10), item("beta", 11)], "1"*40)
        out = mod.public_only_scan("XoticHaze", fetch)
        self.assertEqual(out["admission_authority"], "NONE_DISCOVERY_ONLY")
        self.assertEqual(len(out["repositories"]), 2)
        self.assertEqual(out["repositories"][0]["candidate_workflow"]["git_blob_sha"], "1"*40)
        self.assertEqual(len([c for c in calls if "/contents/" in c]), 2)
        self.assertNotIn("credential", repr(out).lower())
        self.assertNotIn("private_source", repr(out).lower())

    def test_public_repo_without_shared_workflow_stays_discovered(self):
        fetch, _ = self.fetcher([item("alpha", 10)])
        out = mod.public_only_scan("XoticHaze", fetch)
        self.assertIsNone(out["repositories"][0]["candidate_workflow"])

    def test_private_entry_fails_entire_scan(self):
        fetch, _ = self.fetcher([item("secret", 10, private=True)])
        with self.assertRaisesRegex(ValueError, "nonpublic"):
            mod.public_only_scan("XoticHaze", fetch)

    def test_identity_spoof_fails(self):
        fetch, _ = self.fetcher([item("a", 10, full_name="Other/a")])
        with self.assertRaisesRegex(ValueError, "identity"):
            mod.public_only_scan("XoticHaze", fetch)

    def test_duplicate_identity_fails(self):
        fetch, _ = self.fetcher([item("a", 10), item("b", 10)])
        with self.assertRaisesRegex(ValueError, "identity"):
            mod.public_only_scan("XoticHaze", fetch)

    def test_invalid_workflow_sha_fails(self):
        fetch, _ = self.fetcher([item("a", 10)], "not_immutable")
        with self.assertRaisesRegex(ValueError, "blob_sha"):
            mod.public_only_scan("XoticHaze", fetch)

    def test_archived_repo_not_in_candidate_set(self):
        fetch, _ = self.fetcher([item("retired", 10, archived=True)])
        self.assertEqual(mod.public_only_scan("XoticHaze", fetch)["repositories"], [])

    def test_pagination_bounded_and_sorted(self):
        calls = []
        first = [item("r" + str(i), i+1) for i in range(100)]
        last = [item("a", 200)]
        def fetch(path):
            calls.append(path)
            if path.startswith("/users/"):
                return first if "&page=1&type=owner" in path else last
            raise HTTPError(path, 404, "Not found", None, None)
        got = mod.public_only_scan("XoticHaze", fetch)
        self.assertEqual(len(got["repositories"]), 101)
        self.assertEqual(got["repositories"][0]["repository"], "XoticHaze/a")
        self.assertEqual(len([p for p in calls if p.startswith("/users/")]), 2)

if __name__ == "__main__":
    unittest.main()
