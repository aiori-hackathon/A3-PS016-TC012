
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Cpu,
} from "lucide-react";
import {
  BarChart,
  Bar,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Metrics = {
  accuracy: number;
  balanced_accuracy: number;
  handover_precision: number;
  handover_recall: number;
  handover_f1: number;
  brier_score: number;
  confusion_matrix_rows_true_columns_predicted_stay_handover:
    number[][];
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
  input_ranges: Record<
    string,
    { min: number; max: number }
  >;
};

function percent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="eval-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>Training-data fit only</small>
    </div>
  );
}

export default function ModelEvaluation() {
  const [report, setReport] = useState<ModelReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${import.meta.env.BASE_URL}model_evaluation.json`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Report HTTP ${response.status}`);
        }
        return response.json() as Promise<ModelReport>;
      })
      .then((data) => {
        setReport(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(String(err));
        setLoading(false);
      });

    return () => controller.abort();
  }, []);

  if (loading) {
    return <div className="eval-panel">Loading model report…</div>;
  }

  if (error || !report) {
    return (
      <div className="eval-panel eval-warning">
        Unable to load model evaluation: {error}
      </div>
    );
  }

  const metrics = report.training_resubstitution_metrics_only;
  const matrix =
    metrics.confusion_matrix_rows_true_columns_predicted_stay_handover;

  const matrixValid =
    matrix.length === 2 &&
    matrix.every(row => row.length === 2);

  const classData = [
    { name: "STAY", count: report.class_counts["0"] ?? 0 },
    { name: "HANDOVER", count: report.class_counts["1"] ?? 0 },
  ];

  const noIndependentValidation =
    report.independent_validation_available === false;

  return (
    <div className="model-evaluation">
      <div className="eval-heading">
        <div>
          <h2>Random Forest · Model Evaluation & Health</h2>
          <p>
            Actual saved model report · reproducible training diagnostics
          </p>
        </div>
        <span className="eval-version">RF PROTOTYPE V1</span>
      </div>

      <div className="eval-warning">
        <AlertTriangle size={20} />
        <div>
          <strong>Independent validation not available</strong>
          <p>
            All classification metrics below were computed on the
            same observations used to fit the model. They must not
            be presented as accuracy on unseen data or proof of
            improved handover performance.
          </p>
        </div>
      </div>

      <div className="eval-heading-secondary">
        <h3>Classification Diagnostics</h3>
        <span>TRAINING RESUBSTITUTION</span>
      </div>

      <div className="eval-metric-grid">
        <MetricCard
          label="Training Accuracy"
          value={percent(metrics.accuracy)}
        />
        <MetricCard
          label="Balanced Accuracy"
          value={percent(metrics.balanced_accuracy)}
        />
        <MetricCard
          label="HANDOVER Precision"
          value={percent(metrics.handover_precision)}
        />
        <MetricCard
          label="HANDOVER Recall"
          value={percent(metrics.handover_recall)}
        />
        <MetricCard
          label="HANDOVER F1"
          value={percent(metrics.handover_f1)}
        />
        <MetricCard
          label="Training Brier Score"
          value={metrics.brier_score.toFixed(4)}
        />
      </div>

      <div className="eval-two-column">
        <div className="eval-panel">
          <h3>Confusion Matrix</h3>
          <p>
            Training observations · rows are actual labels,
            columns are predicted labels
          </p>

          {matrixValid ? (
            <div className="eval-matrix">
              <div />
              <div className="eval-matrix-label">Predicted STAY</div>
              <div className="eval-matrix-label">Predicted HANDOVER</div>

              <div className="eval-matrix-label">Actual STAY</div>
              <div className="eval-cell eval-correct">
                <strong>{matrix[0][0]}</strong>
                <span>True Negative</span>
              </div>
              <div className="eval-cell eval-incorrect">
                <strong>{matrix[0][1]}</strong>
                <span>False Positive</span>
              </div>

              <div className="eval-matrix-label">Actual HANDOVER</div>
              <div className="eval-cell eval-incorrect">
                <strong>{matrix[1][0]}</strong>
                <span>False Negative</span>
              </div>
              <div className="eval-cell eval-correct">
                <strong>{matrix[1][1]}</strong>
                <span>True Positive</span>
              </div>
            </div>
          ) : (
            <p>Confusion matrix is unavailable or malformed.</p>
          )}
        </div>

        <div className="eval-panel">
          <h3>Training Class Distribution</h3>
          <p>
            Actual labeled samples used for model fitting
          </p>
          <div className="eval-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={classData}>
                <CartesianGrid
                  stroke="#35404d"
                  vertical={false}
                />
                <XAxis
                  dataKey="name"
                  stroke="#a7b4c3"
                  fontSize={11}
                />
                <YAxis
                  stroke="#a7b4c3"
                  fontSize={11}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#222a34",
                    border: "1px solid #475365",
                    color: "#f2f6fb",
                  }}
                />
                <Bar
                  dataKey="count"
                  name="Training samples"
                  fill="#55c1dc"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="eval-note">
            Only {report.unique_feature_vectors} unique feature
            vectors across {report.training_rows} observations.
            The single STAY example makes generalization
            especially uncertain.
          </p>
        </div>
      </div>

      <div className="eval-heading-secondary">
        <h3>Model Health & Readiness</h3>
        <span>ARTIFACT AND VALIDATION STATUS</span>
      </div>

      <div className="eval-health-grid">
        <div className="eval-health">
          <CheckCircle2 color="#63d4ae" size={19} />
          <div>
            <strong>Model Artifact</strong>
            <span>Available · RF prototype v1</span>
          </div>
        </div>

        <div className="eval-health">
          <Cpu color="#63d4ae" size={19} />
          <div>
            <strong>JSON / sklearn parity</strong>
            <span>
              Maximum absolute error:
              {" "}{report.json_sklearn_max_absolute_error.toExponential(2)}
            </span>
          </div>
        </div>

        <div className="eval-health">
          <ShieldAlert color="#f0bb70" size={19} />
          <div>
            <strong>Independent validation</strong>
            <span>
              {noIndependentValidation
                ? "Not available"
                : "See validation report"}
            </span>
          </div>
        </div>

        <div className="eval-health">
          <ShieldAlert color="#f0bb70" size={19} />
          <div>
            <strong>Class balance</strong>
            <span>
              {classData[0].count} STAY /
              {" "}{classData[1].count} HANDOVER
            </span>
          </div>
        </div>

        <div className="eval-health">
          <ShieldAlert color="#f0bb70" size={19} />
          <div>
            <strong>Held-out test evaluation</strong>
            <span>
              {report.test_metrics === null
                ? "Not available"
                : "Results recorded"}
            </span>
          </div>
        </div>

        <div className="eval-health">
          <Cpu color="#8ba8cb" size={19} />
          <div>
            <strong>C++ parity report</strong>
            <span>{report.cpp_compile_and_parity}</span>
          </div>
        </div>
      </div>

      <div className="eval-panel">
        <h3>Training Feature Ranges</h3>
        <p>
          Recorded training coverage. These ranges are not
          live input-drift measurements.
        </p>

        <div className="table-scroll">
          <table className="eval-table">
            <thead>
              <tr>
                <th>Input feature</th>
                <th>Minimum</th>
                <th>Maximum</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.input_ranges).map(
                ([name, range]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{range.min.toFixed(3)}</td>
                    <td>{range.max.toFixed(3)}</td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="eval-warning">
        <AlertTriangle size={19} />
        <div>
          <strong>Research limitation</strong>
          <p>
            This prototype was trained on 16 paired-outcome rows
            with four distinct feature vectors. There is no
            independent evaluation set, no validated probability
            calibration, and no established real-world
            performance guarantee.
          </p>
          <p className="eval-model-id">
            Model ID: {report.model_id}
          </p>
        </div>
      </div>
    </div>
  );
}
