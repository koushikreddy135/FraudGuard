"""Unit tests for the cost-based decision function (no model needed)."""
import numpy as np
import pytest

from policy import (ACTIONS, DEFAULT_COST_PARAMS, decide_batch, decide_one, expected_costs, realized_cost)

C = dict(DEFAULT_COST_PARAMS)


def test_declines_when_almost_certainly_fraud_and_amount_is_high():
    action, _ = decide_one(0.99, 80_000, C)
    assert action == "DECLINE"


def test_approves_when_almost_certainly_genuine():
    action, _ = decide_one(0.001, 5_000, C)
    assert action == "APPROVE"


def test_middle_probability_goes_to_review_or_step_up_not_approve():
    action, _ = decide_one(0.2, 100_000, C)
    assert action in ("STEP_UP", "REVIEW")


def test_expected_cost_formulas_by_hand():
    p, a = 0.3, 10_000
    ap, su, rv, de = expected_costs([p], [a], C)[0]
    assert ap == pytest.approx(p * a * C["fraudLossProportion"])
    assert de == pytest.approx((1 - p) * C["falseDeclineCost"])
    assert su == pytest.approx(C["stepUpFrictionCost"] + p * (1 - C["stepUpPreventionProb"]) * a * C["fraudLossProportion"])
    assert rv == pytest.approx(C["reviewCost"] + p * (1 - C["reviewAccuracy"]) * a * C["fraudLossProportion"]
                               + (1 - p) * (1 - C["reviewAccuracy"]) * C["falseDeclineCost"])


def test_tie_prefers_the_less_disruptive_action():
    # amount 0 makes APPROVE cost 0 and (with these settings) every other action costs >= 0: APPROVE must win a tie
    c = {**C, "stepUpFrictionCost": 0.0, "reviewCost": 0.0, "falseDeclineCost": 0.0, "reviewAccuracy": 1.0}
    action, costs = decide_one(0.5, 0.0, c)
    assert all(v == 0 for v in costs.values())
    assert action == "APPROVE"


def test_review_is_not_offered_when_the_queue_is_full():
    p, a = 0.2, 100_000
    open_queue, _ = decide_one(p, a, C, queue_length=0)
    full_queue, _ = decide_one(p, a, C, queue_length=C["reviewCapacityPerHour"])
    assert open_queue == "REVIEW"
    assert full_queue != "REVIEW"


def test_batch_respects_hourly_review_capacity():
    n = 200
    p = np.full(n, 0.2)
    amt = np.full(n, 100_000.0)
    step = np.ones(n, dtype=int)                       # all in the same hour
    c = {**C, "reviewCapacityPerHour": 10}
    action = decide_batch(p, amt, step, c)
    assert (action == ACTIONS.index("REVIEW")).sum() == 10


def test_realized_cost_charges_missed_fraud_and_false_declines():
    a = np.array([1000.0, 1000.0])
    y = np.array([1, 0])
    approve = np.array([0, 0])
    decline = np.array([3, 3])
    assert realized_cost(approve, y, a, C).tolist() == [1000.0 * C["fraudLossProportion"], 0.0]
    assert realized_cost(decline, y, a, C).tolist() == [0.0, C["falseDeclineCost"]]
