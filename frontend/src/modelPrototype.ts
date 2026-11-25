type TreeNode = [feature: number, value: number, left: number, right: number];
type TrainingMetrics = { accuracy: number; balanced_accuracy: number; handover_average_precision: number };

export type PrototypeBundle = {
  schema_version: number;
  threshold: number;
  missing_slope_median: number;
  training_rows: number;
  unique_feature_vectors: number;
  conflicting_feature_vectors: number;
  class_counts: Record<string, number>;
  features: { name: string; unit: string }[];
  examples: { features: number[]; class_counts: Record<string, number> }[];
  models: {
    xgboost: { id: string; trees: TreeNode[][]; training_metrics: TrainingMetrics };
    logistic: {
      id: string; intercept: number; coefficients: number[]; means: number[]; scales: number[];
      training_metrics: TrainingMetrics;
    };
  };
};

export function scorePrototypes(bundle: PrototypeBundle, input: number[]) {
  const x = [...input];
  const trend = x[4];
  if (trend === 0) x[3] = bundle.missing_slope_median;
  if (x.length !== bundle.features.length || !x.every(value => Number.isFinite(Math.fround(value))) ||
      (trend !== 0 && trend !== 1) || Math.abs(x[1] - x[0] - x[2]) > 1e-5 ||
      x[5] <= 0 || x[6] < 0 || x[6] > 0.5) return null;

  let treeMargin = 0;
  for (const tree of bundle.models.xgboost.trees) {
    let [feature, value, left, right] = tree[0];
    while (feature >= 0) {
      [feature, value, left, right] = tree[Math.fround(x[feature]) < Math.fround(value) ? left : right];
    }
    treeMargin = Math.fround(treeMargin + Math.fround(value));
  }

  const model = bundle.models.logistic;
  const linearMargin = model.coefficients.reduce((margin, coefficient, i) =>
    margin + coefficient * ((x[i] - model.means[i]) / model.scales[i]), model.intercept);

  return [treeMargin, linearMargin].map(margin => {
    const score = 1 / (1 + Math.exp(-margin));
    return { score, action: score >= bundle.threshold ? "HANDOVER" : "STAY" };
  });
}
