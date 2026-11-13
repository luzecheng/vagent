import tempfile, unittest, subprocess
from pathlib import Path
from unittest.mock import patch, Mock
import codex_daemon as w

class DaemonTests(unittest.TestCase):
    def issue(self, **kw):
        d={"number":7,"state":"open","user":{"login":"luzecheng"},"body":w.APPROVAL}
        d.update(kw)
        return d
    def test_authorization(self):
        self.assertTrue(w.authorized(self.issue()))
        self.assertFalse(w.authorized(self.issue(user={"login":"other"})))
        self.assertFalse(w.authorized(self.issue(body="no marker")))
        self.assertFalse(w.authorized(self.issue(state="closed")))
        self.assertFalse(w.authorized(self.issue(pull_request={})))
    def test_completed(self):
        with patch.object(w,"api",return_value=[{"body":w.RESULT}]):
            self.assertTrue(w.completed(7))
        with patch.object(w,"api",return_value=[]):
            self.assertFalse(w.completed(7))
    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as d, patch.object(w,"completed",return_value=False):
            self.assertEqual(w.process(self.issue(),Path(d),Path(d),True),"ready")
            self.assertFalse((Path(d)/"issue-7.claimed").exists())
    def test_claim_prevents_repeat(self):
        with tempfile.TemporaryDirectory() as d, patch.object(w,"completed",return_value=False), patch.object(w,"command",return_value=Mock(returncode=0)), patch.object(w,"post") as post:
            self.assertEqual(w.process(self.issue(),Path(d),Path(d)),"reported")
            self.assertEqual(w.process(self.issue(),Path(d),Path(d)),"claimed")
            post.assert_called_once()
    def test_timeout(self):
        with tempfile.TemporaryDirectory() as d, patch.object(w,"completed",return_value=False), patch.object(w,"command",side_effect=subprocess.TimeoutExpired("codex",300)), patch.object(w,"post") as post:
            self.assertEqual(w.process(self.issue(),Path(d),Path(d)),"timeout")
            self.assertEqual(post.call_args.args[1],"TIMEOUT")

if __name__=="__main__": unittest.main()
