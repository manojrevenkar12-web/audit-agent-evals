"""Agents read PDFs and their own config; they never see how packages are made or what is wrong with them."""

import ast
from pathlib import Path

from aae import config

AGENTS = config.ROOT / "aae" / "agents"
ALLOWED = {"aae.config", "aae.agents"}
FORBIDDEN_TEXT = ("truth", "dataset.yaml", "matching.yaml", "acceptable_locations", "placed")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: resolve against aae.agents
                base = ["aae", "agents"][: 3 - node.level] if node.level <= 2 else []
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if node.module is None:  # "from .. import config" imports aae.config
                out |= {f"{mod}.{a.name}" for a in node.names}
            else:
                out.add(mod)
    return {m for m in out if m.startswith("aae")}


def test_agents_import_only_config_and_agents():
    for path in AGENTS.glob("*.py"):
        bad = {m for m in _imports(path) if not any(m == a or m.startswith(a + ".") for a in ALLOWED)}
        assert not bad, f"{path.name} imports {bad}"


def test_agent_code_never_names_the_truth():
    for path in AGENTS.glob("*.py"):
        text = path.read_text()
        for word in FORBIDDEN_TEXT:
            assert word not in text, f"{path.name} mentions {word!r}"


def test_prompts_do_not_describe_the_generator():
    for path in (config.ROOT / "prompts").glob("*.md"):
        text = path.read_text().lower()
        for word in ("seed", "inject", "decoy", "synthetic", "planted"):
            assert word not in text, f"{path.name} mentions {word!r}"


def test_agent_folder_holds_only_pdfs(unit_split):
    for folder in (config.DATA / unit_split / "packages").iterdir():
        assert {p.suffix for p in folder.iterdir()} == {".pdf"}
