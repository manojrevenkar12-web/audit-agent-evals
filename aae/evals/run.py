"""Run an agent over a split, then score its saved answers against the truth.

Answers are saved per package (``data/runs/<split>/<agent>/<package>.json``) before anything is scored, so a
score can be recomputed, a run resumed after a crash, and an old answer replayed against a new matcher.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .. import config
from ..agents import registry
from ..agents.schema import AgentRun
from .match import PackageResult, match
from .metrics import Counts, counts


def runs_dir(split: str, agent_id: str) -> Path:
    return config.DATA / "runs" / split / agent_id.replace("@", "_v")


def package_ids(split: str) -> list[str]:
    manifest = json.loads((config.DATA / split / "manifest.json").read_text())
    return [p["id"] for p in manifest["packages"]]


def _review_one(args: tuple[str, str, str]) -> str:
    name, split, pid = args
    agent = registry.get(name)
    out = runs_dir(split, agent.id) / f"{pid}.json"
    if out.exists():
        return pid
    try:
        run = agent.review(config.DATA / split / "packages" / pid)
    except Exception as e:  # an agent crash is an answer too: no findings, an error
        run = AgentRun(package=pid, agent=agent.id, findings=[], spans=[], error=f"{type(e).__name__}: {e}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(run.model_dump_json())
    tmp.replace(out)
    return pid


def run_agent(name: str, split: str, workers: int = 4, limit: int | None = None) -> Path:
    ids = package_ids(split)[:limit]
    jobs = [(name, split, pid) for pid in ids]
    if workers <= 1:
        for j in jobs:
            _review_one(j)
    else:
        with ProcessPoolExecutor(workers) as pool:
            list(pool.map(_review_one, jobs, chunksize=4))
    return runs_dir(split, registry.get(name).id)


def load_runs(split: str, agent_id: str) -> dict[str, AgentRun]:
    folder = runs_dir(split, agent_id)
    return {p.stem: AgentRun.model_validate_json(p.read_text()) for p in sorted(folder.glob("*.json"))}


def load_truth(split: str, pid: str) -> dict:
    return json.loads((config.DATA / split / "truth" / f"{pid}.json").read_text())


def score_runs(split: str, runs: dict[str, AgentRun]) -> tuple[list[PackageResult], Counts]:
    results = [match(load_truth(split, pid), run.findings) for pid, run in sorted(runs.items())]
    return results, counts(results)
