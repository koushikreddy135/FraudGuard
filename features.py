"""
Feature engineering for FraudGuard (PaySim data).

Every feature for a transaction is computed ONLY from transactions in EARLIER steps
(step = 1 hour). Rows in the same step never see each other, so nothing from the
"future" leaks into training. This is the same logic the live scoring worker must
follow when it reads aggregates from Redis.

We deliberately do NOT use newbalanceOrig / newbalanceDest: they are the result of the
transaction and would not be known at decision time.
"""
import numpy as np
import pandas as pd

KEEP_TYPES = ["TRANSFER", "CASH_OUT"]   # in PaySim, fraud only occurs in these types
WINDOWS = {"1h": 1, "24h": 24, "7d": 168}
START = pd.Timestamp("2026-01-01 00:00:00")  # step 1 -> START + 1 hour (used for replay)

FEATURE_COLUMNS = [
    # transaction itself (known at decision time)
    "amount", "is_transfer", "hour_of_day",
    "oldbalanceOrg", "amount_to_balance", "drains_account",
    "oldbalanceDest", "dest_was_empty",
    # sender history  (live: Redis keyed by customerId)
    "orig_cnt_1h", "orig_cnt_24h", "orig_cnt_7d", "orig_sum_24h",
    "orig_prior_cnt", "orig_hrs_since_last", "orig_amount_vs_mean",
    # receiver history (live: Redis keyed by merchantId / destination account)
    "dest_cnt_1h", "dest_cnt_24h", "dest_cnt_7d", "dest_sum_24h",
    "dest_prior_cnt", "dest_hrs_since_last", "dest_amount_vs_mean",
]



def _history_features(df: pd.DataFrame, key: str, prefix: str) -> pd.DataFrame:
    """Window counts/sums over strictly earlier steps for each row, per account `key`."""
    n = len(df)
    codes = pd.factorize(df[key])[0].astype(np.int64)
    step = df["step"].to_numpy(np.int64)
    amt = df["amount"].to_numpy(np.float64)

    K = 100_000                          # > max step + longest window
    comp = codes * K + step
    order = np.argsort(comp, kind="stable")
    comp_s, codes_s, step_s, amt_s = comp[order], codes[order], step[order], amt[order]
    cum = np.concatenate([[0.0], np.cumsum(amt_s)])

    hi = np.searchsorted(comp_s, comp_s, side="left")        # first row with same (account, step)
    lo_all = np.searchsorted(comp_s, codes_s * K, side="left")  # first row of this account

    out = {}
    for name, w in WINDOWS.items():
        lo = np.searchsorted(comp_s, codes_s * K + (step_s - w), side="left")
        out[f"{prefix}_cnt_{name}"] = (hi - lo).astype(np.float32)
        if name == "24h":
            out[f"{prefix}_sum_24h"] = (cum[hi] - cum[lo]).astype(np.float32)

    prior_cnt = hi - lo_all
    out[f"{prefix}_prior_cnt"] = prior_cnt.astype(np.float32)

    last_step = np.where(prior_cnt > 0, step_s[np.maximum(hi - 1, 0)], np.nan)
    out[f"{prefix}_hrs_since_last"] = (step_s - last_step).astype(np.float32)

    prior_sum = cum[hi] - cum[lo_all]
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_prior = np.where(prior_cnt > 0, prior_sum / prior_cnt, np.nan)
        out[f"{prefix}_amount_vs_mean"] = (amt_s / mean_prior).astype(np.float32)

    res = {}
    for k, v in out.items():
        arr = np.empty(n, dtype=np.float32)
        arr[order] = v
        res[k] = arr
    return pd.DataFrame(res, index=df.index)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """df must contain the raw PaySim columns. Returns df + FEATURE_COLUMNS + timestamp."""
    df = df.copy()
    # history is computed on ALL transaction types (a live system sees everything)
    hist_o = _history_features(df, "nameOrig", "orig")
    hist_d = _history_features(df, "nameDest", "dest")
    df = pd.concat([df, hist_o, hist_d], axis=1)

    df["is_transfer"] = (df["type"] == "TRANSFER").astype(np.int8)
    df["hour_of_day"] = (df["step"] % 24).astype(np.int8)
    df["amount_to_balance"] = (df["amount"] / (df["oldbalanceOrg"] + 1.0)).astype(np.float32)
    df["drains_account"] = (df["amount"] >= df["oldbalanceOrg"] - 0.01).astype(np.int8)
    df["dest_was_empty"] = (df["oldbalanceDest"] == 0).astype(np.int8)
    df["timestamp"] = START + pd.to_timedelta(df["step"], unit="h")
    return df
