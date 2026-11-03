"""A review agent built on Claude: it reads the package PDFs itself (text and scans) and returns findings.

It runs the Claude Code CLI headless in a folder that holds only the package's PDFs, with the Read tool and
nothing else, a versioned prompt (``prompts/``), a JSON schema for the answer and a spending cap. Answers are
cached by prompt, model and the PDFs' hashes, so a rerun of the evaluation is free and replays exactly what the
model said; a cache miss with ``AAE_LLM=off`` is an error rather than a silent call.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .. import config
from .schema import AgentRun, Finding, Span

CACHE = config.DATA / "llm_cache"


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

    def cache_key(self, folder: Path) -> str:
        h = hashlib.sha256()
        h.update(self.model.encode())
        h.update(self.prompt_file.read_bytes())
        h.update(json.dumps(answer_schema(), sort_keys=True).encode())
        for pdf in sorted(folder.glob("*.pdf")):
            h.update(pdf.name.encode())
            h.update(hashlib.sha256(pdf.read_bytes()).digest())
        return h.hexdigest()[:24]

    def _call(self, folder: Path) -> dict:
        with tempfile.TemporaryDirectory(prefix="aae-review-") as tmp:
            for pdf in sorted(folder.glob("*.pdf")):
                shutil.copy(pdf, Path(tmp) / pdf.name)
            cmd = [
                "claude",
                "-p",
                "Review the financial statements in this folder.",
                "--model",
                self.model,
                "--output-format",
                "json",
                "--system-prompt",
                self.prompt_file.read_text(),
                "--tools",
                "Read",
                "--allowedTools",
                "Read",
                "--setting-sources",
                "",
                "--no-session-persistence",
                "--json-schema",
                json.dumps(answer_schema()),
                "--max-budget-usd",
                str(self.budget),
            ]
            p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=self.timeout)
            if p.returncode != 0 and not p.stdout.strip():
                raise RuntimeError(f"claude exited {p.returncode}: {p.stderr[-500:]}")
            return json.loads(p.stdout)

    def review(self, folder: Path) -> AgentRun:
        key = self.cache_key(folder)
        cached = CACHE / f"{key}.json"
        start = time.perf_counter()
        hit = cached.exists()
        if hit:
            raw = json.loads(cached.read_text())
        else:
            if os.environ.get("AAE_LLM", "on") == "off":
                raise RuntimeError(f"no cached answer for {folder.name} and AAE_LLM=off")
            raw = self._call(folder)
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(raw, ensure_ascii=False))
        usage = raw.get("usage", {})
        structured = raw.get("structured_output") or {}
        error = (
            None
            if raw.get("subtype", "success") == "success" and not raw.get("is_error")
            else str(raw.get("subtype") or raw.get("result"))[:300]
        )
        findings = []
        for f in structured.get("findings", []):
            try:
                findings.append(Finding.model_validate(f))
            except ValueError:
                continue
        span = Span(
            name=f"review {self.model}",
            kind="llm",
            started_ms=0.0,
            duration_ms=float(raw.get("duration_ms", (time.perf_counter() - start) * 1000)),
            input_tokens=int(usage.get("input_tokens", 0)) + int(usage.get("cache_creation_input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
            cost_usd=float(raw.get("total_cost_usd", 0.0)),
            model=self.model,
            status="ok" if error is None else "error",
            attributes={"cache_key": key, "replayed": hit, "turns": int(raw.get("num_turns", 0))},
        )
        return AgentRun(package=folder.name, agent=self.id, findings=findings, spans=[span], error=error)
