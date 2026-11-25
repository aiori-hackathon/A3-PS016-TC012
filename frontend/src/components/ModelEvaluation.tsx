import { useEffect, useState } from "react";
import { AlertTriangle, Binary, BookOpen, ChartBar, ChevronDown, Cpu, Grid2X2, Layers3, LoaderCircle, SlidersHorizontal } from "lucide-react";
import "./inspection.css";

type Metrics = {
  accuracy: number;
  balanced_accuracy: number;
  handover_precision: number;
  handover_recall: number;
  handover_f1: number;
  brier_score: number;
  confusion_matrix_rows_true_columns_predicted_stay_handover: number[][];
};
type ModelReport = {
  model_id: string;
  model_status: string;
  training_rows: number;
  unique_feature_vectors: number;
  class_counts: Record<string, number>;
  training_resubstitution_metrics_only: Metrics;
  validation_metrics: unknown | null;
  test_metrics: unknown | null;
  independent_validation_available: boolean;
  json_sklearn_max_absolute_error: number;
  cpp_compile_and_parity: string;
  hyperparameter_search_performed: boolean;
  threshold_tuned: boolean;
  limitations: string[];
  input_ranges: Record<string, { min: number; max: number }>;
};

const actions = ["STAY", "HANDOVER"];
const cellNames = [["True negative", "False positive"], ["False negative", "True positive"]];
const classificationMetrics = [
  ["Accuracy", "accuracy"], ["Balanced accuracy", "balanced_accuracy"],
  ["HANDOVER precision", "handover_precision"], ["HANDOVER recall", "handover_recall"],
  ["HANDOVER F1", "handover_f1"], ["Brier score", "brier_score"],
] as const;

function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  const [asPercentage, setAsPercentage] = useState(false);
  const valid = Array.isArray(matrix) && matrix.length === 2 &&
    matrix.every(row => Array.isArray(row) && row.length === 2 && row.every(n => Number.isFinite(n) && n >= 0));
  return <section className="inspect-card eval-matrix-card">
    <div className="inspect-head"><h2><Grid2X2 size={17}/>Confusion matrix</h2>
      {valid && <div className="eval-segmented" role="group" aria-label="Confusion matrix unit">
        <button type="button" aria-pressed={!asPercentage} onClick={() => setAsPercentage(false)}>Count</button>
        <button type="button" aria-pressed={asPercentage} onClick={() => setAsPercentage(true)}>Row %</button>
      </div>}
    </div>
    {valid ? <div className="eval-matrix-body">
      <table className="eval-matrix" aria-label={asPercentage ? "Percentage of each actual class by prediction" : "Training observations by actual class and prediction"}>
        <thead><tr><th scope="col">Actual ↓</th>{actions.map(action => <th key={action} scope="col">Pred. {action}</th>)}</tr></thead>
        <tbody>{matrix.map((row, actual) => {
          const total = row.reduce((sum, count) => sum + count, 0);
          return <tr key={actions[actual]}><th scope="row">{actions[actual]}</th>{row.map((value, predicted) =>
            <td key={actions[predicted]} className={actual === predicted ? "eval-agrees" : "eval-differs"}>
              <strong key={String(asPercentage)}>{asPercentage ? total ? `${(value / total * 100).toFixed(1)}%` : "—" : value}</strong>
              <small>{cellNames[actual][predicted]}</small>
            </td>)}</tr>;
        })}</tbody>
      </table>
    </div> : <p className="inspect-empty">The report contains no usable confusion matrix.</p>}
  </section>;
}

export default function ModelEvaluation() {
  const [report, setReport] = useState<ModelReport | null>(null);
  const [error, setError] = useState("");
  const [request, setRequest] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${import.meta.env.BASE_URL}model_evaluation.json`, { signal: abort.signal })
      .then(response => {
        if (!response.ok) throw new Error(`Report returned HTTP ${response.status}.`);
        return response.json() as Promise<ModelReport>;
      })
      .then(setReport)
      .catch((err: unknown) => { if (!abort.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => abort.abort();
  }, [request]);

  if (error) return <div className="inspection-pages"><div className="inspect-notice" role="alert">
    <AlertTriangle size={18}/><div><strong>Model report unavailable</strong><p>{error}</p>
      <button type="button" className="inspect-link" onClick={() => { setError(""); setRequest(n => n + 1); }}>Try again</button>
    </div></div></div>;
  if (!report) return <div className="inspection-pages"><div className="inspect-loading" role="status">
    <LoaderCircle size={18} className="inspect-spin"/>Loading the saved model report…
  </div></div>;

  const metrics = report.training_resubstitution_metrics_only;
  const stay = report.class_counts["0"] ?? 0;
  const handover = report.class_counts["1"] ?? 0;
  const total = stay + handover;
  const inputs = Object.entries(report.input_ranges);
  return <div className="inspection-pages model-evaluation">
    <div className="inspect-notice"><BookOpen size={17}/><div>
      <strong>Random Forest · training-set evaluation</strong>
      <p>These scores describe the {report.training_rows} observations used to fit the prototype.
        {" "}{report.independent_validation_available ? "Independent validation is recorded separately." : "Independent validation is pending."}</p>
    </div></div>
    <section className="inspect-card eval-scores" aria-label="Training-set classification metrics">
      <div className="inspect-head"><h2><ChartBar size={17}/>Classification metrics</h2><span className="inspect-aside">Training set</span></div>
      <div className="eval-metric-grid">{classificationMetrics.map(([label, key]) =>
        <div className="eval-metric" key={key}><span>{label}</span>
          <strong>{key === "brier_score" ? metrics[key].toFixed(4) : `${(metrics[key] * 100).toFixed(2)}%`}</strong>
        </div>)}</div>
    </section>
    <div className="eval-pair">
      <ConfusionMatrix matrix={metrics.confusion_matrix_rows_true_columns_predicted_stay_handover}/>
      <section className="inspect-card">
        <div className="inspect-head"><h2><Layers3 size={17}/>Training data</h2></div>
        <div className="eval-training-body">
          <dl className="eval-counts">
            <div><dt>Labelled observations</dt><dd>{report.training_rows}</dd></div>
            <div><dt>Unique input vectors</dt><dd>{report.unique_feature_vectors}</dd></div>
          </dl>
          <div className="eval-distribution" aria-hidden="true">
            <i style={{ width: `${total ? stay / total * 100 : 0}%` }}/><i style={{ width: `${total ? handover / total * 100 : 0}%` }}/>
          </div>
          <div className="eval-class-labels"><span><i/>STAY <strong>{stay}</strong></span><span><i/>HANDOVER <strong>{handover}</strong></span></div>
        </div>
      </section>
    </div>
    <section className="inspect-card">
      <div className="inspect-head"><h2><Cpu size={17}/>Model artifact</h2></div>
      <dl className="eval-provenance">
        <div><dt>Model ID</dt><dd><code>{report.model_id}</code></dd></div>
        <div><dt>Artifact status</dt><dd>{report.model_status.replaceAll("_", " ")}</dd></div>
        <div><dt>Validation metrics</dt><dd>{report.validation_metrics === null ? "Unavailable" : "Recorded"}</dd></div>
        <div><dt>Held-out test metrics</dt><dd>{report.test_metrics === null ? "Unavailable" : "Recorded"}</dd></div>
        <div><dt>JSON / sklearn parity</dt><dd>{report.json_sklearn_max_absolute_error.toExponential(2)} max. absolute difference</dd></div>
        <div><dt>C++ parity report</dt><dd>{report.cpp_compile_and_parity}</dd></div>
      </dl>
      <details className="inspect-details">
        <summary><span><SlidersHorizontal size={15}/>Training feature ranges</span><span>{inputs.length} inputs <ChevronDown size={14}/></span></summary>
        <div className="inspect-table-wrap" role="region" aria-label="Training feature ranges" tabIndex={0}><table>
          <thead><tr><th>Input feature</th><th>Minimum</th><th>Maximum</th></tr></thead>
          <tbody>{inputs.map(([name, range]) => <tr key={name}><td><code>{name}</code></td><td>{range.min.toFixed(3)}</td><td>{range.max.toFixed(3)}</td></tr>)}</tbody>
        </table></div>
      </details>
      {report.limitations.length > 0 && <details className="inspect-details">
        <summary><span><Binary size={15}/>Evaluation limitations</span><ChevronDown size={14}/></summary>
        <ul className="eval-limitations">{report.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul>
      </details>}
    </section>
  </div>;
}
