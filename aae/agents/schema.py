"""What every review agent returns, whatever it is built from."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FindingType = Literal["casting", "tie", "prior_year", "narrative", "missing_disclosure", "period"]


class Finding(BaseModel):
    """One issue, located the way a reviewer would point at it on the page."""

    type: FindingType
    document: str = Field(description="file name, e.g. jahresabschluss_2026.pdf")
    page: int | None = Field(default=None, ge=1)
    row_label: str | None = Field(default=None, description="the line item as printed, e.g. 'Sonstige Rückstellungen'")
    column: str | None = Field(default=None, description="the column header as printed, e.g. '31.12.2025 TEUR'")
    quote: str | None = Field(default=None, description="for text: the sentence or heading, or the missing disclosure")
    found_value: str | None = None
    expected_value: str | None = None
    explanation: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)


class Span(BaseModel):
    """One step of an agent run, for the trace store."""

    name: str
    kind: Literal["retrieve", "extract", "check", "llm", "tool", "other"] = "other"
    started_ms: float
    duration_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    status: Literal["ok", "error"] = "ok"
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)


class AgentRun(BaseModel):
    """An agent's answer for one package, with its trace."""

    package: str
    agent: str  # name@version
    findings: list[Finding]
    spans: list[Span]
    pages_read: int = 0
    pages_unreadable: int = 0
    error: str | None = None
