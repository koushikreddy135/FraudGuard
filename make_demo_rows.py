"""
Builds demo_rows.json for the "Simulate normal payment" / "Simulate suspicious payment" buttons.

The rows are HELD-OUT test rows (the model never trained or calibrated on them), already in the model's
feature format, so the backend can send them straight to POST /score. Be open about it in the viva:
"the model is trained on public data; the simulator replays held-out rows into the live pipeline."

    python make_demo_rows.py --csv "Fraud detection Dataset.csv" --nrows 15000000 --model-dir artifacts --out demo_rows.json

Use the SAME --nrows as your train.py run, so the held-out split is identical.
"""
import argparse, json, warnings
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from features import build_features, FEATURE_COLUMNS, KEEP_TYPES
from policy import DEFAULT_COST_PARAMS, ACTIONS, decide_batch, expected_costs

warnings.filterwarnings("ignore", category=UserWarning)
RAW_COLS = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud"]


def clean(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return float(v)          # full precision: rounding features can shift the model's score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--nrows", type=int, default=None)
    ap.add_argument("--model-dir", default="artifacts")
    ap.add_argument("--out", default="demo_rows.json")
    ap.add_argument("--n", type=int, default=25, help="rows per group")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    d = Path(args.model_dir)

    df = pd.read_csv(args.csv, nrows=args.nrows, usecols=RAW_COLS).sort_values("step", kind="stable").reset_index(drop=True)
    df = build_features(df)
    df = df[df.type.isin(KEEP_TYPES)].reset_index(drop=True)

    # same hold-out as train.py: earliest 70% trains; the later period is split randomly 50/50 (calibration / test)
    train_end = int(df.step.quantile(0.70))
    future = df[df.step > train_end].sample(frac=1.0, random_state=7)
    te = future.iloc[len(future) // 2:].sort_values("step", kind="stable")
    print(f"held-out test rows: {len(te):,}  (frauds: {int(te.isFraud.sum()):,})")

    booster = lgb.Booster(model_file=str(d / "model.txt"))
    cal = joblib.load(d / "calibrator.joblib")
    cost = dict(DEFAULT_COST_PARAMS)
    if (d / "cost_params.json").exists():
        cost.update(json.loads((d / "cost_params.json").read_text()))
    version = (d / "VERSION").read_text().strip() if (d / "VERSION").exists() else "unknown"

    p = cal.predict(booster.predict(te[FEATURE_COLUMNS].to_numpy(np.float64)))
    action = decide_batch(p, te.amount.values, te.step.values, cost)
    te = te.assign(p=p, action=action)
    rng = np.random.default_rng(args.seed)

    def pick(frame, k):
        frame = frame.iloc[rng.permutation(len(frame))[:k]]
        return [{"label": "fraud" if r.isFraud == 1 else "legit",
                 "amount": clean(r.amount),
                 "model_probability": round(float(r.p), 4),
                 "decision": ACTIONS[int(r.action)],
                 "features": {c: clean(getattr(r, c)) for c in FEATURE_COLUMNS}}
                for r in frame.itertuples()]

    out = {
        "note": "Held-out PaySim test rows in the model's feature format. The model is trained on public data; "
                "the simulator replays held-out rows into the live pipeline.",
        "model_version": version,
        "how_to_use": "POST /score with {\"amount\": row.amount, \"features\": row.features}",
        "normal": pick(te[(te.isFraud == 0) & (te.p < 0.01)], args.n),
        "suspicious": pick(te[(te.isFraud == 1) & (te.p >= 0.5)], args.n),
        "by_decision": {a: pick(te[te.action == i], 5) for i, a in enumerate(ACTIONS)},
    }
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"wrote {args.out}")
    print(f"  normal rows: {len(out['normal'])}   suspicious rows: {len(out['suspicious'])}")
    for a in ACTIONS:
        n_all = int((te.action == ACTIONS.index(a)).sum())
        print(f"  decision {a:8s}: {n_all:6,} test rows, {len(out['by_decision'][a])} saved")
    missing = [a for a in ACTIONS if not out["by_decision"][a]]
    if missing:
        print(f"NOTE: no held-out rows produce {', '.join(missing)} with the current cost settings. "
              "Your model is very confident, so mid-range probabilities are rare. "
              "Edit artifacts/cost_params.json (for example raise false_decline_cost) to see those decisions.")


if __name__ == "__main__":
    main()
