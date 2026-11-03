"""Review API and queue: labels are appended, validated, counted per reviewer; agreement and golden export."""

import json

import pytest
from fastapi.testclient import TestClient

from aae import config
from aae.review import queue


@pytest.fixture()
def review_env(tmp_path, monkeypatch, unit_split, unit_truths):
    """A judged-items file and an empty review folder, isolated from the real ones."""
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "REPORTS", tmp_path / "reports")
    (tmp_path / "reports" / "judge").mkdir(parents=True)
    pid = next(iter(unit_truths))
    items = [
        {
            "agent": "a@1",
            "package": pid,
            "idx": 0,
            "finding": {"type": "narrative", "document": "x.pdf", "explanation": "e", "confidence": 0.9},
            "verdict": "unlocated",
            "label": "unknown",
            "judge_valid": True,
            "judge_confidence": 0.8,
            "judge_reason": "r",
            "error": None,
        },
        {
            "agent": "a@1",
            "package": pid,
            "idx": 1,
            "finding": {"type": "casting", "document": "x.pdf", "explanation": "e"},
            "verdict": "hit",
            "label": "valid",
            "judge_valid": False,
            "judge_confidence": 0.6,
            "judge_reason": "r",
            "error": None,
        },
        {
            "agent": "a@1",
            "package": pid,
            "idx": 2,
            "finding": {"type": "casting", "document": "x.pdf", "explanation": "e"},
            "verdict": "hit",
            "label": "valid",
            "judge_valid": True,
            "judge_confidence": 0.9,
            "judge_reason": "r",
            "error": None,
        },
    ]
    (tmp_path / "reports" / "judge" / "unit_items.jsonl").write_text("\n".join(json.dumps(i) for i in items) + "\n")
    return pid


def test_queue_holds_what_truth_cannot_settle_and_disagreements(review_env):
    assert queue.build("unit") == 2
    items = queue.load()
    assert items[0]["reason"].startswith("the judge says invalid")  # disagreement first
    assert {i["idx"] for i in items} == {0, 1}


def test_labels_are_validated_appended_and_latest_per_reviewer_counts(review_env):
    queue.build("unit")
    iid = queue.load()[0]["id"]
    with pytest.raises(ValueError):
        queue.add_label(iid, "ana", "maybe")
    with pytest.raises(ValueError):
        queue.add_label(iid, "  ", "valid")
    with pytest.raises(KeyError):
        queue.add_label("nope", "ana", "valid")
    queue.add_label(iid, "ana", "invalid")
    queue.add_label(iid, "ana", "valid")
    assert len(queue.all_labels()) == 2
    assert queue.latest_labels()[iid] == {"ana": "valid"}


def test_agreement_and_golden_export(review_env):
    queue.build("unit")
    ids = {i["idx"]: i["id"] for i in queue.load()}
    for iid, (x, y) in ((ids[0], ("valid", "valid")), (ids[1], ("valid", "invalid"))):
        queue.add_label(iid, "ana", x)
        queue.add_label(iid, "ben", y)
    ag = queue.agreement()
    assert ag["items"] == 2 and ag["agreement"] == 0.5
    rows = [json.loads(x) for x in queue.export_golden("unit").read_text().splitlines()]
    sources = {r["id"].rsplit(":", 1)[1]: (r["label"], r["source"]) for r in rows}
    assert sources["0"] == ("valid", "review")  # people settled what truth could not
    assert sources["2"] == ("valid", "seeded truth")
    assert "1" in sources and sources["1"][1] == "seeded truth"  # disagreement among people: truth stands


def test_api_queue_label_and_page_image(review_env, unit_split, monkeypatch):
    from aae import api

    queue.build("unit")
    c = TestClient(api.app)
    assert c.get("/api/health").json() == {"ok": True}
    open_items = c.get("/api/queue").json()
    iid = open_items[0]["id"]
    assert c.post(f"/api/queue/{iid}/labels", json={"reviewer": "ana", "label": "nonsense"}).status_code == 422
    assert c.post("/api/queue/missing/labels", json={"reviewer": "ana", "label": "valid"}).status_code == 404
    r = c.post(f"/api/queue/{iid}/labels", json={"reviewer": "ana", "label": "valid", "note": "checked"})
    assert r.status_code == 201
    done = c.get("/api/queue?status=all").json()
    assert next(i for i in done if i["id"] == iid)["labels"] == {"ana": "valid"}
    assert c.get("/api/judge/unit").status_code == 404
    assert c.get("/api/evals/..%2F..%2Fetc/passwd").status_code in (400, 404)


def test_page_images_render_and_names_are_checked(unit_split, unit_truths):
    from aae import api

    c = TestClient(api.app)
    pid = next(iter(unit_truths))
    r = c.get(f"/api/packages/{unit_split}/{pid}/jahresabschluss_2025/pages/1.png")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert c.get(f"/api/packages/{unit_split}/{pid}/jahresabschluss_2025/pages/99.png").status_code == 404
    assert c.get(f"/api/packages/{unit_split}/{pid}/..secret/pages/1.png").status_code == 400
