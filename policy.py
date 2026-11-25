"""
Cost-based decision policy (the heart of FraudGuard).

For each transaction, with p = calibrated fraud probability and A = amount:

  APPROVE : p * A * fraudLossProportion
  DECLINE : (1 - p) * falseDeclineCost
  STEP_UP : stepUpFrictionCost + p * (1 - stepUpPreventionProb) * A * fraudLossProportion
  REVIEW  : reviewCost + p * (1 - reviewAccuracy) * A * fraudLossProportion
                       + (1 - p) * (1 - reviewAccuracy) * falseDeclineCost

Pick the cheapest. Ties go to the less disruptive action: APPROVE, STEP_UP, REVIEW, DECLINE.
If the review capacity for the hour is used up, REVIEW is removed and the next cheapest wins.

The numbers below are PLACEHOLDERS (they are business estimates, not learned). PaySim
amounts are large, so the costs are scaled to match. Tune them and justify them in your demo.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression


class SigmoidCalibrator:
    """Smooth Platt-scaling calibrator on logit(raw_prob) with a .predict() API matching IsotonicRegression."""

    def __init__(self):
        self._lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)

    @staticmethod
    def _to_logits(raw_scores):
        clipped = np.clip(np.asarray(raw_scores, dtype=np.float64), 1e-6, 1.0 - 1e-6)
        return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)

    def fit(self, raw_scores, y):
        self._lr.fit(self._to_logits(raw_scores), np.asarray(y, dtype=int))
        return self

    def predict(self, raw_scores):
        probs = self._lr.predict_proba(self._to_logits(raw_scores))[:, 1]
        return np.clip(probs, 0.0, 1.0)

ACTIONS = ["APPROVE", "STEP_UP", "REVIEW", "DECLINE"]   # order = tie-break order
A_, S_, R_, D_ = 0, 1, 2, 3

DEFAULT_COST_PARAMS = {
    "falseDeclineCost": 5000.0,      # cost of declining a genuine customer
    "fraudLossProportion": 1.0,      # share of the amount lost if fraud gets through
    "reviewCost": 200.0,             # cost of one analyst review
    "stepUpFrictionCost": 20.0,      # cost of annoying a customer with a challenge
    "stepUpPreventionProb": 0.70,    # chance a step-up stops the fraud
    "reviewAccuracy": 0.95,          # chance the analyst gets it right
    "reviewCapacityPerHour": 50,     # max reviews the team can do per step (hour)
}


def expected_costs(p, amount, c):
    """Returns an (n, 4) array of expected costs in the order APPROVE, STEP_UP, REVIEW, DECLINE."""
    p = np.asarray(p, dtype=np.float64)
    a = np.asarray(amount, dtype=np.float64)
    loss = a * c["fraudLossProportion"]
    approve = p * loss
    decline = (1 - p) * c["falseDeclineCost"]
    step_up = c["stepUpFrictionCost"] + p * (1 - c["stepUpPreventionProb"]) * loss
    review = (c["reviewCost"]
              + p * (1 - c["reviewAccuracy"]) * loss
              + (1 - p) * (1 - c["reviewAccuracy"]) * c["falseDeclineCost"])
    return np.column_stack([approve, step_up, review, decline])


def decide_batch(p, amount, step, c):
    """Vectorised decisions with the per-hour review capacity limit. Returns int array (0..3)."""
    costs = expected_costs(p, amount, c)
    action = costs.argmin(axis=1)                 # argmin keeps the first minimum -> tie rule
    cap = int(c["reviewCapacityPerHour"])
    step = np.asarray(step)
    rev_idx = np.where(action == R_)[0]
    if len(rev_idx) == 0:
        return action
    # only matters when a step has more REVIEWs than capacity
    order = np.argsort(step[rev_idx], kind="stable")
    rev_idx = rev_idx[order]
    steps_r = step[rev_idx]
    bounds = np.flatnonzero(np.diff(steps_r)) + 1
    for grp in np.split(rev_idx, bounds):
        if len(grp) <= cap:
            continue
        alt = costs[grp].copy()
        alt[:, R_] = np.inf
        best_alt = alt.argmin(axis=1)
        saving_lost = alt[np.arange(len(grp)), best_alt] - costs[grp, R_]
        keep = np.argsort(-saving_lost)[:cap]     # keep the reviews that save the most money
        drop = np.ones(len(grp), dtype=bool)
        drop[keep] = False
        action[grp[drop]] = best_alt[drop]
    return action


def decide_one(p, amount, c, queue_length=0):
    """Single transaction (what the Node scoring worker does). Returns (action, costs dict)."""
    costs = expected_costs([p], [amount], c)[0]
    avail = costs.copy()
    if queue_length >= c["reviewCapacityPerHour"]:
        avail[R_] = np.inf
    best = int(avail.argmin())
    return ACTIONS[best], dict(zip(ACTIONS, costs.round(4).tolist()))


def realized_cost(action, y, amount, c):
    """Expected cost of each chosen action GIVEN the true label (used to evaluate on test data)."""
    a = np.asarray(amount, dtype=np.float64)
    y = np.asarray(y)
    loss = a * c["fraudLossProportion"]
    fd = c["falseDeclineCost"]
    cost = np.zeros(len(a))
    m = action == A_
    cost[m] = np.where(y[m] == 1, loss[m], 0.0)
    m = action == S_
    cost[m] = c["stepUpFrictionCost"] + np.where(y[m] == 1, (1 - c["stepUpPreventionProb"]) * loss[m], 0.0)
    m = action == R_
    cost[m] = c["reviewCost"] + (1 - c["reviewAccuracy"]) * np.where(y[m] == 1, loss[m], fd)
    m = action == D_
    cost[m] = np.where(y[m] == 0, fd, 0.0)
    return cost
