import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { RobustnessData } from "@/types";

export default function DecisionRobustnessCard({
  robustness,
}: {
  robustness: RobustnessData | null;
}) {
  if (!robustness) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">
          Not enough scored alternatives for robustness analysis.
        </CardContent>
      </Card>
    );
  }

  const topTwo = robustness.top_two;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">Decision Robustness</span>
          <Badge variant="secondary">{robustness.robustness_label}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {robustness.winner_name} ranked first in{" "}
          {robustness.winner_robustness_percent}% (
          {robustness.winner_retained_count} / {robustness.winner_retained_total}{" "}
          simulations).
        </p>
        <p className="text-xs text-muted-foreground">
          Method: {robustness.method_description}
        </p>
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <span>Winner changed: {robustness.winner_changed_percent}%</span>
          <span>Weights: uniform ±10%, renormalized per alternative</span>
          <span>Scores: uniform ±5 points, clipped [0,100]</span>
          {topTwo && (
            <span>
              Mean weighted score advantage:{" "}
              {topTwo.mean_difference_percentage_points} percentage points
            </span>
          )}
          {topTwo && (
            <span>
              95% simulation interval: {topTwo.interval_95_percentage_points.lower} to{" "}
              {topTwo.interval_95_percentage_points.upper} percentage points
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Sensitivity model: weights are sampled uniformly ±10%, scores uniformly ±5
          points, values are clipped to [0,100], and sampled weights are
          renormalized to each alternative&apos;s base total when possible.
        </p>
        <div className="space-y-1 text-xs">
          <div className="font-medium">Rank acceptability (Rank 1)</div>
          {robustness.rank_acceptability.map((item) => (
            <div key={item.activity_id} className="flex justify-between gap-3">
              <span className="truncate">{item.activity_name}</span>
              <span>{item.first_rank_percent}%</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
