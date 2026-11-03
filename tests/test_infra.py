"""Policy checks on the OpenTofu configuration: retention matches config, writers cannot delete, data stays in the EU."""

import hcl2
import pytest

from aae import config

INFRA = config.ROOT / "infra"


def _clean(v):
    """python-hcl2 keeps string quotes; strip them so values compare as written."""
    if isinstance(v, dict):
        return {_clean(k): _clean(x) for k, x in v.items() if k not in ("__is_block__", "__comments__")}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1]
    return v


@pytest.fixture(scope="module")
def tf():
    out: dict = {"resource": {}, "variable": {}}
    for path in INFRA.glob("*.tf"):
        with open(path) as f:
            doc = _clean(hcl2.load(f))
        for block in doc.get("resource", []):
            for rtype, named in block.items():
                for name, body in named.items():
                    out["resource"].setdefault(rtype, {})[name] = body
        for block in doc.get("variable", []):
            for name, body in block.items():
                out["variable"][name] = body
    return out


def _default(tf, name):
    return tf["variable"][name]["default"]


def test_retention_matches_config(tf):
    t = config.load("traces")
    assert _default(tf, "hot_days") == t["clickhouse"]["hot_days"]
    assert _default(tf, "archive_keep_days") == t["archive"]["keep_days"]
    rules = tf["resource"]["google_storage_bucket"]["archive"]["lifecycle_rule"]
    deletes = [r for r in rules if r["action"][0]["type"] == "Delete"]
    assert len(deletes) == 1 and "archive_keep_days" in str(deletes[0]["condition"][0]["age"])


def test_buckets_are_private_and_uniform(tf):
    for name, b in tf["resource"]["google_storage_bucket"].items():
        assert b["public_access_prevention"] == "enforced", name
        assert b["uniform_bucket_level_access"] is True, name


def test_nobody_can_delete_archived_runs(tf):
    roles = [m["role"] for m in tf["resource"]["google_storage_bucket_iam_member"].values()]
    assert roles and all(r in ("roles/storage.objectCreator", "roles/storage.objectViewer") for r in roles)


def test_only_the_evaluator_reads_the_model_key(tf):
    members = [m["member"] for m in tf["resource"]["google_secret_manager_secret_iam_member"].values()]
    assert members == ["serviceAccount:${google_service_account.evaluator.email}"]


def test_api_never_writes_traces(tf):
    for kind in ("google_bigquery_dataset_iam_member", "google_storage_bucket_iam_member"):
        for name, m in tf["resource"][kind].items():
            if "api" in m["member"]:
                assert m["role"].endswith(("dataViewer", "objectViewer")), name


def test_data_stays_in_the_eu(tf):
    assert _default(tf, "region").startswith("europe-")
    assert tf["resource"]["google_bigquery_dataset"]["traces"]["location"] == "EU"


def test_hot_tables_use_the_generated_schemas_and_partitions(tf):
    t = tf["resource"]["google_bigquery_table"]["hot"]
    assert "bigquery/${each.key}.json" in t["schema"]
    assert t["time_partitioning"][0]["field"] == "day"
    assert t["require_partition_filter"] is True
