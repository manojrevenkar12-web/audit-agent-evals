"""Build an agent from its entry in config/agents.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .. import config
from .schema import AgentRun


class Agent(Protocol):
    name: str

    @property
    def id(self) -> str: ...

    def review(self, folder: Path) -> AgentRun: ...


def get(name: str) -> Agent:
    spec = config.load("agents")["agents"][name]
    if spec["kind"] == "rules":
        from .baseline import BaselineAgent

        return BaselineAgent(name)
    if spec["kind"] == "llm":
        from .llm import LLMAgent

        return LLMAgent(name)
    if spec["kind"] == "hybrid":
        from .hybrid import HybridAgent

        return HybridAgent(name)
    raise ValueError(f"unknown agent kind {spec['kind']}")


def names() -> list[str]:
    return list(config.load("agents")["agents"])
