import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("sync_skills", Path(__file__).with_name("sync-skills.py"))
sync_skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_skills)


class SyncTests(unittest.TestCase):
    def test_committed_package_provenance_and_repeatability(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, output = base / "source", base / "output"
            source.mkdir()
            output.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            def git(*args):
                return sync_skills.git(source, *args).decode().strip()
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "core.autocrlf", "false")
            git("remote", "add", "origin", sync_skills.FORK)
            package = source / "skills" / sync_skills.NAME
            (package / "scripts").mkdir(parents=True)
            (package / "SKILL.md").write_text("committed instructions", encoding="utf-8")
            (package / "scripts/am.mjs").write_bytes(b"console.log('fixture');\n")
            (source / "LICENSE").write_text("license fixture", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "fixture")
            commit = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/upstream/main", commit)
            (package / "SKILL.md").write_text("uncommitted", encoding="utf-8")
            self.assertEqual(sync_skills.sync(source, commit, output), commit)
            target = output / "skills" / sync_skills.NAME
            self.assertEqual((target / "SKILL.md").read_text(), "committed instructions")
            self.assertEqual((target / "LICENSE").read_text(), "license fixture")
            self.assertIn(commit, (target / "UPSTREAM.md").read_text())
            expected = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            (target / "obsolete.txt").write_text("old content")
            (output / "skills/unrelated.md").write_text("keep")
            sync_skills.sync(source, commit, output)
            actual = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            self.assertEqual(expected, actual)
            self.assertTrue((output / "skills/unrelated.md").exists())
            git("remote", "set-url", "origin", "https://github.com/another/repository")
            with self.assertRaises(ValueError):
                sync_skills.sync(source, commit, output)


if __name__ == "__main__":
    unittest.main()
