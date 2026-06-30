from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Activity, DecisionWeight, AlternativeScore, Decision, Metric
from services.decision_limits import MAX_DECISION_ALTERNATIVES, MAX_DECISION_METRICS
from services.robustness import (
    _renormalize_weights,
    build_decision_robustness,
    robustness_label,
)


def _db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _decision_with_options(db, scores=(90, 70), weights=(100,)):
    decision = Decision(query="Pick one", category="General")
    metric = Metric(name="Quality", category="Quality", higher_is_better=True)
    db.add_all([decision, metric])
    db.flush()
    # Create decision-level weight(s) — shared across all activities
    for w in weights:
        db.add(DecisionWeight(decision_id=decision.id, metric_id=metric.id, weight=w))
    activities = []
    for index, score in enumerate(scores):
        activity = Activity(
            name=f"Option {index + 1}", category="General", decision_id=decision.id
        )
        db.add(activity)
        db.flush()
        db.add(
            AlternativeScore(activity_id=activity.id, metric_id=metric.id, score=score)
        )
        activities.append(activity)
    db.commit()
    return decision, activities, metric


def test_robustness_schema_and_seed_determinism():
    db = _db()
    decision, activities, _metric = _decision_with_options(db)
    first = build_decision_robustness(decision.id, db, seed=7, simulations=100)
    second = build_decision_robustness(decision.id, db, seed=7, simulations=100)

    assert first == second
    assert first["method"] == "weighted_additive_monte_carlo"
    assert "WAVM" in first["method_description"]
    assert "not hypothesis testing" in first["method_description"]
    assert first["simulations"] == 100
    assert first["winner_id"] == activities[0].id
    assert first["winner_robustness_percent"] >= 95
    assert first["winner_retained_count"] == round(
        first["winner_robustness_percent"] / 100 * first["winner_retained_total"]
    )
    assert first["winner_retained_total"] == first["simulations"]
    assert first["weight_renormalization"]["applied"] is True
    assert first["score_perturbation"]["clipped_to"] == [0, 100]
    assert first["top_two"]["mean_difference_percentage_points"] == round(
        first["top_two"]["mean_difference"] * 100, 2
    )
    assert first["top_two"]["interval_95"]["method"] == "empirical_percentile"
    assert first["top_two"]["interval_95_percentage_points"]["lower"] == round(
        first["top_two"]["interval_95"]["lower"] * 100, 2
    )
    assert "confidence interval" not in str(first).lower()
    assert "p_value" not in str(first)
    db.close()


def test_single_alternative_returns_certain_rank_acceptability():
    db = _db()
    decision, activities, _metric = _decision_with_options(
        db, scores=(80,), weights=(100,)
    )
    robustness = build_decision_robustness(decision.id, db, seed=1)

    assert robustness["winner_id"] == activities[0].id
    assert robustness["winner_robustness_percent"] == 100.0
    assert robustness["winner_retained_count"] == robustness["simulations"]
    assert robustness["winner_changed_percent"] == 0.0
    assert robustness["top_two"] is None
    assert robustness["rank_acceptability"][0]["first_rank_percent"] == 100.0
    db.close()


def test_no_alternatives_returns_none():
    db = _db()
    decision = Decision(query="Empty", category="General")
    db.add(decision)
    db.commit()

    assert build_decision_robustness(decision.id, db) is None
    db.close()


def test_all_zero_weights_tie_first_rank_acceptability():
    db = _db()
    decision, _activities, _metric = _decision_with_options(
        db, scores=(80, 20), weights=(0,)
    )
    robustness = build_decision_robustness(decision.id, db, seed=2, simulations=100)

    assert [
        item["first_rank_percent"] for item in robustness["rank_acceptability"]
    ] == [
        100.0,
        100.0,
    ]
    assert robustness["winner_changed_percent"] == 0.0
    db.close()


def test_robustness_label_thresholds():
    assert robustness_label(95) == "Very High"
    assert robustness_label(85) == "High"
    assert robustness_label(70) == "Moderate"
    assert robustness_label(69.99) == "Low"


def test_weight_renormalization_preserves_positive_base_total():
    sampled = _renormalize_weights({1: 99.0, 2: 33.0}, {1: 80.0, 2: 40.0})

    assert round(sum(sampled.values()), 6) == 120.0


def test_weight_renormalization_preserves_base_total_with_caps():
    sampled = _renormalize_weights({1: 100.0, 2: 90.0}, {1: 100.0, 2: 100.0})

    assert sampled == {1: 100.0, 2: 100.0}
    assert round(sum(sampled.values()), 6) == 200.0


def test_weight_renormalization_noops_for_zero_totals():
    assert _renormalize_weights({1: 0.0}, {1: 0.0}) == {1: 0.0}


def test_robustness_workload_guard_returns_none():
    db = _db()
    decision = Decision(query="Large", category="General")
    db.add(decision)
    db.flush()
    metrics = []
    for index in range(MAX_DECISION_METRICS):
        metric = Metric(
            name=f"Metric {index}", category="General", higher_is_better=True
        )
        db.add(metric)
        db.flush()
        metrics.append(metric)

    # Create decision-level weights (one per metric)
    for metric in metrics:
        db.add(DecisionWeight(decision_id=decision.id, metric_id=metric.id, weight=50))
    for alt_index in range(MAX_DECISION_ALTERNATIVES + 1):
        activity = Activity(
            name=f"Option {alt_index}", category="General", decision_id=decision.id
        )
        db.add(activity)
        db.flush()
        for metric in metrics:
            db.add(
                AlternativeScore(activity_id=activity.id, metric_id=metric.id, score=50)
            )
    db.commit()

    assert build_decision_robustness(decision.id, db) is None
    db.close()
