"""A review agent built on Claude: it reads the package PDFs itself (text and scans) and returns findings.

The model sees only the package's PDFs (through the Read tool), a versioned prompt (``prompts/``) and the answer
schema; see ``claude_cli`` for caching and replay.
"""

from __future__ import annotations

import time
from pathlib import Path

from .. import config
from . import claude_cli
from .schema import AgentRun, Finding, Span

TASK = "Review the financial statements in this folder."


def answer_schema() -> dict:
    item = Finding.model_json_schema()
    item.pop("title", None)
    return {"type": "object", "properties": {"findings": {"type": "array", "items": item}}, "required": ["findings"]}


class LLMAgent:
    def __init__(self, name: str):
        spec = config.load("agents")["agents"][name]
        self.name, self.version = name, spec["version"]
        self.model = spec["model"]
        self.prompt_file = config.ROOT / spec["prompt"]
        self.budget = float(spec.get("max_budget_usd", 1.0))
        self.timeout = int(spec.get("timeout_s", 600))

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def review(self, folder: Path) -> AgentRun:
        start = time.perf_counter()
        files = sorted(folder.glob("*.pdf"))
        raw, key, replayed = claude_cli.ask(
            self.model, self.prompt_file.read_text(), TASK, answer_schema(), files, self.budget, self.timeout
        )
        error = claude_cli.failed(raw)
        findings = []
        for f in (raw.get("structured_output") or {}).get("findings", []):
            try:
                findings.append(Finding.model_validate(f))
            except ValueError:
                continue  # one malformed finding does not void the others
        u = claude_cli.usage(raw)
        span = Span(
            name=f"review {self.model}",
            kind="llm",
            started_ms=0.0,
            duration_ms=u["duration_ms"] or (time.perf_counter() - start) * 1000,
            input_tokens=u["input_tokens"],
            output_tokens=u["output_tokens"],
            cache_read_tokens=u["cache_read_tokens"],
            cost_usd=u["cost_usd"],
            model=self.model,
            status="ok" if error is None else "error",
            attributes={"cache_key": key, "replayed": replayed, "turns": u["turns"]},
        )
        return AgentRun(package=folder.name, agent=self.id, findings=findings, spans=[span], error=error)
