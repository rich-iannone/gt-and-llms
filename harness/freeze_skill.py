"""Freeze the rich arm's skill (plan D1, Phase 5): copy great-tables' skills/great-tables/ at
a commit into arms/rich/skill and record the commit and the tree's hash in PROVENANCE.md.

    uv run harness/freeze_skill.py ~/py_projects/great-tables --rev <sha>
    uv run harness/freeze_skill.py ~/py_projects/great-tables --rev <sha> --replace

The files come from the commit (`git archive`), not the working tree, so uncommitted edits are
never frozen. The tree hash is the one an arm's hash covers (harness/arms.py): every file's
relative path and bytes, in sorted order. An existing arms/rich/skill is only replaced with
--replace. The script prints who committed the skill's files: the skill is meant to be written
by Rich without model assistance (§4.1), and this can't check that, only show the history.
"""

import argparse
import datetime
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import REPO

DEST = REPO / "arms/rich/skill"
PROVENANCE = REPO / "PROVENANCE.md"
SOURCE = "skills/great-tables"
UPSTREAM = "posit-dev/great-tables"


def tree_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr.decode().strip()}")
    return proc.stdout


def extract(repo: Path, sha: str, source: str, out: Path) -> None:
    """Write `source` at `sha` into `out`, without the `source` prefix."""
    data = git(repo, "archive", "--format=tar", sha, "--", source)
    prefix = source.rstrip("/") + "/"
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if not member.name.startswith(prefix):
                raise SystemExit(f"unexpected path in archive: {member.name}")
            rel = Path(member.name[len(prefix) :])
            if rel.is_absolute() or ".." in rel.parts:
                raise SystemExit(f"unsafe path in archive: {member.name}")
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())


def provenance_row(sha: str, source: str, tree: str, committed: str, frozen: str) -> str:
    return (
        f"| rich | {UPSTREAM}@{sha[:7]}, `{source}/`; tree sha256 `{tree}` | Rich Iannone | "
        f"{committed} (commit); frozen {frozen} | copied unchanged by `harness/freeze_skill.py` |"
    )


def record(row: str, path: Path) -> None:
    text = path.read_text()
    new, n = re.subn(r"^\| rich \|.*$", lambda _: row, text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"no `| rich |` row in {path.name}'s Skills table")
    path.write_text(new)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path, help="a great-tables clone")
    parser.add_argument("--rev", required=True, help="the commit to freeze")
    parser.add_argument("--source", default=SOURCE, help=f"the skill's path (default {SOURCE})")
    parser.add_argument("--replace", action="store_true", help="replace an existing skill")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    sha = git(repo, "rev-parse", "--verify", f"{args.rev}^{{commit}}").decode().strip()
    source = args.source.strip("/")
    if not git(repo, "ls-tree", sha, "--", f"{source}/SKILL.md").strip():
        raise SystemExit(f"{source}/SKILL.md doesn't exist at {sha[:7]}")
    if DEST.exists() and not args.replace:
        old = tree_sha256(DEST)
        raise SystemExit(
            f"{DEST.relative_to(REPO)} exists (tree sha256 {old}); pass --replace to replace it"
        )

    with tempfile.TemporaryDirectory(prefix="gt-skill-") as tmp:
        staged = Path(tmp) / "skill"
        extract(repo, sha, source, staged)
        tree = tree_sha256(staged)
        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, DEST)

    committed = git(repo, "show", "-s", "--format=%cs", sha).decode().strip()
    frozen = datetime.date.today().isoformat()
    record(provenance_row(sha, source, tree, committed, frozen), PROVENANCE)

    files = sum(1 for p in DEST.rglob("*") if p.is_file())
    print(f"froze {source}/ at {sha[:7]} into {DEST.relative_to(REPO)}: {files} files")
    print(f"tree sha256 {tree}; recorded in {PROVENANCE.name}")
    log = git(repo, "log", "--format=%h %cs %an <%ae>  %s", sha, "--", source).decode()
    print(f"\nCommits touching {source}/ up to {sha[:7]}:\n{log.rstrip()}")


if __name__ == "__main__":
    main()
