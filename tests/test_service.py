"""Tests for the ML service. A tiny model is trained on the fly, so no real artifacts are needed (CI-friendly)."""
import importlib.util, json, os
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.isotonic import IsotonicRegression

from features import FEATURE_COLUMNS
from policy import DEFAULT_COST_PARAMS


def build_tiny_model(folder):
    rng = np.random.default_rng(0)
    n = 6000
    X = rng.random((n, len(FEATURE_COLUMNS))) * 100
    idx = {c: i for i, c in enumerate(FEATURE_COLUMNS)}
    X[:, idx["drains_account"]] = rng.integers(0, 2, n)
    X[:, idx["dest_was_empty"]] = rng.integers(0, 2, n)
    # fraud mostly when the account is drained into an empty destination
    y = ((X[:, idx["drains_account"]] == 1) & (X[:, idx["dest_was_empty"]] == 1) & (rng.random(n) < 0.9)).astype(int)
    m = lgb.LGBMClassifier(n_estimators=40, num_leaves=8, verbose=-1, random_state=1).fit(X, y)
    raw = m.booster_.predict(X)
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(raw, y)
    m.booster_.save_model(str(folder / "model.txt"))
    joblib.dump(cal, folder / "calibrator.joblib")
    (folder / "feature_schema.json").write_text(json.dumps(FEATURE_COLUMNS))
    (folder / "cost_params.json").write_text(json.dumps(DEFAULT_COST_PARAMS))
    (folder / "VERSION").write_text("test-v1")


SERVE_PY = Path(__file__).resolve().parent.parent / "serve.py"


def fresh_service(model_dir, name):
    """Load a separate copy of serve.py pointed at model_dir, so tests cannot interfere with each other."""
    old = os.environ.get("MODEL_DIR")
    os.environ["MODEL_DIR"] = str(model_dir)
    try:
        spec = importlib.util.spec_from_file_location(name, SERVE_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("MODEL_DIR", None)
        else:
            os.environ["MODEL_DIR"] = old
    return mod


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    folder = tmp_path_factory.mktemp("model")
    build_tiny_model(folder)
    with TestClient(fresh_service(folder, "serve_ok").app) as c:
        yield c


SUSPICIOUS = {"amount": 377127, "features": {"amount": 377127, "is_transfer": 1, "hour_of_day": 3,
              "oldbalanceOrg": 377127, "amount_to_balance": 1.0, "drains_account": 1,
              "oldbalanceDest": 0, "dest_was_empty": 1}}
NORMAL = {"amount": 2000, "features": {"amount": 2000, "is_transfer": 0, "hour_of_day": 14,
          "oldbalanceOrg": 500000, "amount_to_balance": 0.004, "drains_account": 0,
          "oldbalanceDest": 800000, "dest_was_empty": 0}}


def test_health_is_ready_after_the_model_loads(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_version": "test-v1"}


def test_health_is_503_when_there_is_no_model(tmp_path):
    with TestClient(fresh_service(tmp_path, "serve_empty").app) as c:      # empty folder = no model
        assert c.get("/health").status_code == 503
        assert c.post("/score", json=NORMAL).status_code == 503


def test_score_returns_the_agreed_contract(client):
    r = client.post("/score", json={**SUSPICIOUS, "transaction_id": "t-1"})
    assert r.status_code == 200
    b = r.json()
    assert 0.0 <= b["fraud_probability"] <= 1.0
    assert b["decision"] in ("APPROVE", "STEP_UP", "REVIEW", "DECLINE")
    assert set(b["expected_costs"]) == {"approve", "step_up", "review", "decline"}
    assert 1 <= len(b["top_factors"]) <= 10
    assert {"feature", "impact"} <= set(b["top_factors"][0])
    assert b["model_version"] == "test-v1" and b["transaction_id"] == "t-1"


def test_suspicious_scores_higher_than_normal(client):
    s = client.post("/score", json=SUSPICIOUS).json()
    n = client.post("/score", json=NORMAL).json()
    assert s["fraud_probability"] > n["fraud_probability"]
    assert s["decision"] != "APPROVE"
    assert n["decision"] == "APPROVE" and n["reasons"] == []


def test_decision_is_the_cheapest_action(client):
    b = client.post("/score", json=SUSPICIOUS).json()
    cheapest = min(b["expected_costs"], key=b["expected_costs"].get)
    assert b["decision"].lower() == cheapest or b["expected_costs"][b["decision"].lower()] == b["expected_costs"][cheapest]


def test_policy_in_the_request_changes_the_decision(client):
    base = client.post("/score", json=SUSPICIOUS).json()
    only_decline_is_free = {**SUSPICIOUS, "policy": {"false_decline_cost": 0, "review_cost": 10**9, "stepup_cost": 10**9}}
    assert client.post("/score", json=only_decline_is_free).json()["decision"] == "DECLINE"
    never_decline = {**SUSPICIOUS, "policy": {"false_decline_cost": 10**12}}
    assert client.post("/score", json=never_decline).json()["decision"] != "DECLINE"
    assert base["decision"] in ("STEP_UP", "REVIEW", "DECLINE")


def test_full_review_queue_removes_review(client):
    # a free, perfectly accurate review makes REVIEW the cheapest action, until the queue is full
    body = {**SUSPICIOUS, "policy": {"review_cost": 0, "review_accuracy": 1.0, "stepup_cost": 10**9, "review_capacity": 5}}
    assert client.post("/score", json={**body, "queue_length": 0}).json()["decision"] == "REVIEW"
    assert client.post("/score", json={**body, "queue_length": 5}).json()["decision"] != "REVIEW"


def test_missing_amount_is_a_400(client):
    r = client.post("/score", json={"features": {"is_transfer": 1}})
    assert r.status_code == 400 and r.json()["error"] == "amount_required"


def test_unknown_feature_name_is_a_400(client):
    r = client.post("/score", json={"amount": 100, "features": {"amount": 100, "not_a_feature": 1}})
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_features" and r.json()["unknown"] == ["not_a_feature"]


def test_wrong_types_are_a_400(client):
    r = client.post("/score", json={"amount": "lots", "features": {}})
    assert r.status_code == 400 and r.json()["error"] == "invalid_request"


def test_bad_policy_value_is_a_400(client):
    r = client.post("/score", json={**NORMAL, "policy": {"review_accuracy": 1.5}})
    assert r.status_code == 400


def test_schema_lists_features_and_default_policy(client):
    b = client.get("/schema").json()
    assert b["features"] == FEATURE_COLUMNS and "review_cost" in b["default_policy"]
