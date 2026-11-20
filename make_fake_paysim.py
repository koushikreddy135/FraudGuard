"""
Makes a SMALL FAKE file with PaySim's columns so you can test the pipeline before the real
download. The numbers are made up and the results mean nothing. Use the real PaySim for results.

    python make_fake_paysim.py fake_paysim.csv 300000
"""
import sys
import numpy as np
import pandas as pd

out = sys.argv[1] if len(sys.argv) > 1 else "fake_paysim.csv"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 300_000
rng = np.random.default_rng(1)

step = np.sort(rng.integers(1, 745, n))
typ = rng.choice(["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"], n, p=[.34, .08, .35, .22, .01])
orig = np.array([f"C{i}" for i in rng.integers(1, int(n * 0.9), n)])
dest = np.where(typ == "PAYMENT", [f"M{i}" for i in rng.integers(1, 5000, n)],
                [f"C{i}" for i in rng.integers(1, int(n * 0.5), n)])
amount = np.round(rng.lognormal(10.5, 1.3, n), 2)
oldO = np.round(rng.lognormal(11, 1.5, n), 2)

risky = np.isin(typ, ["TRANSFER", "CASH_OUT"])
mules = [f"C{i}" for i in rng.integers(1, 300, 40)]
score = (-9 + 2.0 * (amount > np.exp(12)) + 3.0 * (amount >= oldO) + 1.0 * (rng.random(n) < 0.02))
fraud = (risky & (rng.random(n) < 1 / (1 + np.exp(-score)))).astype(int)
fi = np.flatnonzero(fraud)
dest = dest.astype(object)
dest[fi] = rng.choice(mules, len(fi))              # fraud money goes to a few "mule" accounts
amount[fi] = np.minimum(oldO[fi], amount[fi] * 3)
oldD = np.where(rng.random(n) < 0.4, 0.0, np.round(rng.lognormal(11, 1.5, n), 2))

pd.DataFrame({"step": step, "type": typ, "amount": amount, "nameOrig": orig,
              "oldbalanceOrg": oldO, "newbalanceOrig": np.maximum(oldO - amount, 0),
              "nameDest": dest, "oldbalanceDest": oldD, "newbalanceDest": oldD + amount,
              "isFraud": fraud, "isFlaggedFraud": 0}).to_csv(out, index=False)
print(f"wrote {out}: {n:,} rows, fraud rate {fraud.mean():.3%}")
