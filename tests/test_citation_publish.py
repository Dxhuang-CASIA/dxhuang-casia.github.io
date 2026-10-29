import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="citation-publish-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.source = self.base / "source"
        self.env = os.environ.copy()
        # Tests must not depend on the developer's Git identity or signing setup.
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.command("git", "init", "--bare", str(self.remote), cwd=self.base)
        self.command("git", "init", "-b", "main", str(self.source), cwd=self.base)
        self.git("config", "user.name", "Citation Test")
        self.git("config", "user.email", "citation-test@example.invalid")
        self.git("remote", "add", "origin", str(self.remote))
        (self.source / "scripts").mkdir()
        (self.source / "data").mkdir()
        (self.source / "index.html").write_text("Original homepage\n")
        self.snapshot = {"publications": {"paper": {"citations": 1}}}
        (self.source / "data/scholar-citations.json").write_text(json.dumps(self.snapshot))
        (self.source / "data/scholar-citations.js").write_text("old snapshot")

    def command(self, *args, cwd=None, check=True):
        return subprocess.run(args, cwd=cwd or self.source, env=self.env,
                              check=check, text=True, capture_output=True)

    def git(self, *args):
        return self.command("git", *args).stdout.strip()

    def prepare(self, updater):
        (self.source / "scripts/sync_citations.py").write_text(updater)
        self.git("add", ".")
        self.git("commit", "-m", "Seed repository")
        self.git("push", "-u", "origin", "main")
        (self.source / "index.html").write_text("Staged homepage edit\n")
        self.git("add", "index.html")
        (self.source / "index.html").write_text("More homepage edits\n")
        self.original_head = self.git("rev-parse", "HEAD")
        self.original_status = self.git("status", "--porcelain")
        self.original_index = self.git("show", ":index.html")

    def publish(self):
        return self.command(sys.executable, str(ROOT / "scripts/sync_citations_to_github.py"),
                            "--repo-path", str(self.source), check=False)

    def assert_source_preserved(self):
        self.assertEqual(self.git("rev-parse", "HEAD"), self.original_head)
        self.assertEqual(self.git("status", "--porcelain"), self.original_status)
        self.assertEqual(self.git("show", ":index.html"), self.original_index)
        self.assertEqual((self.source / "index.html").read_text(), "More homepage edits\n")
        self.assertEqual(json.loads((self.source / "data/scholar-citations.json").read_text()), self.snapshot)

    def remote_git(self, *args):
        return self.command("git", "--git-dir", str(self.remote), *args).stdout.strip()

    def test_publishes_only_data_and_preserves_dirty_worktree_and_index(self):
        self.prepare('''import json
from pathlib import Path
path = Path("data/scholar-citations.json")
snapshot = json.loads(path.read_text())
snapshot["publications"]["paper"]["citations"] = 2
path.write_text(json.dumps(snapshot))
Path("data/scholar-citations.js").write_text("new snapshot")
# Even an unrelated change made by the updater must never be published.
Path("index.html").write_text("Unrelated generated content")
''')
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Citation counts changed: 1", result.stdout)
        changed = self.remote_git("diff-tree", "--no-commit-id", "--name-only", "-r", "main").splitlines()
        self.assertEqual(set(changed), {"data/scholar-citations.json", "data/scholar-citations.js"})
        published = json.loads(self.remote_git("show", "main:data/scholar-citations.json"))
        self.assertEqual(published["publications"]["paper"]["citations"], 2)
        self.assertEqual(self.remote_git("show", "main:index.html"), "Original homepage")
        self.assert_source_preserved()

    def test_failed_fetch_does_not_publish_partial_data(self):
        self.prepare('''from pathlib import Path
Path("data/scholar-citations.json").write_text("partial result")
raise SystemExit(1)
''')
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Local citation sync failed:", result.stderr)
        self.assertEqual(self.remote_git("rev-parse", "main"), self.original_head)
        self.assert_source_preserved()


if __name__ == "__main__":
    unittest.main()
