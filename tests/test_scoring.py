"""Tests for the scoring algorithm (decision flow)."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Decision, Activity, DecisionWeight, Metric, AlternativeScore
from services.scoring import (
    compute_alternative_fit_scores,
    filter_by_thresholds,
)


@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    yield session
    session.close()


def make_decision(db, query="Test decision?"):
    d = Decision(query=query, category="General")
    db.add(d)
    db.flush()
    return d


def make_metric(db, name, category="Financial"):
    m = Metric(name=name, category=category)
    db.add(m)
    db.flush()
    return m


def make_activity(db, name, decision_id):
    a = Activity(name=name, category="General", decision_id=decision_id)
    db.add(a)
    db.flush()
    return a


def test_basic_scoring(db):
    decision = make_decision(db)
    m1 = make_metric(db, "Cost")
    m2 = make_metric(db, "Quality")
    alt1 = make_activity(db, "Option A", decision.id)
    alt2 = make_activity(db, "Option B", decision.id)

    # Weights: Cost=80, Quality=60 (decision-level, shared across all activities)
    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m1.id, weight=80),
            DecisionWeight(decision_id=decision.id, metric_id=m2.id, weight=60),
        ]
    )
    db.flush()

    # Scores: Option A -> Cost=30, Quality=80; Option B -> Cost=70, Quality=40
    db.add_all(
        [
            AlternativeScore(activity_id=alt1.id, metric_id=m1.id, score=30),
            AlternativeScore(activity_id=alt1.id, metric_id=m2.id, score=80),
            AlternativeScore(activity_id=alt2.id, metric_id=m1.id, score=70),
            AlternativeScore(activity_id=alt2.id, metric_id=m2.id, score=40),
        ]
    )
    db.commit()

    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 2
    assert results[0]["activity_name"] == "Option B"
    assert results[1]["activity_name"] == "Option A"
    assert round(results[0]["fit_score"], 4) == 0.5714
    assert round(results[1]["fit_score"], 4) == 0.5143


def test_scores_are_direct_benefit_values(db):
    """Scores are treated as direct benefit-oriented values."""
    decision = make_decision(db)
    m = make_metric(db, "Cost")
    alt = make_activity(db, "Cheap", decision.id)
    db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
    db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=30))
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 1
    assert round(results[0]["fit_score"], 4) == 0.3000


def test_mixed_metric_scoring_uses_direct_benefit_values(db):
    """Multiple metrics use direct benefit scores."""
    decision = make_decision(db)
    m1 = make_metric(db, "Cost", category="Financial")
    m2 = make_metric(db, "Quality", category="Quality")
    m3 = make_metric(db, "Risk", category="Risk")
    alt1 = make_activity(db, "Option A", decision.id)
    alt2 = make_activity(db, "Option B", decision.id)

    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m1.id, weight=80),
            DecisionWeight(decision_id=decision.id, metric_id=m2.id, weight=60),
            DecisionWeight(decision_id=decision.id, metric_id=m3.id, weight=50),
        ]
    )
    db.flush()

    db.add_all(
        [
            AlternativeScore(activity_id=alt1.id, metric_id=m1.id, score=40),
            AlternativeScore(activity_id=alt1.id, metric_id=m2.id, score=80),
            AlternativeScore(activity_id=alt1.id, metric_id=m3.id, score=20),
            AlternativeScore(activity_id=alt2.id, metric_id=m1.id, score=80),
            AlternativeScore(activity_id=alt2.id, metric_id=m2.id, score=30),
            AlternativeScore(activity_id=alt2.id, metric_id=m3.id, score=70),
        ]
    )
    db.commit()

    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 2
    assert results[0]["activity_name"] == "Option B"
    assert round(results[0]["fit_score"], 4) == 0.6158
    assert round(results[1]["fit_score"], 4) == 0.4737


def test_all_low_cost_risk_scores_are_direct_values(db):
    """All scores are treated as benefit scores."""
    decision = make_decision(db)
    m1 = make_metric(db, "Cost")
    m2 = make_metric(db, "Risk")
    alt1 = make_activity(db, "Good", decision.id)
    alt2 = make_activity(db, "Bad", decision.id)
    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m1.id, weight=100),
            DecisionWeight(decision_id=decision.id, metric_id=m2.id, weight=100),
            AlternativeScore(activity_id=alt1.id, metric_id=m1.id, score=20),
            AlternativeScore(activity_id=alt1.id, metric_id=m2.id, score=30),
            AlternativeScore(activity_id=alt2.id, metric_id=m1.id, score=80),
            AlternativeScore(activity_id=alt2.id, metric_id=m2.id, score=90),
        ]
    )
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 2
    assert results[0]["activity_name"] == "Bad"
    assert round(results[0]["fit_score"], 4) == 0.8500
    assert round(results[1]["fit_score"], 4) == 0.2500


def test_boundary_scores(db):
    """Scores at 0 and 100 boundaries."""
    decision = make_decision(db)
    m1 = make_metric(db, "Cost")
    m2 = make_metric(db, "Quality")
    alt1 = make_activity(db, "Best", decision.id)
    alt2 = make_activity(db, "Worst", decision.id)
    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m1.id, weight=100),
            DecisionWeight(decision_id=decision.id, metric_id=m2.id, weight=100),
            AlternativeScore(activity_id=alt1.id, metric_id=m1.id, score=0),
            AlternativeScore(activity_id=alt1.id, metric_id=m2.id, score=100),
            AlternativeScore(activity_id=alt2.id, metric_id=m1.id, score=100),
            AlternativeScore(activity_id=alt2.id, metric_id=m2.id, score=0),
        ]
    )
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 2
    assert round(results[0]["fit_score"], 4) == 0.5
    assert round(results[1]["fit_score"], 4) == 0.5


def test_dimension_scores_use_direct_benefit_scores(db):
    """Dimension scores should use direct benefit-oriented scores."""
    from services.scoring import compute_dimension_scores

    decision = make_decision(db)
    m1 = make_metric(db, "Cost", category="Financial")
    m2 = make_metric(db, "Value", category="Financial")
    alt = make_activity(db, "Option", decision.id)
    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m1.id, weight=80),
            DecisionWeight(decision_id=decision.id, metric_id=m2.id, weight=60),
            AlternativeScore(activity_id=alt.id, metric_id=m1.id, score=30),
            AlternativeScore(activity_id=alt.id, metric_id=m2.id, score=80),
        ]
    )
    db.commit()

    dim_scores = compute_dimension_scores(decision.id, db)
    assert len(dim_scores) == 1
    fin = dim_scores[0]
    assert fin["dimension"] == "Financial"
    assert fin["score"] == 51.4


def test_missing_metric_row_still_scores_directly(db):
    """Missing metric metadata does not affect direct benefit scoring."""
    decision = make_decision(db)
    m = make_metric(db, "Cost")
    alt = make_activity(db, "Test", decision.id)
    fake_metric_id = 99999  # Does not exist in Metric table
    db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=80))
    db.add(DecisionWeight(decision_id=decision.id, metric_id=fake_metric_id, weight=60))
    db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=30))
    db.add(AlternativeScore(activity_id=alt.id, metric_id=fake_metric_id, score=80))
    db.commit()

    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 1
    assert round(results[0]["fit_score"], 4) == 0.5143


def test_perfect_score(db):
    decision = make_decision(db)
    m = make_metric(db, "Quality")
    alt = make_activity(db, "Perfect", decision.id)
    db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
    db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=100))
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 1
    assert results[0]["fit_score"] == 1.0


def test_zero_scores(db):
    decision = make_decision(db)
    m = make_metric(db, "Quality")
    alt = make_activity(db, "Zero", decision.id)
    db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
    db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=0))
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 1
    assert results[0]["fit_score"] == 0.0


def test_no_activities(db):
    decision = make_decision(db)
    results = compute_alternative_fit_scores(decision.id, db)
    assert results == []


def test_no_weights_skipped(db):
    decision = make_decision(db)
    m = make_metric(db, "Quality")
    alt = make_activity(db, "No Weights", decision.id)
    # No DecisionWeight
    db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=80))
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 0  # skipped because no weights


def test_sorting_order(db):
    decision = make_decision(db)
    m = make_metric(db, "Score")
    alt1 = make_activity(db, "Low", decision.id)
    alt2 = make_activity(db, "High", decision.id)
    db.add_all(
        [
            DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100),
            AlternativeScore(activity_id=alt1.id, metric_id=m.id, score=30),
            AlternativeScore(activity_id=alt2.id, metric_id=m.id, score=90),
        ]
    )
    db.commit()
    results = compute_alternative_fit_scores(decision.id, db)
    assert len(results) == 2
    assert results[0]["activity_name"] == "High"
    assert results[1]["activity_name"] == "Low"


# ── Threshold filtering tests ──


class TestFilterByThresholds:
    def test_all_pass(self, db):
        decision = make_decision(db)
        m = make_metric(db, "Cost")
        alt = make_activity(db, "Good Fit", decision.id)
        db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
        db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=80))
        decision.thresholds = json.dumps(
            [{"metric_id": m.id, "operator": ">=", "value": 60}]
        )
        db.commit()

        result = filter_by_thresholds(decision.id, db)
        assert result["all_passed"] is True
        assert len(result["passed"]) == 1
        assert len(result["failed"]) == 0

    def test_one_fails_one_passes(self, db):
        decision = make_decision(db)
        m = make_metric(db, "Cost")
        alt1 = make_activity(db, "Affordable", decision.id)
        alt2 = make_activity(db, "Poor Fit", decision.id)
        db.add_all(
            [
                DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100),
                AlternativeScore(activity_id=alt1.id, metric_id=m.id, score=80),
                AlternativeScore(activity_id=alt2.id, metric_id=m.id, score=30),
            ]
        )
        decision.thresholds = json.dumps(
            [{"metric_id": m.id, "operator": ">=", "value": 60}]
        )
        db.commit()

        result = filter_by_thresholds(decision.id, db)
        assert result["all_passed"] is False
        assert len(result["passed"]) == 1
        assert len(result["failed"]) == 1
        assert result["passed"][0]["activity_name"] == "Affordable"
        assert result["failed"][0]["activity_name"] == "Poor Fit"

    def test_all_fail(self, db):
        decision = make_decision(db)
        m = make_metric(db, "Cost")
        alt = make_activity(db, "Poor Fit", decision.id)
        db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
        db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=30))
        decision.thresholds = json.dumps(
            [{"metric_id": m.id, "operator": ">=", "value": 60}]
        )
        db.commit()

        result = filter_by_thresholds(decision.id, db)
        assert result["all_passed"] is False
        assert len(result["passed"]) == 0
        assert len(result["failed"]) == 1
        assert result["survivor_results"] == []

    def test_no_thresholds_all_pass(self, db):
        decision = make_decision(db)
        m = make_metric(db, "Quality")
        alt = make_activity(db, "Good", decision.id)
        db.add(DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100))
        db.add(AlternativeScore(activity_id=alt.id, metric_id=m.id, score=85))
        db.commit()

        result = filter_by_thresholds(decision.id, db)
        assert result["all_passed"] is True
        assert len(result["passed"]) == 1
        assert len(result["failed"]) == 0
        assert len(result["survivor_results"]) == 1

    def test_benefit_oriented_minimum_threshold(self, db):
        """Cost >= 30 with score 50 should pass; score 20 should fail."""
        decision = make_decision(db)
        m = make_metric(db, "Cost")
        alt_good = make_activity(db, "LowCost", decision.id)
        alt_bad = make_activity(db, "HighCost", decision.id)
        db.add_all(
            [
                DecisionWeight(decision_id=decision.id, metric_id=m.id, weight=100),
                AlternativeScore(activity_id=alt_good.id, metric_id=m.id, score=50),
                AlternativeScore(activity_id=alt_bad.id, metric_id=m.id, score=20),
            ]
        )
        decision.thresholds = json.dumps(
            [{"metric_id": m.id, "operator": ">=", "value": 30}]
        )
        db.commit()

        result = filter_by_thresholds(decision.id, db)
        assert result["all_passed"] is False
        assert len(result["passed"]) == 1
        assert result["passed"][0]["activity_name"] == "LowCost"
        assert len(result["failed"]) == 1
        assert result["failed"][0]["activity_name"] == "HighCost"
