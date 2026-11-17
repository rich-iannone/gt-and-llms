"""Corpus items: corpus/<split>/<id>/prompt.json, where <split> is dev, test, or unsplit
(items not yet assigned to a split)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from harness import REPO

CORPUS = REPO / "corpus"
DATA = REPO / "data"


@dataclass(frozen=True)
class Item:
    id: str
    split: str
    prompt: str
    data: list[str]
    meta: dict
    dir: Path

    @property
    def hash(self) -> str:
        """Hash of what the model sees: the prompt text and the data files' contents."""
        h = hashlib.sha256(self.prompt.encode())
        for name in sorted(self.data):
            h.update(name.encode())
            h.update((DATA / name).read_bytes())
        return h.hexdigest()

    def user_message(self) -> str:
        files = ", ".join(f"`data/{name}`" for name in self.data)
        label = "Data file" if len(self.data) == 1 else "Data files"
        return f"{label}: {files}.\n\n{self.prompt}"


def load(prompt_id: str) -> Item:
    matches = list(CORPUS.glob(f"*/{prompt_id}/prompt.json"))
    if not matches:
        raise SystemExit(f"no corpus item named {prompt_id!r} under {CORPUS}")
    if len(matches) > 1:
        raise SystemExit(f"{prompt_id!r} is in more than one split: {matches}")
    path = matches[0]
    spec = json.loads(path.read_text())
    if spec["id"] != prompt_id:
        raise SystemExit(f"{path} has id {spec['id']!r}")
    for name in spec["data"]:
        if not (DATA / name).is_file():
            raise SystemExit(f"{prompt_id}: data file {name} isn't in data/")
    meta = {k: v for k, v in spec.items() if k not in ("id", "prompt", "data")}
    return Item(prompt_id, path.parent.parent.name, spec["prompt"], spec["data"], meta, path.parent)


def ids(split: str | None = None) -> list[str]:
    pattern = f"{split or '*'}/*/prompt.json"
    return sorted(p.parent.name for p in CORPUS.glob(pattern))
