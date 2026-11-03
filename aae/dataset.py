"""Build a split of seeded-defect packages: PDFs for the agents, truth for the evaluator, kept apart.

data/<split>/packages/<package>/<document>.pdf   what an agent may read
data/<split>/truth/<package>.json                defects, decoys, locations; only aae.evals reads it
data/<split>/manifest.json                       package ids and the SHA-256 of every PDF
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from . import config
from .checks import footing
from .defects import plant
from .document import Package, build_package
from .ledger import generate_company
from .render import write


def _weighted(rng: random.Random, weights: dict) -> object:
    keys = list(weights)
    return rng.choices(keys, weights=[float(weights[k]) for k in keys])[0]


def make_package(seed: int, split: str) -> tuple[Package, dict]:
    cfg = config.load("dataset")
    rng = random.Random(f"{split}:{seed}")
    pkg = build_package(f"{split}-{seed}", generate_company(seed, cfg["fiscal_year"]))
    n = int(_weighted(rng, cfg["defects_per_package"]))  # type: ignore[arg-type]
    kinds = [str(_weighted(rng, cfg["defect_kinds"])) for _ in range(n)]
    restate = rng.random() < cfg["restatement_rate"]
    defects, decoys, restated = plant(pkg, rng, kinds, restate)
    pkg.documents[0].scanned = rng.random() < cfg["scanned_rate"]
    truth = {
        "package": pkg.id,
        "seed": seed,
        "company": pkg.company.name,
        "fiscal_year": pkg.company.fiscal_year,
        "documents": [{"id": d.id, "file": f"{d.id}.pdf", "scanned": d.scanned} for d in pkg.documents],
        "defects": [d.to_json() for d in defects],
        "decoys": [
            {"id": d.id, "kind": d.kind, "description": d.description, "locations": d.locations} for d in decoys
        ],
        "restated_rows": dict(sorted(restated.items())),
        "rounding_differences": _rounding_differences(pkg),
    }
    return pkg, truth


def _rounding_differences(pkg: Package) -> list[str]:
    """Totals whose shown lines do not add up exactly but within rounding: correct, and a trap for strict agents."""
    strict, real = set(), set()
    for doc in pkg.documents:
        strict |= {v.locations[0] for v in footing(doc, strict=True)}
        real |= {v.locations[0] for v in footing(doc)}
    return sorted(strict - real)


def build(split: str, limit: int | None = None) -> Path:
    cfg = config.load("dataset")["splits"][split]
    root = config.DATA / split
    (root / "packages").mkdir(parents=True, exist_ok=True)
    (root / "truth").mkdir(parents=True, exist_ok=True)
    manifest = {"split": split, "packages": []}
    count = cfg["packages"] if limit is None else min(limit, cfg["packages"])
    for i in range(count):
        seed = cfg["first_seed"] + i
        pkg, truth = make_package(seed, split)
        folder = root / "packages" / pkg.id
        placed = []
        for d in pkg.documents:
            placed += [p.to_json() for p in write(d, folder)]
        truth["placed"] = placed
        (root / "truth" / f"{pkg.id}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1))
        hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(folder.glob("*.pdf"))}
        manifest["packages"].append({"id": pkg.id, "files": hashes})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return root


__all__ = ["build", "make_package"]
