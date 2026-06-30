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
          {robustness.winner_robustness_percent}% of {robustness.simulations}{" "}
          weighted additive simulations.
        </p>
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <span>Winner changed: {robustness.winner_changed_percent}%</span>
          <span>
            Weights: {robustness.weight_perturbation.min_factor}×–
            {robustness.weight_perturbation.max_factor}×
          </span>
          <span>
            Scores: {robustness.score_perturbation.min_delta} to +
            {robustness.score_perturbation.max_delta} points
          </span>
          {topTwo && (
            <span>
              Mean top-two advantage: {topTwo.mean_difference}
            </span>
          )}
          {topTwo && (
            <span>
              Top-two interval: {topTwo.interval_95.lower} to {topTwo.interval_95.upper}
            </span>
          )}
        </div>
        <div className="space-y-1 text-xs">
          <div className="font-medium">First-rank acceptability</div>
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
