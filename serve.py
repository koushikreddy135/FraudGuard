"""
FraudGuard ML service (internal only: the backend calls it, the browser never does).

Run:   python -m uvicorn serve:app --port 8000          (Swagger UI at /docs)
Env:   MODEL_DIR=artifacts  (default)

POST /score   one call = fraud probability + cost-based decision + explanation
  request  {"amount": 52000,
            "features": {"amount": 52000, "is_transfer": 1, ...},      # names listed in GET /schema, null = unknown
            "policy": {"review_cost": 40, ...},                        # optional: overrides the server's default cost policy
            "queue_length": 0,                                         # optional: analyst cases already waiting
            "transaction_id": "..."}                                   # optional: echoed back
  response {"fraud_probability": 0.31, "decision": "REVIEW",
            "expected_costs": {"approve": ..., "step_up": ..., "review": ..., "decline": ...},
            "top_factors": [{"feature": "amount", "impact": 0.42, "value": 52000}],
            "reasons": ["..."], "model_version": "..."}
GET  /health  ready only once the model is loaded (Kubernetes readiness probe) -> 200 / 503
GET  /schema  feature names + default policy
(POST /decide is kept as an alias of /score.)
"""
import json, os, warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import lightgbm as lgb
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from policy import DEFAULT_COST_PARAMS, decide_one
from backend.database import init_db
from backend.auth_routes import router as auth_router
from backend.customer_routes import router as customer_router
from backend.admin_routes import router as admin_router

warnings.filterwarnings("ignore", category=UserWarning)
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "artifacts"))
STATE = {"ready": False}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()                                 # Initialize SQLite auth database and schema
    load()                                    # runs once at startup, before the first request
    yield


app = FastAPI(title="FraudGuard ML & Authentication Service", version="1.0", lifespan=lifespan)

# Enable CORS for local dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Authentication & Portal Routers
app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(admin_router)


# API names (snake_case, like the rest of the plan)  ->  internal names used in policy.py
POLICY_KEYS = {
    "false_decline_cost": "falseDeclineCost",
    "fraud_loss_proportion": "fraudLossProportion",
    "review_cost": "reviewCost",
    "stepup_cost": "stepUpFrictionCost",
    "stepup_prevention_prob": "stepUpPreventionProb",
    "review_accuracy": "reviewAccuracy",
    "review_capacity": "reviewCapacityPerHour",
}
DECISION_KEYS = {"APPROVE": "approve", "STEP_UP": "step_up", "REVIEW": "review", "DECLINE": "decline"}

# Plain-English wording for the model's features (shown to the customer / analyst).
REASON_TEXT = {
    "amount_to_balance": "The transfer is a very large share of the account balance",
    "drains_account": "The transfer empties the whole account balance",
    "oldbalanceDest": "The receiving account had no money in it before this transfer",
    "dest_was_empty": "The receiving account was empty or new",
    "hour_of_day": "The transaction is happening at an unusual hour",
    "is_transfer": "Transfers are a higher-risk type of transaction",
    "oldbalanceOrg": "The account balance is in a range common in fraud cases",
    "amount": "The amount is unusually large",
}


def reason_for(feature: str) -> str:
    if feature in REASON_TEXT:
        return REASON_TEXT[feature]
    if feature.startswith("dest_"):
        return "The receiving account has unusual recent activity"
    if feature.startswith("orig_"):
        return "The sender's recent activity looks unusual"
    return f"Unusual value for {feature}"


# ----------------------------------------------------------------------------- request / response
class PolicyOverride(BaseModel):
    """Cost settings (the Admin Portal's policy document). Anything left out uses the server default."""
    model_config = ConfigDict(extra="forbid")
    false_decline_cost: Optional[float] = Field(None, ge=0, description="cost of declining a genuine customer")
    fraud_loss_proportion: Optional[float] = Field(None, ge=0, le=1, description="share of the amount lost if fraud gets through")
    review_cost: Optional[float] = Field(None, ge=0, description="cost of one analyst review")
    stepup_cost: Optional[float] = Field(None, ge=0, description="cost of the OTP friction for the customer")
    stepup_prevention_prob: Optional[float] = Field(None, ge=0, le=1, description="chance an OTP stops the fraud")
    review_accuracy: Optional[float] = Field(None, ge=0, le=1, description="chance the analyst gets it right")
    review_capacity: Optional[int] = Field(None, ge=0, description="max cases waiting before REVIEW is no longer offered")


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0, description="payment amount; if left out, features.amount is used")
    features: Dict[str, Optional[float]]
    policy: Optional[PolicyOverride] = None
    queue_length: int = Field(0, ge=0, description="analyst cases already waiting for review")


class TopFactor(BaseModel):
    feature: str
    impact: float
    value: Optional[float] = None


class ScoreResponse(BaseModel):
    transaction_id: Optional[str] = None
    fraud_probability: float
    decision: str
    expected_costs: Dict[str, float]
    top_factors: List[TopFactor]
    reasons: List[str]
    model_version: str


# ----------------------------------------------------------------------------- errors
@app.exception_handler(RequestValidationError)
async def bad_request(_: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "reason": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=400, content={"error": "invalid_request", "details": details})


def _error(status: int, code: str, message: str, **extra):
    return HTTPException(status, detail={"error": code, "message": message, **extra})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"error": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


# ----------------------------------------------------------------------------- model
def _vector(features: Dict[str, Optional[float]]) -> np.ndarray:
    """Fixed column order; missing values become NaN (LightGBM handles them)."""
    return np.array([[np.nan if features.get(f) is None else float(features[f])
                      for f in STATE["names"]]], dtype=np.float64)


def _predict(features: Dict[str, Optional[float]]):
    x = _vector(features)
    raw = STATE["booster"].predict(x)
    prob = float(STATE["calibrator"].predict(raw)[0])
    contrib = STATE["booster"].predict(x, pred_contrib=True)[0][:-1]       # last column is the baseline
    order = np.argsort(-np.abs(contrib))[:10]
    factors = [{"feature": STATE["names"][j], "impact": round(float(contrib[j]), 4),
                "value": None if np.isnan(x[0, j]) else round(float(x[0, j]), 4)} for j in order]
    return prob, factors                      # unrounded: decisions must use the exact probability


def load():
    try:
        schema = MODEL_DIR / "feature_schema.json"
        if not schema.exists():
            schema = MODEL_DIR / "feature_names.json"          # older artifacts folders
        STATE["names"] = json.loads(schema.read_text())
        STATE["booster"] = lgb.Booster(model_file=str(MODEL_DIR / "model.txt"))
        STATE["calibrator"] = joblib.load(MODEL_DIR / "calibrator.joblib")
        STATE["version"] = (MODEL_DIR / "VERSION").read_text().strip()
        cost = dict(DEFAULT_COST_PARAMS)
        if (MODEL_DIR / "cost_params.json").exists():
            cost.update(json.loads((MODEL_DIR / "cost_params.json").read_text()))
        STATE["cost"] = cost
        _predict({})                          # prove the model can score before taking traffic
        STATE["ready"] = True
    except Exception as e:                    # no usable model -> stay not ready (readiness probe fails)
        STATE["ready"] = False
        print("model load failed:", e)


def _require_ready():
    if not STATE["ready"]:
        raise _error(503, "model_not_ready", "the model is not loaded yet")


# ----------------------------------------------------------------------------- endpoints
@app.get("/health")
@app.get("/readyz", include_in_schema=False)
def health():
    """Kubernetes readiness probe: 200 only after the model has loaded and scored once."""
    if STATE["ready"]:
        return {"status": "ok", "model_version": STATE["version"]}
    return JSONResponse(status_code=503, content={"status": "loading"})


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "alive"}


@app.get("/schema")
def schema():
    _require_ready()
    default = {api: STATE["cost"][internal] for api, internal in POLICY_KEYS.items()}
    return {"features": STATE["names"], "default_policy": default,
            "decisions": list(DECISION_KEYS), "model_version": STATE["version"]}


@app.post("/score", response_model=ScoreResponse)
@app.post("/decide", response_model=ScoreResponse, include_in_schema=False)
def score(req: ScoreRequest):
    _require_ready()
    unknown = sorted(set(req.features) - set(STATE["names"]))
    if unknown:
        raise _error(400, "unknown_features", "these feature names are not in the model's schema (see GET /schema)",
                     unknown=unknown)
    amount = req.amount if req.amount is not None else req.features.get("amount")
    if amount is None or amount <= 0:
        raise _error(400, "amount_required", "send 'amount' (> 0), or features.amount")

    cost = dict(STATE["cost"])
    if req.policy:
        for api_key, value in req.policy.model_dump(exclude_none=True).items():
            cost[POLICY_KEYS[api_key]] = value

    prob, factors = _predict(req.features)
    action, costs = decide_one(prob, amount, cost, queue_length=req.queue_length)
    # Plain-English reasons only make sense when we are NOT simply approving.
    reasons = ([] if action == "APPROVE" else
               [reason_for(f["feature"]) for f in factors if f["impact"] > 0.2][:3])
    return {"transaction_id": req.transaction_id, "fraud_probability": round(prob, 6), "decision": action,
            "expected_costs": {DECISION_KEYS[k]: v for k, v in costs.items()},
            "top_factors": factors, "reasons": reasons, "model_version": STATE["version"]}


# Serve production frontend single-page application (SPA)
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Don't intercept API or docs routes
        if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Not Found")
