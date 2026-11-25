import { useState } from "react";
import { Activity, ArrowUpRight, CircuitBoard, Database, Gauge, ListFilter, RadioTower, RotateCcw } from "lucide-react";
import { type Benchmark, type BenchmarkRun, policyLabels } from "../benchmark";
import { eventLabel } from "./recordedReplay";

export function Methodology({ benchmark }: { benchmark: Benchmark }) {
  const speeds = [...new Set(benchmark.runs.map(r => r.speed_kmh))].sort((a, b) => a - b);
  const runs = [...new Set(benchmark.runs.map(r => r.rng_run))].sort((a, b) => a - b);
  const definitions = [
    { Icon: RadioTower, title: "Simulation topology", body: `Three LTE base stations serve one moving UE. The archive covers ${speeds.join(" and ")} km/h with RNG runs ${runs.join(" and ")}.` },
    { Icon: Activity, title: "Handover events", body: "The event log records connection establishment, handover starts and outcomes. A successful handover changes the serving cell in the replay. Device position and packet animation are schematic." },
    { Icon: Gauge, title: "Packet reception", body: `Throughput uses received payload bytes. Excess reception gaps measure time above the expected sequence-number spacing at a nominal ${benchmark.metadata.nominal_packet_interval_ms} ms packet interval. End-to-end packet loss and service interruption require separate evidence.` },
    { Icon: RotateCcw, title: "Ping-pong window", body: `A completed A → B → A return by the same UE within ${benchmark.metadata.pingpong_window_s} seconds counts as a ping-pong event in this benchmark.` },
    { Icon: CircuitBoard, title: "Random Forest prototype", body: "The model was fitted on a small, related set of paired simulations. Its evaluation page reports training-set performance. Independent validation is pending." },
    { Icon: Database, title: "Recorded and live runs", body: "The benchmark archive provides reproducible comparisons. A live simulation creates its own job and results on the configured ns-3 server." },
  ];
  return <div className="method-grid">{definitions.map(({ Icon, title, body }) =>
    <article className="surface method-card" key={title}><span className="method-icon"><Icon size={21}/></span>
      <h2>{title}</h2><p>{body}</p></article>)}</div>;
}

export function Events({ runs, onReplay }: { runs: BenchmarkRun[]; onReplay: (id: string, time: number) => void }) {
  const [policy, setPolicy] = useState("ml");
  const [kind, setKind] = useState("all");
  const policies = [...new Set(runs.map(run => run.controller))];
  const selected = policies.includes(policy) ? policy : policies[0] ?? "";
  const events = runs.filter(run => run.controller === selected).flatMap(run => run.events.map(event => ({ ...event, run })))
    .sort((a, b) => a.run.rng_run - b.run.rng_run || a.time_s - b.time_s);
  const kinds = [...new Set(events.map(e => e.event))];
  const currentKind = kinds.includes(kind) ? kind : "all";
  const visible = events.filter(e => currentKind === "all" || e.event === currentKind);
  return <section className="surface events-table page-in">
    <div className="surface-head"><h2><ListFilter size={17}/>Event history</h2><span className="count-tag">{visible.length} events</span></div>
    <div className="table-toolbar">
      <label className="field-inline">Controller<select value={selected} onChange={e => { setPolicy(e.target.value); setKind("all"); }}>
        {policies.map(p => <option value={p} key={p}>{policyLabels[p] ?? p}</option>)}</select></label>
      <label className="field-inline">Event<select value={currentKind} onChange={e => setKind(e.target.value)}>
        <option value="all">All events</option>{kinds.map(id => <option key={id} value={id}>{id.replaceAll("_", " ")}</option>)}</select></label>
    </div>
    <div className="table-scroll"><table><thead><tr><th>RNG run</th><th>Time (s)</th><th>Event</th><th>Cell</th><th>Target</th><th><span className="sr-only">Replay</span></th></tr></thead>
      <tbody>{visible.map((e, i) => <tr key={e.run.id + i}>
        <td>Run {e.run.rng_run}</td><td className="numeric">{e.time_s.toFixed(4)}</td>
        <td><span className={`event-badge ${e.event.toLowerCase()}`}>{eventLabel(e)}</span></td>
        <td>{e.cell_id}</td><td>{e.target_cell_id ?? "—"}</td>
        <td><button className="text-link" onClick={() => onReplay(e.run.id, e.time_s)} aria-label={`Replay run ${e.run.rng_run} at ${e.time_s.toFixed(4)} s`}>Replay <ArrowUpRight size={14}/></button></td>
      </tr>)}</tbody></table></div>
    {!visible.length && <p className="empty-state">No events match these filters.</p>}
  </section>;
}
