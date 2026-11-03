"""The review API: evaluation results, release decisions, the judge's calibration, and the human review queue.

Read-only except for labels, which are appended. Page images are rendered from the package PDFs on request so
a reviewer sees exactly what the agent read.
"""

from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .review import queue

SAFE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,80}$")
app = FastAPI(
    title="audit-agent-evals",
    version="1.0.0",
    description="Evaluation results, release decisions and the human review queue for audit review agents.",
)


def _safe(*parts: str) -> None:
    for p in parts:
        if not SAFE.match(p) or ".." in p:
            raise HTTPException(400, f"invalid name: {p!r}")


def _json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(404, f"{path.name} has not been produced yet")
    return json.loads(path.read_text())


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/evals")
def evals() -> list[dict]:
    out = []
    for p in sorted((config.REPORTS / "evals").glob("*/*.json")):
        r = json.loads(p.read_text())
        out.append(
            {
                "agent": r["agent"],
                "name": p.stem,
                "split": r["split"],
                "packages": r["packages"],
                "defects": r["defects"],
                "findings": r["findings"],
                "verdicts": r["verdicts"],
                "metrics": r["metrics"],
                "operational": r["operational"],
                "run_id": r.get("run_id"),
            }
        )
    return out


@app.get("/api/evals/{split}/{name}")
def eval_detail(split: str, name: str) -> dict:
    _safe(split, name)
    return _json(config.REPORTS / "evals" / split / f"{name}.json")


@app.get("/api/releases")
def releases() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((config.REPORTS / "releases").glob("*.json"))]


@app.get("/api/judge/{split}")
def judge(split: str) -> dict:
    _safe(split)
    return _json(config.REPORTS / "judge" / f"{split}.json")


@app.get("/api/queue")
def get_queue(status: Literal["open", "done", "all"] = "open") -> list[dict]:
    items = queue.load()
    return items if status == "all" else [i for i in items if i["status"] == status]


class LabelIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    label: Literal["valid", "invalid", "out_of_scope"]
    note: str = Field(default="", max_length=2000)


@app.post("/api/queue/{item_id}/labels", status_code=201)
def post_label(item_id: str, body: LabelIn) -> dict:
    try:
        return queue.add_label(item_id, body.reviewer, body.label, body.note)
    except KeyError:
        raise HTTPException(404, "no such queue item") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.get("/api/agreement")
def agreement() -> dict:
    return queue.agreement()


@lru_cache(maxsize=256)
def _page_png(path: str, page: int, mtime: float) -> bytes:
    doc = pdfium.PdfDocument(path)
    if not 1 <= page <= len(doc):
        raise IndexError(page)
    img = doc[page - 1].render(scale=1.5).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@app.get("/api/packages/{split}/{package}/{document}/pages/{page}.png")
def page_image(split: str, package: str, document: str, page: int) -> Response:
    _safe(split, package, document)
    pdf = config.DATA / split / "packages" / package / (document if document.endswith(".pdf") else f"{document}.pdf")
    if not pdf.exists():
        raise HTTPException(404, "no such document")
    try:
        png = _page_png(str(pdf), page, pdf.stat().st_mtime)
    except IndexError:
        raise HTTPException(404, "no such page") from None
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


_dist = config.ROOT / "web" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        return FileResponse(_dist / "index.html")
