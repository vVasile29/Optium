from sqlalchemy.orm import Session

from models import Activity, DecisionWeight, AlternativeScore, Decision, Metric
from services.robustness import build_decision_robustness
from services.scoring import (
    compute_alternative_fit_scores,
    filter_by_thresholds,
    sanitize_persisted_thresholds,
)


def _selected_metrics(decision_id: int, db: Session) -> list[Metric]:
    metric_ids = {
        dw.metric_id
        for dw in db.query(DecisionWeight)
        .filter(DecisionWeight.decision_id == decision_id)
        .all()
    }
    if not metric_ids:
        return []
    return db.query(Metric).filter(Metric.id.in_(metric_ids)).order_by(Metric.id).all()


def get_decision_export_data(decision_id: int, db: Session) -> dict | None:
    decision = db.query(Decision).filter(Decision.id == decision_id).first()
    if not decision:
        return None

    activities = (
        db.query(Activity)
        .filter(Activity.decision_id == decision_id)
        .order_by(Activity.id)
        .all()
    )
    metrics = _selected_metrics(decision_id, db)
    results = compute_alternative_fit_scores(decision_id, db)
    thresholds = sanitize_persisted_thresholds(decision_id, db)
    filter_result = filter_by_thresholds(decision_id, db) if thresholds else None
    result_basis = (
        filter_result.get("survivor_results", results) if filter_result else results
    )

    scores_by_activity = {}
    for activity in activities:
        scores_by_activity[activity.id] = {
            score.metric_id: score.score
            for score in db.query(AlternativeScore)
            .filter(AlternativeScore.activity_id == activity.id)
            .all()
        }

    weights_by_metric = {}
    for dw in (
        db.query(DecisionWeight).filter(DecisionWeight.decision_id == decision_id).all()
    ):
        weights_by_metric[dw.metric_id] = dw.weight

    rows = []
    for metric in metrics:
        rows.append(
            {
                "metric_id": metric.id,
                "metric_name": metric.name,
                "metric_desc": metric.description or "",
                "weight": weights_by_metric.get(metric.id, 50),
                "scores": {
                    activity.name: scores_by_activity.get(activity.id, {}).get(
                        metric.id, 0
                    )
                    for activity in activities
                },
            }
        )

    series = [
        {
            "name": activity.name,
            "scores": [
                scores_by_activity.get(activity.id, {}).get(metric.id, 0)
                for metric in metrics
            ],
        }
        for activity in activities
    ]

    return {
        "decision": {
            "id": decision.id,
            "query": decision.query,
            "mode": getattr(decision, "mode", None) or "choose",
            "created_at": decision.created_at,
            "category": decision.category,
        },
        "activities": [
            {"id": activity.id, "name": activity.name} for activity in activities
        ],
        "metrics": [
            {
                "id": metric.id,
                "name": metric.name,
                "description": metric.description or "",
            }
            for metric in metrics
        ],
        "results": results,
        "series": series,
        "robustness": build_decision_robustness(
            decision_id,
            db,
            activity_ids=[result["activity_id"] for result in result_basis],
        ),
        "significance": None,
        "rows": rows,
        "thresholds": thresholds,
        "filter_result": filter_result,
    }


def generate_markdown_brief(data: dict) -> str:
    decision = data["decision"]
    lines = [
        f"# Decision Brief: {decision['query']}",
        "",
        f"- Mode: {decision['mode']}",
        f"- Category: {decision.get('category') or 'General'}",
        f"- Created: {decision['created_at']}",
        "",
        "## Alternatives",
    ]
    for activity in data["activities"]:
        lines.append(f"- {activity['name']}")

    lines.extend(["", "## Ranking"])
    if data["results"]:
        for idx, result in enumerate(data["results"], start=1):
            lines.append(f"{idx}. {result['activity_name']} — {result['fit_pct']}%")
    else:
        lines.append("No scored results yet.")

    if data.get("thresholds"):
        lines.extend(["", "## Threshold Filters"])
        metric_names = {m["id"]: m["name"] for m in data["metrics"]}
        for threshold in data["thresholds"]:
            metric_name = metric_names.get(threshold.get("metric_id"), "Unknown metric")
            lines.append(
                f"- {metric_name} {threshold.get('operator', '>=')} {threshold.get('value')}"
            )

    robustness = data.get("robustness")
    if robustness:
        top_two = robustness.get("top_two")
        lines.extend(
            [
                "",
                "## Decision Robustness",
                robustness.get(
                    "method_description",
                    "Monte Carlo sensitivity analysis on a weighted additive value model (WAVM); not hypothesis testing.",
                ),
                "Sensitivity model: weights uniform ±10%, scores uniform ±5 points, values clipped [0,100], and sampled weights renormalized to each alternative's base total when possible.",
                f"- Winner: {robustness['winner_name']}",
                f"- Winner retained: {robustness['winner_robustness_percent']}% ({robustness.get('winner_retained_count', 0)} / {robustness.get('winner_retained_total', robustness['simulations'])} simulations; {robustness['robustness_label']})",
                f"- Winner changed: {robustness['winner_changed_percent']}% of simulations",
                f"- Simulations: {robustness['simulations']}",
            ]
        )
        if top_two:
            interval = top_two["interval_95"]
            lines.extend(
                [
                    f"- Mean weighted score advantage: {top_two.get('mean_difference_percentage_points', top_two['mean_difference'] * 100)} percentage points",
                    f"- 95% simulation interval: {top_two.get('interval_95_percentage_points', interval)['lower']} to {top_two.get('interval_95_percentage_points', interval)['upper']} percentage points",
                ]
            )
        lines.append("- Rank acceptability (Rank 1):")
        for item in robustness.get("rank_acceptability", []):
            lines.append(f"  - {item['activity_name']}: {item['first_rank_percent']}%")

    lines.extend(
        [
            "",
            "## Detailed Scores",
            "",
            "| Criterion | Weight | "
            + " | ".join(a["name"] for a in data["activities"])
            + " |",
        ]
    )
    lines.append("|---|---:|" + "---:|" * len(data["activities"]))
    for row in data["rows"]:
        scores = " | ".join(
            str(row["scores"].get(activity["name"], 0))
            for activity in data["activities"]
        )
        lines.append(f"| {row['metric_name']} | {row['weight']} | {scores} |")

    return "\n".join(lines) + "\n"
