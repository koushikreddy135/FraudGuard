"""
FraudGuard retraining job with a cost-based PROMOTION GATE.

What it does
  1. Loads labelled transactions (in the real system these are analyst verdicts + outcomes).
  2. Keeps the NEWEST slice as a hold-out that no model trains or calibrates on.
  3. Trains a CANDIDATE model on everything older (LightGBM + isotonic calibration).
  4. Scores the hold-out with BOTH the live model and the candidate, runs the cost policy, and
     compares total expected cost (the same cost parameters the live policy uses).
  5. PROMOTES the candidate only if it passes the gates:
        - cost gate:         candidate total cost is lower than live by at least --min-improvement
        - calibration gate:  candidate's worst decile gap <= 5 percentage points (SRS requirement)
     Otherwise the live model stays. Every run is logged to registry/history.jsonl.

Folders
  --current   (default artifacts)   the LIVE model; serve.py reads this folder
  --registry  (default registry)    every candidate + archived live models, plus history.jsonl

Usage
  python retrain.py --csv "Fraud detection Dataset.csv" --simulate     # safe demo, touches nothing live
  python retrain.py --csv "Fraud detection Dataset.csv"                # real retrain vs artifacts/
  python retrain.py --csv ... --dry-run                                # evaluate only, never promote
  python retrain.py --rollback                                         # restore the previous live model

After a promotion, restart serve.py so it loads the new model.
"""
import argparse, json, shutil, sqlite3, time, warnings
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss

from features import build_features, FEATURE_COLUMNS, KEEP_TYPES
from policy import DEFAULT_COST_PARAMS, ACTIONS, SigmoidCalibrator, decide_batch, realized_cost

warnings.filterwarnings("ignore", category=UserWarning)

RAW_COLS = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
            "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud"]
MODEL_FILES = ["model.txt", "calibrator.joblib", "feature_schema.json", "feature_names.json", "cost_params.json", "metrics.json"]
MAX_DECILE_GAP_PP = 5.0


# ----------------------------------------------------------------------------- helpers
def hr(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def new_version(tag=""):
    return time.strftime("v%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}{tag}"


def load_modelling_data(csv, nrows):
    df = pd.read_csv(csv, nrows=nrows, usecols=RAW_COLS)
    df = df.sort_values("step", kind="stable").reset_index(drop=True)
    df = build_features(df)                       # history uses ALL types, earlier steps only
    return df[df.type.isin(KEEP_TYPES)].reset_index(drop=True)


def load_cost_params(model_dir):
    """The live policy = defaults overlaid with whatever the admin saved in cost_params.json."""
    c = dict(DEFAULT_COST_PARAMS)
    p = Path(model_dir) / "cost_params.json"
    if p.exists():
        c.update(json.loads(p.read_text()))
    return c


def read_version(model_dir):
    p = Path(model_dir) / "VERSION"
    return p.read_text().strip() if p.exists() else None


def install(src, dst):
    """Copy a model folder into place. VERSION is written last so a half-copied folder never looks complete."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for f in MODEL_FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    shutil.copy2(src / "VERSION", dst / "VERSION")


def log_history(registry, entry):
    registry.mkdir(parents=True, exist_ok=True)
    with open(registry / "history.jsonl", "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def read_history(registry):
    p = registry / "history.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def load_db_feedback(db_path, step_value):
    """Load admin-reviewed transactions from SQLite as labelled feedback rows."""
    p = Path(db_path)
    if not p.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT amount_cents, decision, ml_features
        FROM transactions
        WHERE decision IN ('MANUALLY_APPROVED', 'MANUALLY_DECLINED')
          AND ml_features IS NOT NULL
    """).fetchall()
    conn.close()
    records = []
    for row in rows:
        feats = json.loads(row["ml_features"])
        rec = {col: feats.get(col) for col in FEATURE_COLUMNS}
        rec["amount"] = row["amount_cents"] / 100.0
        rec["isFraud"] = 1 if row["decision"] == "MANUALLY_DECLINED" else 0
        rec["step"] = int(step_value)
        records.append(rec)
    return pd.DataFrame(records) if records else pd.DataFrame()


# ----------------------------------------------------------------------------- training
def fit_model(train, calib, trees, pos_weight, calibration="sigmoid"):
    m = lgb.LGBMClassifier(
        n_estimators=trees, learning_rate=0.05, max_depth=6, num_leaves=31,
        min_child_samples=100, reg_alpha=1.0, reg_lambda=5.0, min_child_weight=1.0,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.6,
        scale_pos_weight=pos_weight, n_jobs=-1, random_state=7, verbose=-1)
    m.fit(train[FEATURE_COLUMNS], train.isFraud.values)
    booster = m.booster_
    raw = booster.predict(calib[FEATURE_COLUMNS].to_numpy(np.float64))
    cal = (SigmoidCalibrator() if calibration == "sigmoid"
           else IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0))
    cal.fit(raw, calib.isFraud.values)
    return booster, cal


def train_on_pool(pool, trees, pos_weight, calibration="sigmoid"):
    """Older 70% of the pool trains; the recent 30% is split randomly into more training data and a
    calibration half, so the calibrator sees the same regime as the data closest to the future."""
    q = int(pool.step.quantile(0.70))
    early = pool[pool.step <= q]
    recent = pool[pool.step > q].sample(frac=1.0, random_state=7)
    half = len(recent) // 2
    train = pd.concat([early, recent.iloc[:half]])
    calib = recent.iloc[half:]
    if len(calib) == 0 or calib.isFraud.sum() < 20:
        print(f"WARNING: calibration slice has only {int(calib.isFraud.sum())} frauds; calibration will be noisy.")
    booster, cal = fit_model(train, calib, trees, pos_weight, calibration=calibration)
    info = {"trained_rows": int(len(train)), "trained_frauds": int(train.isFraud.sum()),
            "calibration_rows": int(len(calib)), "calibration_frauds": int(calib.isFraud.sum()),
            "data_until_step": int(pool.step.max())}
    return booster, cal, info


def predict(booster, cal, df):
    raw = booster.predict(df[FEATURE_COLUMNS].to_numpy(np.float64))
    return cal.predict(raw)


def evaluate(p, df, c):
    y, amt, step = df.isFraud.values, df.amount.values, df.step.values
    action = decide_batch(p, amt, step, c)
    total = float(realized_cost(action, y, amt, c).sum())
    mix = np.bincount(action, minlength=4) / len(df)
    t = pd.DataFrame({"p": p, "y": y})
    t["d"] = pd.qcut(t.p.rank(method="first"), 10, labels=False)
    gap = float((t.groupby("d").p.mean() - t.groupby("d").y.mean()).abs().max() * 100)
    return {"pr_auc": float(average_precision_score(y, p)), "brier": float(brier_score_loss(y, p)),
            "max_decile_gap_pp": gap, "total_cost": total, "mix": mix}


def save_model(folder, booster, cal, version, cost_params, meta):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(folder / "model.txt"))
    joblib.dump(cal, folder / "calibrator.joblib")
    (folder / "feature_schema.json").write_text(json.dumps(FEATURE_COLUMNS, indent=2))
    (folder / "cost_params.json").write_text(json.dumps(cost_params, indent=2))
    (folder / "metrics.json").write_text(json.dumps({"modelVersion": version, **meta}, indent=2, default=float))
    (folder / "VERSION").write_text(version)


def load_live(model_dir):
    d = Path(model_dir)
    model_text = (d / "model.txt").read_text(encoding="utf-8")
    return lgb.Booster(model_str=model_text), joblib.load(d / "calibrator.joblib")


# ----------------------------------------------------------------------------- rollback
def rollback(current, registry):
    promoted = [h["version"] for h in read_history(registry) if h.get("promoted")]
    dedup = []
    for v in promoted:                       # keep order, drop consecutive repeats
        if not dedup or dedup[-1] != v:
            dedup.append(v)
    live = read_version(current)
    if live in dedup:
        dedup = dedup[:dedup.index(live) + 1]
    if len(dedup) < 2:
        raise SystemExit("Nothing to roll back to: there is no earlier promoted model in the history.")
    target = dedup[-2]
    src = registry / target
    if not (src / "VERSION").exists():
        raise SystemExit(f"Archived model {target} is missing from {registry}.")
    install(src, current)
    log_history(registry, {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": "rollback",
                           "version": target, "promoted": True, "rolled_back_from": live})
    print(f"Rolled back: live model is now {target} (was {live}). Restart serve.py to load it.")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--nrows", type=int, default=None)
    ap.add_argument("--current", default="artifacts")
    ap.add_argument("--registry", default="registry")
    ap.add_argument("--holdout-frac", type=float, default=0.15, help="share of newest rows kept as hold-out")
    ap.add_argument("--min-improvement", type=float, default=0.01,
                    help="candidate must cut total cost by at least this fraction (0.01 = 1%%)")
    ap.add_argument("--trees", type=int, default=400)
    ap.add_argument("--pos-weight", type=float, default=10.0)
    ap.add_argument("--calibration", choices=["sigmoid", "isotonic"], default="sigmoid",
                    help="probability calibration method (sigmoid avoids hard 0/1 step collapses)")
    ap.add_argument("--db", default=None,
                    help="optional SQLite DB path to include admin-reviewed transactions in training")
    ap.add_argument("--simulate", action="store_true",
                    help="demo: build an OLD live model from older data, then retrain; uses sim_* folders")
    ap.add_argument("--sim-old-frac", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true", help="evaluate and report, never promote")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    current, registry = Path(args.current), Path(args.registry)
    if args.rollback:
        return rollback(current, registry)
    if not args.csv:
        ap.error("--csv is required (unless --rollback)")

    if args.simulate:                                   # never touch the real live folders
        current, registry = Path("sim_artifacts"), Path("sim_registry")
        for d in (current, registry):
            shutil.rmtree(d, ignore_errors=True)

    t0 = time.time()
    hr("1. LOAD LABELLED DATA")
    df = load_modelling_data(args.csv, args.nrows)
    print(f"modelling rows: {len(df):,}  frauds: {int(df.isFraud.sum()):,}  steps {df.step.min()}..{df.step.max()}")

    cut = int(df.step.quantile(1 - args.holdout_frac))
    pool, hold = df[df.step <= cut], df[df.step > cut]
    if args.db:
        fb = load_db_feedback(args.db, pool.step.max())
        if len(fb):
            pool = pd.concat([pool, fb], ignore_index=True)
            print(f"appended {len(fb):,} admin-reviewed feedback rows from {args.db}")
    if len(hold) == 0 or hold.isFraud.sum() < 10:
        raise SystemExit("Hold-out has too few frauds to compare models. Use more rows or a larger --holdout-frac.")
    print(f"training pool: steps {pool.step.min()}-{pool.step.max()} ({len(pool):,} rows, {int(pool.isFraud.sum()):,} frauds)")
    print(f"hold-out     : steps {hold.step.min()}-{hold.step.max()} ({len(hold):,} rows, {int(hold.isFraud.sum()):,} frauds)"
          "  <- newest data, never used for training or calibration")

    # ---- simulation: make an older live model first
    if args.simulate:
        hr("SIMULATION: deploying an older model trained on early data only")
        old_pool = pool[pool.step <= int(pool.step.quantile(args.sim_old_frac))]
        b, c_, info = train_on_pool(old_pool, args.trees, args.pos_weight, calibration=args.calibration)
        v_old = new_version("-old")
        tmp = registry / v_old
        save_model(tmp, b, c_, v_old, dict(DEFAULT_COST_PARAMS), {**info, "note": "simulated older model"})
        install(tmp, current)
        log_history(registry, {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": "simulated_baseline",
                               "version": v_old, "promoted": True})
        print(f"old live model {v_old} trained on {info['trained_rows']:,} rows up to step {info['data_until_step']}")

    # ---- live model
    cost_params = load_cost_params(current)
    live_version = read_version(current)
    live_meta = json.loads((current / "metrics.json").read_text()) if (current / "metrics.json").exists() else {}
    have_live = live_version is not None

    # ---- candidate
    hr("2. TRAIN CANDIDATE on all data before the hold-out")
    booster, cal, info = train_on_pool(pool, args.trees, args.pos_weight, calibration=args.calibration)
    cand_version = new_version()
    p_cand = predict(booster, cal, hold)
    r_cand = evaluate(p_cand, hold, cost_params)
    print(f"candidate {cand_version}: {info['trained_rows']:,} training rows, {info['trained_frauds']:,} frauds")

    # ---- compare
    hr("3. COMPARE ON THE HOLD-OUT (same cost parameters as the live policy)")
    r_live = None
    if have_live:
        seen = live_meta.get("data_until_step")
        if seen is None:
            print("NOTE: live model has no 'data_until_step' record (it came from train.py). If it was calibrated on\n"
                  "      rows inside this hold-out, the comparison may favour it. Use --simulate for a clean demo.")
        elif seen >= hold.step.min():
            print(f"WARNING: live model has seen data up to step {seen}, which overlaps the hold-out; comparison is biased.")
        lb, lc = load_live(current)
        r_live = evaluate(predict(lb, lc, hold), hold, cost_params)

    def fmt_mix(m):
        return " / ".join(f"{a[:3]} {x:.2%}" for a, x in zip(ACTIONS, m))
    rows = [("PR-AUC", "pr_auc", "{:.4f}"), ("Brier score", "brier", "{:.6f}"),
            ("Worst decile gap (pp)", "max_decile_gap_pp", "{:.3f}"), ("TOTAL EXPECTED COST", "total_cost", "{:,.0f}")]
    print(f"{'':26s}{'LIVE ' + (live_version or '(none)')[:22]:>30s}{'CANDIDATE':>20s}")
    for label, key, f in rows:
        lv = f.format(r_live[key]) if r_live else "-"
        print(f"{label:26s}{lv:>30s}{f.format(r_cand[key]):>20s}")
    print(f"{'decision mix':26s}{(fmt_mix(r_live['mix']) if r_live else '-'):>30s}")
    print(f"{'':26s}{'':>30s}{fmt_mix(r_cand['mix']):>20s}")

    # ---- gates
    hr("4. PROMOTION GATES")
    cal_ok = r_cand["max_decile_gap_pp"] <= MAX_DECILE_GAP_PP
    print(f"calibration gate : worst decile gap {r_cand['max_decile_gap_pp']:.3f} pp <= {MAX_DECILE_GAP_PP} pp ... {'PASS' if cal_ok else 'FAIL'}")
    if r_live:
        saving = (r_live["total_cost"] - r_cand["total_cost"]) / r_live["total_cost"]
        cost_ok = saving >= args.min_improvement
        print(f"cost gate        : candidate saves {saving:+.2%} (needs >= {args.min_improvement:.2%}) ... {'PASS' if cost_ok else 'FAIL'}")
    else:
        saving, cost_ok = None, True
        print("cost gate        : no live model yet, so the first valid model is adopted ... PASS")
    promote = cal_ok and cost_ok and not args.dry_run
    reason = ("dry run" if args.dry_run else "passed both gates" if promote
              else "calibration gate failed" if not cal_ok else "not cheaper than the live model by enough")

    # ---- act
    meta = {**info, "parent": live_version, "holdout_steps": [int(hold.step.min()), int(hold.step.max())],
            "holdout_total_cost": r_cand["total_cost"], "holdout_pr_auc": r_cand["pr_auc"],
            "holdout_brier": r_cand["brier"], "holdout_max_decile_gap_pp": r_cand["max_decile_gap_pp"],
            "promoted": promote}
    save_model(registry / cand_version, booster, cal, cand_version, cost_params, meta)

    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": "retrain", "version": cand_version,
             "promoted": promote, "reason": reason, "candidate_cost": r_cand["total_cost"],
             "live_version": live_version, "live_cost": r_live["total_cost"] if r_live else None,
             "saving": saving}
    if have_live and promote and live_version and not (registry / live_version).exists():
        install(current, registry / live_version)                      # archive the old live model first
        log_history(registry, {"time": entry["time"], "event": "baseline", "version": live_version, "promoted": True})
    if promote:
        install(registry / cand_version, current)
    log_history(registry, entry)

    hr("RESULT")
    if promote:
        print(f"PROMOTED {cand_version}  ({reason}).  Live model folder: {current.resolve()}")
        print("Restart serve.py so it loads the new model. Roll back any time with:  python retrain.py --rollback")
    else:
        print(f"NOT PROMOTED ({reason}). Live model stays {live_version}. Candidate kept in {registry / cand_version}")
    print(f"total time {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
