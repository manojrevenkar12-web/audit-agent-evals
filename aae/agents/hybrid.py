"""Rules where the text layer is readable, the model where it is not.

Most packages arrive as text PDFs, which the rules agent reads exactly and for free. Scans defeat it. The
hybrid runs the rules agent first and calls the model only for packages with a document the rules could not
read, so the model's cost and its own errors are confined to the packages that need it.
"""

from __future__ import annotations

from pathlib import Path

from .. import config
from .baseline import BaselineAgent
from .llm import LLMAgent
from .schema import AgentRun


class HybridAgent:
    def __init__(self, name: str):
        spec = config.load("agents")["agents"][name]
        self.name, self.version = name, spec["version"]
        self.rules = BaselineAgent(spec["rules"])
        self.model = LLMAgent(spec["model_agent"])

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def review(self, folder: Path) -> AgentRun:
        run = self.rules.review(folder)
        run.agent = self.id
        if run.pages_unreadable == 0 and run.error is None:
            return run
        llm = self.model.review(folder)
        unreadable = {
            s.attributes.get("file") for s in run.spans if s.kind == "extract" and s.attributes.get("unreadable")
        }
        # keep the rules' findings on documents they could read; take the model's on the rest
        kept = [f for f in run.findings if f.document not in unreadable]
        taken = [f for f in llm.findings if f.document in unreadable or not unreadable]
        return AgentRun(
            package=run.package,
            agent=self.id,
            findings=kept + taken,
            spans=run.spans + llm.spans,
            pages_read=run.pages_read + run.pages_unreadable,
            pages_unreadable=0,
            error=llm.error,
        )
