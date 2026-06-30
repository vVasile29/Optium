import json
import logging
from sqlalchemy.orm import Session

from models import DecisionWeight


# ── Threshold-based elimination (Elimination by Aspects) ──


def filter_by_thresholds(decision_id: int, db: Session) -> dict:
    """Apply Elimination by Aspects filtering.

    Reads thresholds from Decision.thresholds JSON.
    Checks each activity's AlternativeScores against each threshold.

    Returns: {
        "passed": [...],
        "failed": [{"name": ..., "reason": ...}],
        "all_passed": True/False,
        "survivor_results": [...]  # compute_alternative_fit_scores on passed only
    }
    """
    from models import Activity, AlternativeScore, Decision, Metric

    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if not decision:
        return {"passed": [], "failed": [], "all_passed": True, "survivor_results": []}

    # Parse thresholds JSON
    thresholds = []
    if decision.thresholds:
        try:
            thresholds = json.loads(decision.thresholds)
        except (json.JSONDecodeError, TypeError):
            thresholds = []

    activities = db.query(Activity).filter(Activity.decision_id == decision_id).all()

    if not thresholds:
        # No thresholds applied — all pass, return all fit scores
        all_results = compute_alternative_fit_scores(decision_id, db)
        passed = [{"activity_id": a.id, "activity_name": a.name} for a in activities]
        return {
            "passed": passed,
            "failed": [],
            "all_passed": True,
            "survivor_results": all_results,
        }

    # Build metric lookup
    all_metrics = db.query(Metric).all()
    metric_map = {m.id: m for m in all_metrics}

    passed = []
    failed = []

    for activity in activities:
        # Get scores for this activity
        scores_map: dict[int, float] = {}
        for ascore in (
            db.query(AlternativeScore)
            .filter(AlternativeScore.activity_id == activity.id)
            .all()
        ):
            scores_map[ascore.metric_id] = ascore.score

        fail_reasons = []
        for t in thresholds:
            metric_id = t.get("metric_id")
            operator = t.get("operator", "<=")
            threshold_value = float(t.get("value", 0))

            # Validate threshold value — clamp with warning if out of range
            if threshold_value < 0.0 or threshold_value > 100.0:
                logging.warning(
                    "filter_by_thresholds: threshold value %s out of range for metric %s — clamped to 0-100",
                    threshold_value,
                    metric_id,
                )
                threshold_value = max(0.0, min(100.0, threshold_value))

            # Skip unknown metric_ids
            if metric_id not in metric_map:
                continue

            score = scores_map.get(metric_id)
            if score is None:
                # No score for this metric — fail
                metric_name = metric_map[metric_id].name
                fail_reasons.append(
                    f"No score available for {metric_name} (threshold: {operator} {threshold_value})"
                )
                continue

            # Clamp score to 0-100
            score = max(0.0, min(100.0, score))

            metric_name = metric_map[metric_id].name

            # Check threshold
            failed_check = False
            if operator == "<=" and not (score <= threshold_value):
                failed_check = True
            elif operator == ">=" and not (score >= threshold_value):
                failed_check = True
            elif operator == "<" and not (score < threshold_value):
                failed_check = True
            elif operator == ">" and not (score > threshold_value):
                failed_check = True

            if failed_check:
                fail_reasons.append(
                    f"{metric_name} ({score}) fails {operator} {threshold_value}"
                )

        if fail_reasons:
            failed.append(
                {
                    "activity_id": activity.id,
                    "activity_name": activity.name,
                    "reasons": fail_reasons,
                }
            )
        else:
            passed.append(
                {
                    "activity_id": activity.id,
                    "activity_name": activity.name,
                }
            )

    # Compute fit scores on survivors
    survivor_ids = [p["activity_id"] for p in passed]
    if survivor_ids:
        survivor_results = compute_alternative_fit_scores(decision_id, db)
        # Filter to only survivors (fit scores are already computed across all activities)
        survivor_results = [
            r for r in survivor_results if r["activity_id"] in survivor_ids
        ]
    else:
        survivor_results = []

    return {
        "passed": passed,
        "failed": failed,
        "all_passed": len(failed) == 0,
        "survivor_results": survivor_results,
    }


def compute_alternative_fit_scores(decision_id: int, db: Session) -> list[dict]:
    """Compute fit scores for alternative scoring (decision engine flow).

    Each alternative is an Activity. Each criterion is a Metric.
    Scores come from AlternativeScore table.
    Weights come from DecisionWeight table (decision-level, shared across all activities).

    Returns sorted list of {activity_id, activity_name, fit_score, weighted_score}.
    """
    from models import Activity, AlternativeScore, Metric

    activities = db.query(Activity).filter(Activity.decision_id == decision_id).all()
    if not activities:
        return []

    # Load decision-level weights (shared across all activities)
    decision_weights = (
        db.query(DecisionWeight).filter(DecisionWeight.decision_id == decision_id).all()
    )
    weights: dict[int, float] = {dw.metric_id: dw.weight for dw in decision_weights}
    if not weights:
        return []

    # Build higher_is_better map for metrics in the weights
    metric_ids = list(weights.keys())
    metrics = db.query(Metric).filter(Metric.id.in_(metric_ids)).all()
    higher_is_better_map = {m.id: m.higher_is_better for m in metrics}

    results = []
    for activity in activities:
        # Get scores for this activity
        scores: dict[int, float] = {}
        for ascore in (
            db.query(AlternativeScore)
            .filter(AlternativeScore.activity_id == activity.id)
            .all()
        ):
            scores[ascore.metric_id] = ascore.score

        numerator = 0.0
        denominator = 0.0
        weighted_scores = []

        for metric_id, weight in weights.items():
            score = scores.get(metric_id, 0.0)
            effective_score = (
                score if higher_is_better_map.get(metric_id, True) else (100.0 - score)
            )
            numerator += effective_score * weight
            denominator += weight
            weighted_scores.append(
                {
                    "metric_id": metric_id,
                    "score": score,
                    "weight": weight,
                }
            )

        fit = (numerator / denominator / 100.0) if denominator > 0 else 0.0
        results.append(
            {
                "activity_id": activity.id,
                "activity_name": activity.name,
                "fit_score": round(fit, 4),
                "fit_pct": round(fit * 100, 1),
                "weighted_scores": weighted_scores,
            }
        )

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return results


def compute_dimension_scores(decision_id: int, db: Session) -> list[dict]:
    """Group metric scores by dimension and compute weighted averages.

    Groups metrics by their category (dimension name like 'Financial', 'Quality', etc.)
    For each dimension, computes the weighted average of its metrics' scores.

    Returns: [
        {"dimension": "Financial", "score": 45.2, "metrics": [...], "metric_count": 2},
        ...
    ]
    """
    from models import Activity, AlternativeScore, Metric

    activities = db.query(Activity).filter(Activity.decision_id == decision_id).all()
    if not activities:
        return []

    # Get decision-level weights
    decision_weights = (
        db.query(DecisionWeight).filter(DecisionWeight.decision_id == decision_id).all()
    )
    weights: dict[int, float] = {dw.metric_id: dw.weight for dw in decision_weights}

    if not weights:
        return []

    # Get metric-to-dimension mapping and higher_is_better map
    metric_ids = list(weights.keys())
    metrics = db.query(Metric).filter(Metric.id.in_(metric_ids)).all()
    metric_category: dict[int, str] = {m.id: m.category for m in metrics}
    higher_is_better_map: dict[int, bool] = {m.id: m.higher_is_better for m in metrics}

    # Get scores for each activity (we'll average across activities for diagnose mode
    # where there's typically just one activity)
    activity_scores: dict[int, dict[int, float]] = {}
    for act in activities:
        scores: dict[int, float] = {}
        for ascore in (
            db.query(AlternativeScore)
            .filter(AlternativeScore.activity_id == act.id)
            .all()
        ):
            scores[ascore.metric_id] = ascore.score
        activity_scores[act.id] = scores

    # Group by dimension
    dim_groups: dict[str, list[dict]] = {}
    for metric_id in metric_ids:
        cat = metric_category.get(metric_id, "General")
        if cat not in dim_groups:
            dim_groups[cat] = []
        # Average score across all activities
        scores_list = []
        for act in activities:
            s = activity_scores.get(act.id, {}).get(metric_id)
            if s is not None:
                scores_list.append(s)
        avg_score = sum(scores_list) / len(scores_list) if scores_list else 0.0
        effective_avg_score = (
            avg_score
            if higher_is_better_map.get(metric_id, True)
            else (100.0 - avg_score)
        )
        dim_groups[cat].append(
            {
                "metric_id": metric_id,
                "score": effective_avg_score,
                "weight": weights[metric_id],
            }
        )

    # Compute weighted average per dimension
    results = []
    for dim_name, metric_list in dim_groups.items():
        numerator = sum(m["score"] * m["weight"] for m in metric_list)
        denominator = sum(m["weight"] for m in metric_list)
        weighted_avg = (numerator / denominator) if denominator > 0 else 0.0
        results.append(
            {
                "dimension": dim_name,
                "score": round(weighted_avg, 1),
                "metrics": metric_list,
                "metric_count": len(metric_list),
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def gap_analysis(dimension_scores: list[dict]) -> dict:
    """Compare each dimension score to the overall average.

    Returns: {
        "strengths": [{"dimension": "Quality", "score": 85, "gap": 20}],
        "weaknesses": [{"dimension": "Cost", "score": 35, "gap": -30}],
        "overall_avg": 65.0,
        "balanced": False  # True if all gaps < 5
    }
    """
    if not dimension_scores:
        return {
            "strengths": [],
            "weaknesses": [],
            "overall_avg": 0.0,
            "balanced": True,
        }

    overall_avg = sum(d["score"] for d in dimension_scores) / len(dimension_scores)

    strengths = []
    weaknesses = []
    max_gap = 0.0

    for d in dimension_scores:
        gap = round(d["score"] - overall_avg, 1)
        d["gap"] = gap
        if abs(gap) > max_gap:
            max_gap = abs(gap)
        if gap > 0:
            strengths.append(
                {
                    "dimension": d["dimension"],
                    "score": d["score"],
                    "gap": gap,
                }
            )
        elif gap < 0:
            weaknesses.append(
                {
                    "dimension": d["dimension"],
                    "score": d["score"],
                    "gap": gap,
                }
            )

    strengths.sort(key=lambda x: x["gap"], reverse=True)
    weaknesses.sort(key=lambda x: x["gap"])

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "overall_avg": round(overall_avg, 1),
        "balanced": max_gap < 5.0,
    }
