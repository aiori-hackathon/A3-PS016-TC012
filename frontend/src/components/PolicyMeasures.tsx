import { useState } from "react";
import { ArrowUpRight, ChartNoAxesColumn } from "lucide-react";
import { policyColors, type ControllerSummary } from "../benchmark";

const measures = {
  gap: { name: "Reception gap", note: "Mean of the largest excess reception gap in each run", unit: "ms", digits: 1 },
  throughput: { name: "Throughput", note: "Mean received application payload per second", unit: "Mbps", digits: 4 },
  meanGapCount: { name: "Excess gaps over 5 ms", note: "Mean count of gaps exceeding 5 ms per run", unit: "gaps", digits: 1 },
  meanSkipped: { name: "Skipped sequences", note: "Mean skipped packet sequence numbers per run", unit: "skipped", digits: 1 },
  firstCompletion: { name: "First completed handover", note: "Mean time of first completion among runs with a successful handover", unit: "s", digits: 3 },
};
type Measure = keyof typeof measures;

export default function PolicyMeasures({ rows, onCompare }: { rows: ControllerSummary[]; onCompare?: () => void }) {
  const [measure, setMeasure] = useState<Measure>("gap");
  const metric = measures[measure];
  const maximum = Math.max(0, ...rows.map(row => row[measure] ?? 0));

  return <section className="surface measure-panel">
    <div className="surface-head"><h2><ChartNoAxesColumn size={17}/>Controller metrics</h2>
      {onCompare && <button className="icon-button" onClick={onCompare} aria-label="Open policy comparison"><ArrowUpRight size={17}/></button>}
    </div>
    <div className="measure-content">
      {onCompare ? <div className="segmented measure-switch" role="group" aria-label="Comparison metric">
        {(["gap", "throughput"] as const).map(key => <button key={key} type="button" aria-pressed={measure === key}
          onClick={() => setMeasure(key)}>{measures[key].name}</button>)}
      </div> : <label className="field-inline">Metric<select value={measure} onChange={e => setMeasure(e.target.value as Measure)}>
        {Object.entries(measures).map(([key, m]) => <option key={key} value={key}>{m.name}</option>)}
      </select></label>}
      <p className="measure-note">{metric.note}.</p>
      <div className="measure-bars">
        {rows.map(row => {
          const value = row[measure];
          return <div className="measure-row" key={row.policy}>
            <div><span><i className="policy-dot" style={{ background: policyColors[row.policy] }}/>{row.controller}</span>
              <strong>{value == null ? "—" : <>{value.toFixed(metric.digits)} <small>{metric.unit}</small></>}</strong></div>
            <div className="measure-track" aria-hidden="true"><i style={{
              width: `${maximum && value !== null ? value / maximum * 100 : 0}%`, background: policyColors[row.policy],
            }}/></div>
          </div>;
        })}
      </div>
      {!rows.length && <p className="empty-state">No controller measurements for this selection.</p>}
    </div>
  </section>;
}
