import { Play } from "lucide-react";
import type { TwinRun } from "./NetworkTwin";

type Props = {
  runs: TwinRun[];
  labels: Record<string, string>;
  onReplay: (id: string) => void;
};

const cellColors = ["#66d6c6", "#8caafe", "#d1a4ef"];
const colorFor = (cell: number) => cellColors[(cell - 1) % cellColors.length] ?? "#b1bcc9";

export default function HandoverTimeline({ runs, labels, onReplay }: Props) {
  const rows = runs.map(run => ({
    run,
    events: run.events.filter(e => e.event === "CONNECTION_ESTABLISHED" || e.event === "HO_SUCCESS")
      .sort((a, b) => a.time_s - b.time_s),
  })).sort((a, b) => a.run.controller.localeCompare(b.run.controller) || a.run.rng_run - b.run.rng_run);
  const cells = [...new Set(rows.flatMap(r => r.events.map(e => e.cell_id)))].sort((a, b) => a - b);
  const last = Math.max(0, ...rows.flatMap(r => r.events.map(e => e.time_s)));
  const step = Math.max(1, Math.ceil(last / 4));
  const end = 4 * step;
  const percent = (t: number) => `${100 * t / end}%`;

  return <section className="trace-panel" aria-label="Recorded serving-cell timeline">
    <div className="trace-heading">
      <h2>Serving-cell timeline</h2>
      <p>Connection and completed handovers by recorded run.</p>
    </div>
    <div className="cell-legend">
      {cells.map(cell => <span key={cell}><i style={{ background: colorFor(cell) }}/>Cell {cell}</span>)}
    </div>
    {rows.length === 0 ? <p className="empty-trace">No recordings match these filters.</p> :
      <div className="trace-plot">
        {rows.map(({ run, events }) => <button type="button" className="trace-row" key={run.id} onClick={() => onReplay(run.id)}
          aria-label={`Replay ${labels[run.controller]} at ${run.speed_kmh} km/h, run ${run.rng_run}`}>
          <span className="trace-name">{labels[run.controller]}<small>Run {run.rng_run}</small></span>
          <span className="trace-track" aria-hidden="true">
            {events.map((e, i) => <span key={i} className="trace-segment" style={{
              left: percent(e.time_s), width: percent((events[i + 1]?.time_s ?? e.time_s) - e.time_s),
              color: colorFor(e.cell_id),
            }} title={`Cell ${e.cell_id} at ${e.time_s.toFixed(3)} s`}/>)}
          </span>
          <Play size={13} aria-hidden="true"/>
        </button>)}
        <div className="trace-axis" aria-hidden="true">{[0, 1, 2, 3, 4].map(i =>
          <span key={i} style={{ left: percent(step * i) }}>{step * i}s</span>)}</div>
      </div>}
    <div className="trace-caption"><Play size={13}/>Select a run to open its replay.</div>
  </section>;
}
