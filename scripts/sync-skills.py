"""从维护 fork 的不可变提交同步 HTML 技能发布包。"""

import argparse
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

NAME = "answer-me-with-html"
ROOT = Path(__file__).resolve().parents[1]
FORK = "https://github.com/favonis-tech/answer-me-with-html"
UPSTREAM = "https://github.com/QingYunA/answer-me-with-html"


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])


def sync(source, ref, root=ROOT):
    source, root = Path(source).resolve(), Path(root).resolve()
    remote = git(source, "remote", "get-url", "origin").decode().strip()
    if remote.removesuffix(".git") not in (FORK, "git@github.com:favonis-tech/answer-me-with-html"):
        raise ValueError("source origin must be the Favonis maintenance fork")
    commit = git(source, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    upstream = git(source, "merge-base", commit, "refs/remotes/upstream/main").decode().strip()
    prefix = "skills/" + NAME + "/"
    entries = git(source, "ls-tree", "-r", "-z", commit, "--", prefix)
    files = {}
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, _ = meta.split()
        path = raw_path.decode("utf-8")
        relative = path.removeprefix(prefix)
        if (kind != b"blob" or mode not in (b"100644", b"100755") or not path.startswith(prefix)
                or any(part in ("", ".", "..") for part in relative.split("/"))
                or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute()):
            raise ValueError("unsupported skill entry: " + path)
        files[relative] = (git(source, "show", commit + ":" + path), mode)
    if "SKILL.md" not in files or "scripts/am.mjs" not in files:
        raise ValueError("source commit is missing the skill entry or bundled CLI")
    files["LICENSE"] = (git(source, "show", commit + ":LICENSE"), b"100644")
    provenance = f"""# Upstream

- Original repository: {UPSTREAM}
- Original commit: `{upstream}`
- Maintenance fork: {FORK}
- Maintenance commit: `{commit}`
- Package directory: `skills/{NAME}`
- License: MIT; see LICENSE and the bundled dependency notices in scripts/am.mjs.

Adapted for Favonis. Original rendering and themes are preserved.
"""
    files["UPSTREAM.md"] = (provenance.encode("utf-8"), b"100644")
    skills = root / "skills"
    target = skills / NAME
    # 只允许替换本仓库内这个生成包，拒绝沿符号链接写入其他目录。
    if skills.is_symlink() or target.is_symlink() or target.resolve() != root / "skills" / NAME:
        raise ValueError("publication target must stay inside this repository")
    skills.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sync-", dir=skills) as staging:
        package = Path(staging) / NAME
        for path, (data, mode) in files.items():
            destination = package / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(0o755 if mode == b"100755" else 0o644)
        if target.exists():
            shutil.rmtree(target)
        package.rename(target)
    return commit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ref", required=True, help="维护 fork 中已验证的提交")
    args = parser.parse_args()
    print(f"Synced {NAME} from {sync(args.source, args.ref)}")
