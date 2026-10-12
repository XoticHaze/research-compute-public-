from __future__ import annotations

import io
import unittest
from urllib.error import HTTPError

from scripts.commandcenter_ephemeral_exchange_cleanup_v1 import (
    REPOSITORY, BRANCH, cleanup, paths_for,
)


def http_error(code):
    return HTTPError("https://api.github.com/repositories/redacted", code, "redacted", {}, io.BytesIO())


class EphemeralExchangeCleanupTests(unittest.TestCase):
    def test_two_precise_run_scoped_paths_each_kind(self):
        run="38232080214"
        self.assertEqual(
            paths_for(run,"neutral_gate"),
            ("rendezvous/responses/38232080214/commandcenter-neutral-gate-envelope.json",
             "rendezvous/recipients/38232080214.json"),
        )
        self.assertEqual(
            paths_for(run,"ledger")[0],
            "rendezvous/responses/38232080214/commandcenter-ledger-envelope.json",
        )
        for bad in ("../../branch", "0", "", "abc", "1/2"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    paths_for(bad,"neutral_gate")
        with self.assertRaises(ValueError):
            paths_for(run,"other")

    def test_cleans_only_exact_current_run_with_content_sha_lease(self):
        calls=[]
        def api(method,path,token,data=None):
            calls.append((method,path,data))
            if method=="GET":
                return {"sha":"a"*40}
            self.assertEqual(method,"DELETE")
            self.assertEqual(data["sha"],"a"*40)
            self.assertEqual(data["branch"],BRANCH)
            return {"commit":{"sha":"b"*40}}
        outcome=cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="neutral_gate",token="synthetic",api=api)
        self.assertEqual(outcome,{"status":"PASS","removed_current_tip":2,"already_absent":0})
        self.assertEqual(len(calls),4)
        self.assertTrue(all("38232080214" in path for _,path,_ in calls))
        self.assertFalse(any("38232080215" in path for _,path,_ in calls))

    def test_idempotent_not_found_without_mutation(self):
        calls=[]
        def api(method,path,token,data=None):
            calls.append(method)
            raise http_error(404)
        result=cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="ledger",token="synthetic",api=api)
        self.assertEqual(result["removed_current_tip"],0)
        self.assertEqual(result["already_absent"],2)
        self.assertEqual(calls,["GET","GET"])

    def test_conflicting_branch_reference_refreshes_current_blob(self):
        calls=[]
        attempts={}
        def api(method,path,token,data=None):
            calls.append((method,path))
            if method=="GET":
                return {"sha":"a"*40}
            attempts[path]=attempts.get(path,0)+1
            if attempts[path]==1:
                raise http_error(409)
            return {}
        result=cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="neutral_gate",token="synthetic",api=api)
        self.assertEqual(result["removed_current_tip"],2)
        self.assertEqual(len([x for x in calls if x[0]=="GET"]),4)

    def test_wrong_repo_no_token_bad_sha_and_api_failure_are_rejected(self):
        def fake(method,path,token,data=None):
            return {"sha":"bad"}
        with self.assertRaisesRegex(ValueError,"repository_identity_rejected"):
            cleanup(repo="other/public",run_id="38232080214",proof_kind="ledger",token="synthetic",api=fake)
        with self.assertRaisesRegex(ValueError,"cleanup_token_missing"):
            cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="ledger",token="",api=fake)
        with self.assertRaisesRegex(RuntimeError,"exchange_file_identity_rejected"):
            cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="ledger",token="synthetic",api=fake)
        def broken(method,path,token,data=None):
            raise http_error(403)
        with self.assertRaisesRegex(RuntimeError,"exchange_lookup_rejected"):
            cleanup(repo=REPOSITORY,run_id="38232080214",proof_kind="ledger",token="synthetic",api=broken)


if __name__ == "__main__":
    unittest.main()
