# FraudGuard ML service

Scores one payment: fraud probability -> cost of 4 actions -> cheapest action + reasons.
Internal only: the Node backend calls it; the browser never does.

## Commands (Windows, run in the project folder)
```
pip install -r requirements.txt

python train.py --csv "Fraud detection Dataset.csv" --nrows 15000000      # trains, prints results + confusion matrix, writes artifacts/
python make_demo_rows.py --csv "Fraud detection Dataset.csv" --nrows 15000000 --model-dir artifacts --out demo_rows.json
python -m pytest -q                                                       # 20 tests, no dataset needed
python -m uvicorn serve:app --port 8000                                   # Swagger at http://localhost:8000/docs
```
Use the same `--nrows` for train.py and make_demo_rows.py.

## API
**POST /score**
```json
{ "transaction_id": "t1", "amount": 52000,
  "features": { "amount": 52000, "is_transfer": 1, "oldbalanceOrg": 52000, "amount_to_balance": 1, "drains_account": 1 },
  "policy": { "review_cost": 200 },
  "queue_length": 0 }
```
Only `features` is required (plus `amount`, or `features.amount`). Missing features can be left out or `null`.
`policy` and `queue_length` are optional.
```json
{ "transaction_id": "t1", "fraud_probability": 0.97, "decision": "DECLINE",
  "expected_costs": { "approve": 50440, "step_up": 15132, "review": 2700, "decline": 150 },
  "top_factors": [ { "feature": "amount_to_balance", "impact": 4.69, "value": 1 } ],
  "reasons": [ "The transfer empties the whole account balance" ],
  "model_version": "v20261120-100346" }
```
`decision` is APPROVE, STEP_UP, REVIEW or DECLINE. `reasons` is empty on APPROVE.

**GET /health** 200 `{"status":"ok","model_version":...}` once the model is loaded, else 503 (use as readiness probe).
**GET /schema** feature names, default policy, decisions.
`POST /decide` still works as an alias of `/score`.

Errors are JSON: 400 `invalid_request`, `unknown_features`, `amount_required`; 503 `model_not_ready`.

## Policy fields (snake_case) and defaults
| field | default | meaning |
|---|---|---|
| false_decline_cost | 5000 | cost of declining a genuine customer |
| fraud_loss_proportion | 1.0 | share of the amount lost if fraud gets through |
| review_cost | 200 | cost of one analyst review |
| stepup_cost | 20 | cost of the OTP friction |
| stepup_prevention_prob | 0.70 | chance OTP stops the fraud |
| review_accuracy | 0.95 | chance the analyst is right |
| review_capacity | 50 | cases waiting before REVIEW is no longer offered |

## Cost formulas (policy.py)
- APPROVE = p x amount x fraud_loss_proportion
- DECLINE = (1 - p) x false_decline_cost
- STEP_UP = stepup_cost + p x (1 - stepup_prevention_prob) x amount x fraud_loss_proportion
- REVIEW = review_cost + p x (1 - review_accuracy) x amount x loss + (1 - p) x (1 - review_accuracy) x false_decline_cost

Cheapest wins. Tie order: APPROVE, STEP_UP, REVIEW, DECLINE. REVIEW is removed when `queue_length >= review_capacity`.

## Files
| File | What it does |
|---|---|
| features.py | the 22 features; `FEATURE_COLUMNS` is the contract with the backend |
| train.py | trains LightGBM + isotonic calibration, prints metrics + confusion matrix, writes `artifacts/` (incl. `feature_schema.json`) |
| policy.py | cost formulas and decision rule |
| serve.py | FastAPI service |
| make_demo_rows.py | `demo_rows.json`: held-out rows for the simulator buttons |
| tests/, conftest.py | pytest suite (run it in Jenkins) |
| retrain.py | retraining with promotion gate (extra, not in the plan) |
| replay_generator.py, mock_ingest_api.py | load-test tools (extra, not in the plan) |

## Be honest in the viva
- PaySim is synthetic; scores look better than real life.
- `newbalance*` columns are not used (not known at decision time).
- Cost parameters are set by hand, not learned.
- Demo rows are held-out test rows replayed into the live pipeline.
- Explanations use LightGBM feature contributions (same values as SHAP TreeExplainer).
