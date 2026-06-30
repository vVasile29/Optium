import random

from sqlalchemy.orm import Session

from models import Activity, ActivityWeight, AlternativeScore, Metric
from services.decision_limits import robustness_workload_allowed


DEFAULT_SIMULATIONS = 1000
MIN_SIMULATIONS = 100
MAX_SIMULATIONS = 5000
WEIGHT_MIN_FACTOR = 0.9
WEIGHT_MAX_FACTOR = 1.1
SCORE_MIN_DELTA = -5.0
SCORE_MAX_DELTA = 5.0
METHOD_DESCRIPTION = (
    "Monte Carlo sensitivity analysis on a weighted additive value model "
    "(WAVM); not hypothesis testing."
)


def robustness_label(percent: float) -> str:
    if percent >= 95:
        return "Very High"
    if percent >= 85:
        return "High"
    if percent >= 70:
        return "Moderate"
    return "Low"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _fit(
    metric_ids: list[int],
    weights: dict[int, float],
    scores: dict[int, float],
    higher_is_better: dict[int, bool],
) -> float:
    numerator = 0.0
    denominator = 0.0
    for metric_id in metric_ids:
        weight = _clamp(float(weights.get(metric_id, 0.0)))
        score = _clamp(float(scores.get(metric_id, 0.0)))
        effective_score = (
            score if higher_is_better.get(metric_id, True) else 100.0 - score
        )
        numerator += effective_score * weight
        denominator += weight
    return numerator / denominator / 100.0 if denominator > 0 else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _renormalize_weights(
    sampled_weights: dict[int, float], base_weights: dict[int, float]
) -> dict[int, float]:
    base_total = sum(_clamp(float(weight)) for weight in base_weights.values())
    clamped_weights = {
        metric_id: _clamp(float(weight))
        for metric_id, weight in sampled_weights.items()
    }
    sampled_total = sum(clamped_weights.values())
    if base_total <= 0 or sampled_total <= 0:
        return sampled_weights
    if base_total >= len(clamped_weights) * 100.0:
        return {metric_id: 100.0 for metric_id in clamped_weights}

    renormalized = dict.fromkeys(clamped_weights, 0.0)
    active_metric_ids = set(clamped_weights)
    remaining_total = base_total

    while active_metric_ids and remaining_total > 0:
        active_total = sum(
            clamped_weights[metric_id] for metric_id in active_metric_ids
        )
        if active_total <= 0:
            share = remaining_total / len(active_metric_ids)
            for metric_id in active_metric_ids:
                renormalized[metric_id] = min(100.0, share)
            break
        scale = remaining_total / active_total
        capped_metric_ids = {
            metric_id
            for metric_id in active_metric_ids
            if clamped_weights[metric_id] * scale >= 100.0
        }
        if not capped_metric_ids:
            for metric_id in active_metric_ids:
                renormalized[metric_id] = clamped_weights[metric_id] * scale
            remaining_total = 0.0
            break
        for metric_id in capped_metric_ids:
            renormalized[metric_id] = 100.0
        remaining_total -= len(capped_metric_ids) * 100.0
        active_metric_ids -= capped_metric_ids

    return {metric_id: _clamp(weight) for metric_id, weight in renormalized.items()}


def build_decision_robustness(
    decision_id: int,
    db: Session,
    *,
    activity_ids: list[int] | None = None,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int | None = None,
) -> dict | None:
    simulations = max(MIN_SIMULATIONS, min(MAX_SIMULATIONS, int(simulations)))
    query = (
        db.query(Activity)
        .filter(Activity.decision_id == decision_id)
        .order_by(Activity.id)
    )
    if activity_ids is not None:
        if not activity_ids:
            return None
        query = query.filter(Activity.id.in_(activity_ids))
    activities = query.all()
    if not activities:
        return None

    activity_ids_for_query = [activity.id for activity in activities]
    weights_by_activity: dict[int, dict[int, float]] = {
        activity.id: {} for activity in activities
    }
    scores_by_activity: dict[int, dict[int, float]] = {
        activity.id: {} for activity in activities
    }
    metric_ids_set: set[int] = set()
    for weight in (
        db.query(ActivityWeight)
        .filter(ActivityWeight.activity_id.in_(activity_ids_for_query))
        .all()
    ):
        weights_by_activity[weight.activity_id][weight.metric_id] = weight.weight
        metric_ids_set.add(weight.metric_id)
    for score in (
        db.query(AlternativeScore)
        .filter(AlternativeScore.activity_id.in_(activity_ids_for_query))
        .all()
    ):
        scores_by_activity[score.activity_id][score.metric_id] = score.score

    metric_ids = sorted(metric_ids_set)
    if not robustness_workload_allowed(len(activities), len(metric_ids)):
        return None
    metrics = (
        db.query(Metric).filter(Metric.id.in_(metric_ids)).all() if metric_ids else []
    )
    higher_is_better = {metric.id: metric.higher_is_better for metric in metrics}

    base_scores = {
        activity.id: _fit(
            metric_ids,
            weights_by_activity.get(activity.id, {}),
            scores_by_activity.get(activity.id, {}),
            higher_is_better,
        )
        for activity in activities
    }
    base_order = sorted(
        activities,
        key=lambda activity: (-base_scores[activity.id], activity.id),
    )
    base_rank = {activity.id: index for index, activity in enumerate(base_order)}
    base_winner = base_order[0]

    if len(activities) == 1:
        return _robustness_payload(
            simulations=simulations,
            seed=seed,
            winner=base_winner,
            winner_retained_count=simulations,
            winner_robustness_percent=100.0,
            winner_changed_percent=0.0,
            rank_acceptability=[
                {
                    "activity_id": base_winner.id,
                    "activity_name": base_winner.name,
                    "first_rank_count": simulations,
                    "first_rank_percent": 100.0,
                }
            ],
            top_two=None,
        )

    rng = random.Random(seed)
    first_rank_counts = {activity.id: 0 for activity in activities}
    winner_changed_count = 0
    differences = []
    runner_up = base_order[1]

    for _ in range(simulations):
        simulated_scores = {}
        for activity in activities:
            base_weights = weights_by_activity.get(activity.id, {})
            sampled_weights = {
                metric_id: _clamp(
                    float(weight) * rng.uniform(WEIGHT_MIN_FACTOR, WEIGHT_MAX_FACTOR)
                )
                for metric_id, weight in base_weights.items()
            }
            sampled_weights = _renormalize_weights(sampled_weights, base_weights)
            sampled_scores = {
                metric_id: _clamp(
                    float(score) + rng.uniform(SCORE_MIN_DELTA, SCORE_MAX_DELTA)
                )
                for metric_id, score in scores_by_activity.get(activity.id, {}).items()
            }
            simulated_scores[activity.id] = _fit(
                metric_ids, sampled_weights, sampled_scores, higher_is_better
            )

        top_score = max(simulated_scores.values())
        for activity in activities:
            if abs(simulated_scores[activity.id] - top_score) <= 1e-12:
                first_rank_counts[activity.id] += 1

        simulated_winner = min(
            activities,
            key=lambda activity: (
                -simulated_scores[activity.id],
                base_rank[activity.id],
                activity.id,
            ),
        )
        if simulated_winner.id != base_winner.id:
            winner_changed_count += 1
        differences.append(
            simulated_scores[base_winner.id] - simulated_scores[runner_up.id]
        )

    rank_acceptability = [
        {
            "activity_id": activity.id,
            "activity_name": activity.name,
            "first_rank_count": first_rank_counts[activity.id],
            "first_rank_percent": round(
                first_rank_counts[activity.id] / simulations * 100, 2
            ),
        }
        for activity in activities
    ]
    winner_robustness = next(
        item["first_rank_percent"]
        for item in rank_acceptability
        if item["activity_id"] == base_winner.id
    )
    top_two = {
        "winner_id": base_winner.id,
        "runner_up_id": runner_up.id,
        "mean_difference": round(sum(differences) / len(differences), 4),
        "mean_difference_percentage_points": round(
            sum(differences) / len(differences) * 100, 2
        ),
        "interval_95": {
            "lower": round(_percentile(differences, 0.025), 4),
            "upper": round(_percentile(differences, 0.975), 4),
            "method": "empirical_percentile",
        },
        "interval_95_percentage_points": {
            "lower": round(_percentile(differences, 0.025) * 100, 2),
            "upper": round(_percentile(differences, 0.975) * 100, 2),
            "method": "empirical_percentile",
        },
    }
    return _robustness_payload(
        simulations=simulations,
        seed=seed,
        winner=base_winner,
        winner_retained_count=first_rank_counts[base_winner.id],
        winner_robustness_percent=winner_robustness,
        winner_changed_percent=round(winner_changed_count / simulations * 100, 2),
        rank_acceptability=rank_acceptability,
        top_two=top_two,
    )


def _robustness_payload(
    *,
    simulations: int,
    seed: int | None,
    winner: Activity,
    winner_retained_count: int,
    winner_robustness_percent: float,
    winner_changed_percent: float,
    rank_acceptability: list[dict],
    top_two: dict | None,
) -> dict:
    return {
        "method": "weighted_additive_monte_carlo",
        "method_description": METHOD_DESCRIPTION,
        "simulations": simulations,
        "seed": seed,
        "weight_perturbation": {
            "type": "relative_uniform",
            "min_factor": WEIGHT_MIN_FACTOR,
            "max_factor": WEIGHT_MAX_FACTOR,
        },
        "score_perturbation": {
            "type": "absolute_uniform",
            "min_delta": SCORE_MIN_DELTA,
            "max_delta": SCORE_MAX_DELTA,
            "clipped_to": [0, 100],
        },
        "weight_renormalization": {
            "applied": True,
            "scope": "per_alternative",
            "target": "base_total_weight",
            "when": "after perturbation and clipping when base and sampled totals are positive",
            "zero_total_behavior": "no-op when base or sampled total is zero",
        },
        "winner_id": winner.id,
        "winner_name": winner.name,
        "winner_retained_count": winner_retained_count,
        "winner_retained_total": simulations,
        "winner_robustness_percent": round(winner_robustness_percent, 2),
        "winner_changed_percent": round(winner_changed_percent, 2),
        "robustness_label": robustness_label(winner_robustness_percent),
        "rank_acceptability": rank_acceptability,
        "top_two": top_two,
    }
