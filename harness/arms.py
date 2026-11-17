"""Arms (arms/arms.yaml): what each arm adds to the base system prompt and the workspace."""

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from harness import REPO

ARMS = REPO / "arms"
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Arm:
    name: str
    description: str
    system_prompt: str
    skill_dir: Path | None

    @property
    def hash(self) -> str:
        """Hash of everything the arm gives the model: system prompt plus the skill tree."""
        h = hashlib.sha256(self.system_prompt.encode())
        if self.skill_dir:
            for path in sorted(p for p in self.skill_dir.rglob("*") if p.is_file()):
                h.update(path.relative_to(self.skill_dir).as_posix().encode())
                h.update(path.read_bytes())
        return h.hexdigest()

    def populate(self, workspace: Path) -> None:
        if self.skill_dir:
            shutil.copytree(self.skill_dir, workspace / "skill")


def _require(path: Path, arm: str) -> Path:
    if not path.exists():
        raise SystemExit(f"arm {arm!r} isn't set up yet: {path.relative_to(REPO)} doesn't exist")
    return path


def load(name: str) -> Arm:
    arms = yaml.safe_load((ARMS / "arms.yaml").read_text())
    if name not in arms:
        raise SystemExit(f"unknown arm {name!r}; arms.yaml defines {', '.join(arms)}")
    spec = arms[name] or {}
    system_prompt = (ARMS / "base_prompt.md").read_text()
    skill_dir = None

    if "context" in spec:
        docs = _require(REPO / spec["context"], name).read_text()
        system_prompt += f"\n<docs>\n{docs.strip()}\n</docs>\n"
    if "skill" in spec:
        skill_dir = _require(REPO / spec["skill"], name)
        body = FRONTMATTER.sub("", _require(skill_dir / "SKILL.md", name).read_text())
        system_prompt += (
            "\nThe following skill is available. Its files, including any references/, "
            "are in `skill/` in the working directory.\n"
            f'<skill name="{name}">\n{body.strip()}\n</skill>\n'
        )
    return Arm(name, spec.get("description", ""), system_prompt, skill_dir)
