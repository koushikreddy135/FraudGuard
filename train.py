"""
FraudGuard ML pipeline: explore -> features -> temporal split -> LightGBM -> calibrate
-> SHAP -> cost-based decisions vs baselines -> save artifacts.

Usage:
    python train.py --csv PaySim.csv                    # full file
    python train.py --csv PaySim.csv --nrows 1000000    # quicker while developing
"""
import argparse, json, time, warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_curve, brier_score_loss, confusion_matrix
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

from features import build_features, FEATURE_COLUMNS, KEEP_TYPES
from policy import (DEFAULT_COST_PARAMS, ACTIONS, expected_costs, decide_batch, realized_cost)

warnings.filterwarnings("ignore", category=UserWarning)

RAW_COLS = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud"]


def hr(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def recall_at_fpr(y, score, fpr_target=0.01):
    fpr, tpr, _ = roc_curve(y, score)
    return float(tpr[fpr <= fpr_target].max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--nrows", type=int, default=None, help="read only the first N rows")
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--trees", type=int, default=400)
    ap.add_argument("--pos_weight", type=float, default=10.0)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ------------------------------------------------------------------ 1. load + explore
    hr("1. LOAD AND EXPLORE")
    df = pd.read_csv(args.csv, nrows=args.nrows, usecols=RAW_COLS)
    print(f"rows: {len(df):,}   steps: {df.step.min()}..{df.step.max()}")
    print(f"overall fraud rate: {df.isFraud.mean():.4%}")
    print("\nfraud by type:")
    print(df.groupby("type").isFraud.agg(rows="size", frauds="sum", rate="mean").to_string())
    print(f"\nunique nameOrig: {df.nameOrig.nunique():,}  ({df.nameOrig.nunique()/len(df):.1%} of rows)"
          "  <- near 100% means per-customer history is thin")
    print(f"unique nameDest: {df.nameDest.nunique():,}")
    fd = df[df.isFraud == 1]
    print(f"distinct destinations that received fraud: {fd.nameDest.nunique():,} of {len(fd):,} fraud rows")

    # ------------------------------------------------------------------ 2. features
    hr("2. FEATURES (computed from earlier steps only)")
    df = df.sort_values("step", kind="stable").reset_index(drop=True)
    df = build_features(df)
    df = df[df.type.isin(KEEP_TYPES)].reset_index(drop=True)
    print(f"modelling rows (TRANSFER + CASH_OUT): {len(df):,}   fraud rate {df.isFraud.mean():.4%}")

    # ------------------------------------------------------------------ 3. temporal split
    hr("3. TEMPORAL SPLIT")
    # Split by SHARE OF ROWS (70% / 15% / 15%), cut at step boundaries. PaySim has very uneven
    # volume per step, so cutting by step number can leave a tiny, all-fraud calibration slice.
    # Train on the EARLIER 70% of rows. Everything after that is "the future": it is split randomly
    # 50/50 into a calibration half and a test half, so both halves come from the same period and
    # have the same fraud rate (a purely sequential split gave calibration a 12x lower fraud rate
    # than test, which makes the calibrated probabilities wrong).
    train_end = int(df.step.quantile(0.70))
    tr = df[df.step <= train_end]
    future = df[df.step > train_end].sample(frac=1.0, random_state=7)
    half = len(future) // 2
    ca = future.iloc[:half].sort_values("step", kind="stable")
    te = future.iloc[half:].sort_values("step", kind="stable")
    if min(len(tr), len(ca), len(te)) == 0:
        raise SystemExit("A split is empty: the file covers too few distinct steps. Use more rows (--nrows).")
    for name, part in [("train", tr), ("calibration", ca), ("test", te)]:
        print(f"{name:12s} steps {part.step.min():>3}-{part.step.max():<3} rows {len(part):>9,}  frauds {int(part.isFraud.sum()):>6,}  ({part.isFraud.mean():.3%})")
    if te.isFraud.sum() < 20 or ca.isFraud.sum() < 20:
        print("WARNING: very few fraud rows in the calibration/test slice; results will be noisy. Use more rows.")
    if ca.isFraud.mean() > 0.2:
        print("WARNING: the calibration slice is mostly fraud, so probabilities will be badly inflated. Check the split.")

    Xtr, ytr = tr[FEATURE_COLUMNS], tr.isFraud.values
    Xca, yca = ca[FEATURE_COLUMNS], ca.isFraud.values
    Xte, yte = te[FEATURE_COLUMNS], te.isFraud.values

    # ------------------------------------------------------------------ 4. models
    hr("4. BASELINE (logistic regression) vs LIGHTGBM")
    def prep_lr(X):
        return np.log1p(X.fillna(0).clip(lower=0))       # log scale for heavy-tailed values
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=300, class_weight="balanced"))
    lr.fit(prep_lr(Xtr), ytr)
    p_lr = lr.predict_proba(prep_lr(Xte))[:, 1]

    model = lgb.LGBMClassifier(
        n_estimators=args.trees, learning_rate=0.05, num_leaves=31, min_child_samples=50,
        reg_lambda=5.0, min_child_weight=1.0,      # stops huge leaf values / saturated scores
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        scale_pos_weight=args.pos_weight, n_jobs=-1, random_state=7, verbose=-1)
    model.fit(Xtr, ytr)
    raw_te = model.predict_proba(Xte)[:, 1]
    raw_ca = model.predict_proba(Xca)[:, 1]

    metrics = {}
    for name, s in [("logistic_regression", p_lr), ("lightgbm_raw", raw_te)]:
        metrics[name] = {"pr_auc": float(average_precision_score(yte, s)),
                         "recall_at_1pct_fpr": recall_at_fpr(yte, s)}
        print(f"{name:20s} PR-AUC {metrics[name]['pr_auc']:.4f}   recall@1%FPR {metrics[name]['recall_at_1pct_fpr']:.4f}")
    print(f"(a model that is always 'not fraud' has accuracy {1 - yte.mean():.4%} -> that's why we use PR-AUC)")

    imp = pd.Series(model.booster_.feature_importance("gain"), index=FEATURE_COLUMNS).sort_values(ascending=False)
    print("\ntop features by gain:\n" + (imp / imp.sum()).head(10).round(3).to_string())

    # ------------------------------------------------------------------ 5. calibration + SHAP
    hr("5. CALIBRATION (isotonic, fitted on the calibration slice)")
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    cal.fit(raw_ca, yca)
    p_te = cal.predict(raw_te)
    print(f"Brier score  raw {brier_score_loss(yte, np.clip(raw_te,0,1)):.6f}  ->  calibrated {brier_score_loss(yte, p_te):.6f}")
    metrics["lightgbm_calibrated"] = {"pr_auc": float(average_precision_score(yte, p_te)),
                                      "brier": float(brier_score_loss(yte, p_te))}

    # Decile table (SRS 3.2.2.3.6: observed rate within 5 percentage points of mean predicted score)
    t = pd.DataFrame({"p": p_te, "y": yte})
    t["decile"] = pd.qcut(t.p.rank(method="first"), 10, labels=False) + 1
    dec = t.groupby("decile").agg(n=("y", "size"), mean_pred=("p", "mean"), observed=("y", "mean"))
    dec["abs_gap_pp"] = (dec.mean_pred - dec.observed).abs() * 100
    print("\nDecile table (test set):\n" + dec.round(5).to_string())
    print(f"max gap = {dec.abs_gap_pp.max():.3f} pp  (requirement: <= 5 pp)")
    top = t.nlargest(max(1, len(t) // 100), "p")
    print(f"top 1% by score: mean predicted {top.p.mean():.4f} vs observed fraud rate {top.y.mean():.4f}")

    # Confusion matrix for the slide: (a) at the threshold giving ~1% false positives, (b) at probability 0.5
    fpr, tpr, thr = roc_curve(yte, p_te)
    t1 = float(thr[fpr <= 0.01][-1])
    cm = {}
    for label, cut in [("at_1pct_fpr", t1), ("at_0.5", 0.5)]:
        tn, fp, fn, tp = confusion_matrix(yte, (p_te >= cut).astype(int), labels=[0, 1]).ravel()
        cm[label] = {"threshold": round(cut, 5), "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
                     "precision": round(float(tp / max(tp + fp, 1)), 4), "recall": round(float(tp / max(tp + fn, 1)), 4)}
        print(f"\nConfusion matrix, threshold {cut:.4f} ({label}):  TN {tn:,}  FP {fp:,}  FN {fn:,}  TP {tp:,}"
              f"   precision {cm[label]['precision']:.3f}  recall {cm[label]['recall']:.3f}")
    metrics["confusion_matrix"] = cm

    hr("WHY: the 3 riskiest test transactions (LightGBM feature contributions, same values as SHAP)")
    top_idx = np.argsort(-p_te)[:3]
    sv = model.booster_.predict(Xte.iloc[top_idx].to_numpy(np.float64), pred_contrib=True)[:, :-1]
    for row, i in enumerate(top_idx):
        order = np.argsort(-np.abs(sv[row]))[:10]
        print(f"\ntransaction (test row {i}): risk {p_te[i]:.4f}, amount {te.amount.iloc[i]:,.0f}, true label {yte[i]}")
        for j in order:
            print(f"   {FEATURE_COLUMNS[j]:22s} value {Xte.iloc[i, j]:>14.4g}   contribution {sv[row][j]:+.3f}")

    # ------------------------------------------------------------------ 6. cost-based decisions
    hr("6. COST-BASED DECISIONS vs SIMPLE POLICIES (test set)")
    c = DEFAULT_COST_PARAMS
    amt, step = te.amount.values, te.step.values
    n = len(te)

    def evaluate(action):
        cost = realized_cost(action, yte, amt, c)
        mix = np.bincount(action, minlength=4) / n
        return cost.sum(), mix

    rows = []
    for name, action in [
        ("approve everything", np.zeros(n, dtype=int)),
        ("fixed threshold 0.5 (decline/approve)", np.where(p_te >= 0.5, 3, 0)),
        ("fixed threshold 0.1 (decline/approve)", np.where(p_te >= 0.1, 3, 0)),
        ("COST-BASED (4 actions)", decide_batch(p_te, amt, step, c)),
    ]:
        total, mix = evaluate(action)
        rows.append({"policy": name, "total_cost": total, **{a: f"{m:.3%}" for a, m in zip(ACTIONS, mix)}})
    res = pd.DataFrame(rows)
    res["total_cost"] = res.total_cost.map(lambda v: f"{v:,.0f}")
    print(res.to_string(index=False))

    hr("Change ONE parameter and watch the decisions shift (falseDeclineCost)")
    sens = []
    for f in [0.1, 1, 10]:
        cc = {**c, "falseDeclineCost": c["falseDeclineCost"] * f}
        total, mix = evaluate(decide_batch(p_te, amt, step, cc))
        sens.append({"falseDeclineCost": f"{cc['falseDeclineCost']:,.0f}", "total_cost": f"{total:,.0f}",
                     **{a: f"{m:.3%}" for a, m in zip(ACTIONS, mix)}})
    print(pd.DataFrame(sens).to_string(index=False))

    # ------------------------------------------------------------------ 7. save artifacts
    hr("7. SAVING ARTIFACTS")
    version = time.strftime("v%Y%m%d-%H%M%S")
    model.booster_.save_model(str(out / "model.txt"))
    joblib.dump(cal, out / "calibrator.joblib")
    (out / "feature_schema.json").write_text(json.dumps(FEATURE_COLUMNS, indent=2))
    (out / "cost_params.json").write_text(json.dumps(DEFAULT_COST_PARAMS, indent=2))
    (out / "metrics.json").write_text(json.dumps(
        {"modelVersion": version, "train_steps": [int(tr.step.min()), int(tr.step.max())],
         "test_steps": [int(te.step.min()), int(te.step.max())], **metrics}, indent=2))
    (out / "VERSION").write_text(version)
    print(f"saved to {out.resolve()}  (model {version})   total time {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
