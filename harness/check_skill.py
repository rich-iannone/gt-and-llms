"""Check a skill's GT API against the pinned GT (plan Phase 5): every GT method, `loc.*`,
`style.*`, `vals.*` and great_tables name the skill uses must exist, and every call must fit
its signature. It only reads the skill; it doesn't judge its advice.

    uv run harness/check_skill.py                       # arms/rich/skill
    uv run harness/check_skill.py arms/prose/skill --json

It reads the skill's .md and .py files. Python files and fenced code blocks are parsed, and
their calls checked with `inspect.signature(...).bind`. Inline code spans in the prose are
parsed too when they can be (`fmt_number(decimals=2)`); when they can't (`decimals=`), only
the names in them are checked. A method name GT shares with Polars or Pandas (`pipe`, ...) is
only checked on something known to be a GT: a chain from `GT(...)`, or a name assigned one.
GT-like names that don't exist (`fmt_numbr`, `tab_style2`) are flagged wherever they appear.

It runs under the agent's Python, which has the pinned GT; run from the harness environment
it re-runs itself there. Exits 1 if anything is flagged.
"""

import argparse
import ast
import difflib
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT = REPO / "arms/rich/skill"

# Names that look like GT methods, so a misspelt one is flagged on any receiver
GT_LIKE = re.compile(r"(?:fmt|tab|cols|opt|sub)_\w+|data_color|(?:grand_)?summary_rows")
NAMESPACES = ("loc", "style", "vals")
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)[^\n]*\n(.*?)^\1\2\s*$", re.M | re.S)
INLINE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
CODE_LANGS = {"", "python", "py", "python3", "pycon"}


# Prose that names a call as a mistake: "Do not invent `opt_row_striping(color=...)`"
WARNING = re.compile(
    r"\b(?:not|never|don't|doesn't|isn't|no such|avoid|instead of|wrong|invent\w*|hallucinat\w*"
    r"|raises|deprecated)\b",
    re.I,
)


@dataclass
class Finding:
    file: str
    line: int
    code: str
    problem: str
    # In prose that warns against it, so likely meant (listed apart, not counted)
    warned: bool = False


class API:
    """The pinned GT's names: GT's methods, the loc/style/vals namespaces, and great_tables'
    top-level exports."""

    def __init__(self) -> None:
        import great_tables

        self.gt = great_tables.GT
        self.pkg = great_tables
        self.spaces = {n: importlib.import_module(f"great_tables.{n}") for n in NAMESPACES}
        self.methods = {n for n in dir(self.gt) if not n.startswith("_")}
        self.exports = {n for n in dir(great_tables) if not n.startswith("_")}
        shared = set()
        for mod, cls in (("polars", "DataFrame"), ("pandas", "DataFrame")):
            try:
                shared |= set(dir(getattr(importlib.import_module(mod), cls)))
            except ImportError:
                pass
        self.shared = self.methods & shared

    def version(self) -> str:
        from importlib.metadata import distribution

        dist = distribution("great-tables")
        try:
            vcs = json.loads(dist.read_text("direct_url.json") or "{}").get("vcs_info", {})
        except json.JSONDecodeError:
            vcs = {}
        sha = vcs.get("commit_id")
        return f"{dist.version}" + (f" ({sha[:7]})" if sha else "")


def bind_problem(func, call: ast.Call, method: bool) -> str | None:
    """Why `call` doesn't fit `func`'s signature, or None. Calls with *args or **kwargs
    aren't checked."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        k.arg is None for k in call.keywords
    ):
        return None
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return None
    params = sig.parameters
    if not any(p.kind is p.VAR_KEYWORD for p in params.values()):
        # A misspelt keyword also leaves its parameter missing; name the misspelling
        named = [
            n for n, p in params.items() if p.kind not in (p.VAR_POSITIONAL, p.POSITIONAL_ONLY)
        ]
        unknown = [k.arg for k in call.keywords if k.arg not in params]
        if unknown:
            hints = []
            for k in unknown:
                close = difflib.get_close_matches(k, named, n=1)
                hints.append(f"`{k}`" + (f" (did you mean `{close[0]}`?)" if close else ""))
            return f"no parameter {', '.join(hints)}"
    args = [None] * (len(call.args) + method)
    try:
        sig.bind(*args, **{k.arg: None for k in call.keywords})
    except TypeError as e:
        return str(e)
    return None


def _root(node: ast.AST) -> ast.AST:
    """The start of a method chain: `GT(df)` in `GT(df).fmt_number().tab_header()`."""
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return node


def _attr_chain(node: ast.Attribute) -> list[str] | None:
    """`great_tables.loc.body` -> ["great_tables", "loc", "body"]; None if not names only."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return [node.id, *reversed(parts)]


class Checker(ast.NodeVisitor):
    def __init__(self, api: API, prose: bool = False) -> None:
        self.api = api
        self.prose = prose
        self.problems: list[tuple[int, str]] = []
        self.gt_names: set[str] = set()
        # Names a snippet binds itself, which shadow great_tables' (`def html(...)`)
        self.local: set[str] = set()

    def flag(self, node: ast.AST, problem: str) -> None:
        # A call in a chain starts where the chain does; its line is its method's
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node = node.func
        self.problems.append((getattr(node, "end_lineno", None) or 1, problem))

    def is_gt(self, node: ast.AST) -> bool:
        """Whether a method chain is known to start from a GT, or pass through a method only
        GT has."""
        while True:
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == "GT":
                    return True
                if isinstance(f, ast.Attribute) and f.attr in self.api.methods - self.api.shared:
                    return True
                node = f
            elif isinstance(node, ast.Attribute):
                node = node.value
            else:
                return isinstance(node, ast.Name) and node.id in self.gt_names

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.is_gt(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.gt_names.add(t.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.local.add(node.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        if mod == "great_tables" or mod.startswith("great_tables."):
            try:
                target = importlib.import_module(mod)
            except ImportError:
                self.flag(node, f"no module `{mod}`")
                return
            for alias in node.names:
                if alias.name != "*" and not hasattr(target, alias.name):
                    self.flag(node, f"`{mod}` has no `{alias.name}`")
        else:
            self.local.update(a.asname or a.name for a in node.names)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.startswith("great_tables."):
                try:
                    importlib.import_module(alias.name)
                except ImportError:
                    self.flag(node, f"no module `{alias.name}`")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        chain = _attr_chain(node)
        if chain and chain[0] == "great_tables":
            chain = chain[1:]
            if len(chain) == 1 and chain[0] not in self.api.exports:
                self.flag(node, f"great_tables has no `{chain[0]}`")
        if chain and len(chain) == 2 and chain[0] in NAMESPACES:
            space, name = chain
            if space not in self.local and not hasattr(self.api.spaces[space], name):
                self.flag(node, f"`{space}` has no `{name}`")
        if chain and len(chain) == 2 and chain[0] == "GT" and chain[1] not in self.api.methods:
            self.flag(node, f"GT has no method `{chain[1]}`")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        if isinstance(f, ast.Attribute):
            self.method_call(node, f)
        elif isinstance(f, ast.Name):
            self.name_call(node, f.id)
        self.generic_visit(node)

    def method_call(self, node: ast.Call, f: ast.Attribute) -> None:
        name = f.attr
        chain = _attr_chain(f)
        if chain and chain[0] == "great_tables":
            chain = chain[1:]
        if chain and len(chain) == 2 and chain[0] in NAMESPACES and chain[0] not in self.local:
            obj = getattr(self.api.spaces[chain[0]], chain[1], None)
            if obj is not None and (p := bind_problem(obj, node, method=False)):
                self.flag(node, f"`{chain[0]}.{chain[1]}`: {p}")
            return
        if chain and len(chain) == 1 and chain[0] in self.api.exports:
            self.name_call(node, chain[0])
            return
        if chain and len(chain) == 2 and chain[0] == "GT":
            # A missing method is flagged by visit_Attribute; `GT.fmt_number(decimals=2)` is
            # how prose names a method, so it's checked as one
            if name in self.api.methods and (
                p := bind_problem(getattr(self.api.gt, name), node, method=True)
            ):
                self.flag(node, f"`GT.{name}`: {p}")
            return
        if name in self.api.methods:
            if name in self.api.shared and not self.is_gt(f.value):
                return
            if p := bind_problem(getattr(self.api.gt, name), node, method=True):
                self.flag(node, f"`GT.{name}`: {p}")
        elif GT_LIKE.fullmatch(name):
            self.flag(node, f"GT has no method `{name}`")

    def visit_Name(self, node: ast.Name) -> None:
        # A method named in prose without a call: `fmt_numbr`
        if (
            self.prose
            and GT_LIKE.fullmatch(node.id)
            and node.id not in self.api.methods
            and node.id not in self.local
        ):
            self.flag(node, f"GT has no method `{node.id}`")

    def name_call(self, node: ast.Call, name: str) -> None:
        if name in self.local:
            return
        if name == "GT":
            if p := bind_problem(self.api.gt, node, method=False):
                self.flag(node, f"`GT()`: {p}")
        elif name in self.api.exports:
            obj = getattr(self.api.pkg, name)
            if callable(obj) and (p := bind_problem(obj, node, method=False)):
                self.flag(node, f"`{name}()`: {p}")
        elif self.prose and GT_LIKE.fullmatch(name):
            # `fmt_number(decimals=2)` in prose means the GT method
            if name not in self.api.methods:
                self.flag(node, f"GT has no method `{name}`")
            elif p := bind_problem(getattr(self.api.gt, name), node, method=True):
                self.flag(node, f"`GT.{name}`: {p}")


def _parse(code: str) -> tuple[ast.AST, int] | None:
    """The snippet's tree and how many lines were added before it, trying the forms skills
    show code in; None if none parses."""
    code = code.replace("…", "...")
    tries = [code, re.sub(r"^\s*>>> ?|^\s*\.\.\. ?", "", code, flags=re.M)]
    # A chain shown on its own: `.fmt_number(...)`, or lines of one: `  .tab_header(...)`
    tries += [f"_{t.lstrip()}" for t in tries if t.lstrip().startswith(".")]
    for shift, wrap in ((0, "{}"), (1, "(\n{}\n)")):
        for t in tries:
            try:
                return ast.parse(wrap.format(t)), shift
            except SyntaxError:
                continue
    return None


def check_code(api: API, code: str, prose: bool = False) -> list[tuple[int, str]] | None:
    """Problems in a snippet, by line; None if it doesn't parse."""
    parsed = _parse(code)
    if parsed is None:
        return None
    tree, shift = parsed
    checker = Checker(api, prose=prose)
    # Collect the snippet's own definitions first, so order doesn't matter
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            checker.local.add(node.name)
        elif isinstance(node, ast.Assign):
            checker.local.update(t.id for t in node.targets if isinstance(t, ast.Name))
    checker.visit(tree)
    # A name can be flagged twice (as a call and as a name); keep each problem once
    return list(dict.fromkeys((max(1, line - shift), p) for line, p in checker.problems))


def check_names(api: API, text: str) -> list[str]:
    """Problems with the GT names in text that doesn't parse."""
    out = []
    for m in re.finditer(r"\b(loc|style|vals)\.(\w+)", text):
        if not hasattr(api.spaces[m[1]], m[2]):
            out.append(f"`{m[1]}` has no `{m[2]}`")
    for m in re.finditer(r"(?<![\w.])(?:GT\.)?(" + GT_LIKE.pattern + r")\b", text):
        if m[1] not in api.methods:
            out.append(f"GT has no method `{m[1]}`")
    return out


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def check_file(api: API, path: Path, rel: str) -> list[Finding]:
    text = path.read_text(errors="replace")
    out: list[Finding] = []

    def add(line: int, code: str, problems, around: str = "") -> None:
        for p in problems:
            out.append(Finding(rel, line, code.strip()[:120], p, bool(WARNING.search(around))))

    if path.suffix == ".py":
        lines = text.splitlines()
        problems = check_code(api, text)
        for line, p in [(1, "doesn't parse")] if problems is None else problems:
            add(line, lines[line - 1] if line <= len(lines) else "", [p])
        return out

    prose = text
    for m in FENCE.finditer(text):
        prose = prose[: m.start()] + re.sub(r"[^\n]", " ", m[0]) + prose[m.end() :]
        if m[3].lower() not in CODE_LANGS:
            continue
        start = _line_of(text, m.start(4))
        lines = m[4].splitlines()
        problems = check_code(api, m[4])
        if problems is None:
            # Not Python, or not whole: check the names only
            for i, line in enumerate(lines):
                add(start + i, line, check_names(api, line))
            continue
        for line, p in problems:
            add(start + line - 1, lines[line - 1] if line <= len(lines) else "", [p])

    for m in INLINE.finditer(prose):
        code = m[1].strip()
        line = _line_of(text, m.start())
        problems = check_code(api, code, prose=True)
        found = check_names(api, code) if problems is None else [p for _, p in problems]
        # The sentence up to the span, which says whether it's named as a mistake
        start = max(prose.rfind(". ", 0, m.start()), prose.rfind("\n\n", 0, m.start()))
        add(line, code, found, around=prose[max(start, 0) : m.start()])
    return out


def check_skill(skill: Path) -> list[Finding]:
    api = API()
    findings = []
    for path in sorted(skill.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".py"):
            findings += check_file(api, path, path.relative_to(skill).as_posix())
    return findings


def _rerun_in_agent_env() -> None:
    sys.path.insert(0, str(REPO))
    from harness import console

    env = {**os.environ, **console.agent_env()}
    env.pop("VIRTUAL_ENV", None)
    proc = subprocess.run([str(console.AGENT_PYTHON), __file__, *sys.argv[1:]], env=env)
    raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args()
    try:
        import great_tables  # noqa: F401
    except ImportError:
        _rerun_in_agent_env()
    skill = args.skill.resolve()
    if not (skill / "SKILL.md").is_file():
        raise SystemExit(f"no SKILL.md in {args.skill}")
    findings = check_skill(skill)
    problems = [f for f in findings if not f.warned]
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        print(f"{args.skill}: checked against great-tables {API().version()}")
        for f in problems:
            print(f"{f.file}:{f.line}: {f.problem}\n    {f.code}")
        print(f"{len(problems)} problem{'s' * (len(problems) != 1)}")
        if warned := [f for f in findings if f.warned]:
            print("\nIn prose warning against them (check they're meant as mistakes):")
            for f in warned:
                print(f"{f.file}:{f.line}: {f.problem}\n    {f.code}")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
