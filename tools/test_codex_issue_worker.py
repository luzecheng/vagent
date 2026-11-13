"""Offline unit tests for the read-only worker."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

P = pathlib.Path(__file__).with_name("codex_issue_worker.py")
spec = importlib.util.spec_from_file_location("worker", P)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class WorkerTests(unittest.TestCase):
    def issue(self, author="luzecheng", body=None, state="open"):
        return {"user": {"login": author}, "body": worker.MARKER if body is None else body,
                "state": state}
    def test_owner_and_allowlist_required(self):
        self.assertTrue(worker.eligible(self.issue(), 2, {2}))
        self.assertFalse(worker.eligible(self.issue(), 3, {2}))
        self.assertFalse(worker.eligible(self.issue(author="attacker"), 2, {2}))
        self.assertFalse(worker.eligible(self.issue(body="hello"), 2, {2}))
        self.assertFalse(worker.eligible(self.issue(state="closed"), 2, {2}))
        self.assertFalse(worker.eligible(dict(self.issue(), pull_request={}), 2, {2}))
    def test_duplicate_result_skips_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(worker, "issue_info", return_value=self.issue()), \
                 patch.object(worker, "comments", return_value=[{"body": worker.DONE}]), \
                 patch.object(worker, "run") as execute:
                worker.once([2], pathlib.Path(tmp), pathlib.Path(tmp) / "state")
                execute.assert_not_called()
    def test_dry_run_does_not_execute_or_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = pathlib.Path(tmp) / "state"
            with patch.object(worker, "issue_info", return_value=self.issue()), \
                 patch.object(worker, "comments", return_value=[]), \
                 patch.object(worker, "run") as execute:
                worker.once([2], pathlib.Path(tmp), state, dry_run=True)
                execute.assert_not_called()
                self.assertFalse((state / "issue-2.claimed").exists())

if __name__ == "__main__":
    unittest.main()
