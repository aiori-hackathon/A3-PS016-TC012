import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { scorePrototypes, type PrototypeBundle } from "../modelPrototype";

const names = ["XGBoost", "Logistic Regression"];
const featureLabels = ["Serving RSRP", "Candidate RSRP", "Signal margin", "Signal margin slope", "Trend available", "UE speed", "Mobility age"];

export default function PrototypeComparison() {
  const [bundle, setBundle] = useState<PrototypeBundle | null>(null);
  const [values, setValues] = useState<string[]>([]);
  const [preset, setPreset] = useState("0");
  const [submitted, setSubmitted] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/handover-prototypes`, { signal: abort.signal })
      .then(response => {
        if (!response.ok) throw new Error("Model artifact unavailable");
        return response.json() as Promise<PrototypeBundle>;
      })
      .then(artifact => {
        setBundle(artifact);
        setValues(artifact.examples[0].features.map(String));
      })
      .catch(() => { if (!abort.signal.aborted) setUnavailable(true); });
    return () => abort.abort();
  }, []);

  const inputs = values.map(value => value.trim() === "" ? NaN : Number(value));
  if (inputs.length) inputs[2] = inputs[1] - inputs[0];
  const results = submitted && bundle ? scorePrototypes(bundle, inputs) : null;
  const observed = bundle && preset !== "" ? bundle.examples[Number(preset)].class_counts : null;

  return <section className="inspect-card prototype-comparison">
    <div className="inspect-head"><h2><FlaskConical size={17}/>XGBoost and Logistic Regression</h2><span className="inspect-aside">Integration prototypes</span></div>
    {!bundle ? <p className="prototype-intro" role={unavailable ? "alert" : "status"}>{unavailable ? "The prototype model file could not be loaded." : "Loading models…"}</p> : <>
      <p className="prototype-intro">Both models use {bundle.training_rows} paired labels over {bundle.unique_feature_vectors} unique inputs ({bundle.class_counts["0"]} STAY, {bundle.class_counts["1"]} HANDOVER). Independent validation is pending.</p>
      <form className="prototype-form" onSubmit={event => { event.preventDefault(); setSubmitted(true); }}>
        <label className="prototype-preset">Recorded pilot input<select value={preset} onChange={event => {
          setPreset(event.target.value);
          setValues(bundle.examples[Number(event.target.value)].features.map(String));
          setSubmitted(false);
        }}>
          <option value="" disabled>Edited input</option>
          {bundle.examples.map((sample, i) => <option key={i} value={i}>Input {i + 1} · {Math.round(sample.features[5] * 3.6)} km/h · {sample.features[2].toFixed(2)} dB</option>)}
        </select></label>
        {observed && <small>Observed for this input · {observed["0"]} STAY · {observed["1"]} HANDOVER</small>}
        <div className="prototype-fields">{bundle.features.map(({ name, unit }, i) =>
          <label key={name}>{featureLabels[i]} <small>{unit}</small><input type="number" step="any"
            required={i !== 3 || inputs[4] !== 0} disabled={i === 3 && inputs[4] === 0} readOnly={i === 2}
            value={i === 2 ? Number.isFinite(inputs[2]) ? inputs[2].toFixed(6) : "" : values[i] ?? ""}
            onChange={event => {
              const value = event.target.value;
              setValues(previous => previous.map((field, index) => index === i ? value : field));
              setPreset("");
              setSubmitted(false);
            }}/></label>)}</div>
        <button type="submit" className="primary-action">Compare predictions</button>
      </form>
      {submitted && !results && <p className="prototype-intro" role="alert">Enter finite measurements, a trend flag of 0 or 1, a positive speed and a mobility age between 0 and 0.5 s.</p>}
      <div className="prototype-results" aria-live="polite">{results?.map(({ action, score }, i) => <div key={names[i]}>
        <strong>{names[i]} · {action}</strong><span>HANDOVER score {score.toFixed(4)} · threshold {bundle.threshold.toFixed(2)}</span>
      </div>)}</div>
      <div className="inspect-table-wrap prototype-metrics" role="region" tabIndex={0} aria-label="Prototype training metrics">
        <table><caption>Training-set comparison</caption><thead><tr><th scope="col">Model</th><th scope="col">Accuracy</th><th scope="col">Balanced accuracy</th><th scope="col">HANDOVER average precision</th></tr></thead>
          <tbody>{Object.values(bundle.models).map(({ id, training_metrics: metrics }, i) => <tr key={id}>
            <th scope="row">{names[i]}</th><td>{(100 * metrics.accuracy).toFixed(1)}%</td><td>{(100 * metrics.balanced_accuracy).toFixed(1)}%</td><td>{(100 * metrics.handover_average_precision).toFixed(1)}%</td>
          </tr>)}</tbody></table>
      </div>
    </>}
  </section>;
}
