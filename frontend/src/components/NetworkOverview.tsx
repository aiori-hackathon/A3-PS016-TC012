import { useState } from "react";
import {
  Activity, ArrowLeftRight, ArrowUpRight, CircleCheck, CircleDot, CircleX, Gauge, ListTree, Repeat2, ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { average, policyLabels, type BenchmarkRun, type ControllerSummary } from "../benchmark";
import { eventLabel, type HandoverEvent } from "./recordedReplay";
import HandoverTimeline from "./HandoverTimeline";
import TopologyPreview from "./TopologyPreview";
import PolicyMeasures from "./PolicyMeasures";

type Props = {
  runs: BenchmarkRun[];
  summaries: ControllerSummary[];
  pingpongWindow: number;
  onReplay: (runId: string, time?: number) => void;
  onCompare: () => void;
};

function Kpi({ label, value, unit, detail, Icon, tint }: {
  label: string; value: string; unit?: string; detail: string; Icon: LucideIcon; tint: string;
}) {
  return <div className={`kpi ${tint}`}>
    <div className="kpi-label"><span>{label}</span><Icon size={17} aria-hidden="true"/></div>
    <div className="kpi-value" key={value}>{value}{unit && <small>{unit}</small>}</div>
    <div className="kpi-detail">{detail}</div>
  </div>;
}

function cellTransition(event: HandoverEvent) {
  return event.target_cell_id !== null && event.target_cell_id !== undefined
    ? `Cell ${event.cell_id} → ${event.target_cell_id}` : `Cell ${event.cell_id}`;
}

function EventLog({ run, onReplay }: Pick<Props, "onReplay"> & { run: BenchmarkRun }) {
  const events = [...run.events].sort((a, b) => a.time_s - b.time_s);
  return <section className="surface event-log">
    <div className="surface-head"><h2><Activity size={17}/>Event log</h2><span className="count-tag">{events.length} events</span></div>
    <ol className="event-stream">
      {events.map((evt, i) => {
        const Icon = evt.event === "HO_SUCCESS" ? CircleCheck : evt.event === "HO_START" ? ArrowLeftRight :
          evt.event === "HO_FAILURE" ? CircleX : CircleDot;
        return <li key={i} className={`event-item ${evt.event.toLowerCase()}`}>
          <button type="button" onClick={() => onReplay(run.id, evt.time_s)}
            aria-label={`Replay ${eventLabel(evt)} at ${evt.time_s.toFixed(4)} seconds`}>
            <span className="event-icon"><Icon size={13}/></span>
            <span className="event-identity"><strong>{eventLabel(evt)}</strong><small>{cellTransition(evt)}</small></span>
            <time>{evt.time_s.toFixed(3)} s</time>
          </button>
        </li>;
      })}
    </ol>
    {!events.length && <p className="empty-state">This recording contains no events.</p>}
  </section>;
}

export default function NetworkOverview({ runs, summaries, pingpongWindow, onReplay, onCompare }: Props) {
  const [focusId, setFocusId] = useState("");
  const focus = runs.find(run => run.id === focusId) ?? runs[0];
  const throughput = average(runs.map(run => run.throughput_mbps));
  const totalSuccess = runs.reduce((n, r) => n + r.ho_successes, 0);
  const totalFailures = runs.reduce((n, r) => n + r.ho_failures, 0);
  const totalPingpong = runs.reduce((n, r) => n + r.pingpong, 0);

  return <div className="page-stack overview">
    <div className="kpis">
      <Kpi label="Mean throughput" value={throughput?.toFixed(3) ?? "—"} unit="Mbps" detail="Received payload rate" Icon={Gauge} tint="aqua"/>
      <Kpi label="Completed handovers" value={String(totalSuccess)} detail="Successful handover events" Icon={ArrowLeftRight} tint="blue"/>
      <Kpi label="Logged failures" value={String(totalFailures)} detail="Handover attempts" Icon={ShieldCheck} tint="amber"/>
      <Kpi label="Ping-pong events" value={String(totalPingpong)} detail={`${pingpongWindow} s return window`} Icon={Repeat2} tint="violet"/>
    </div>
    {focus && <section className="overview-replay" aria-label="Selected run">
      <div className="block-heading">
        <h2>Run explorer</h2>
        <label className="run-picker"><ListTree size={15}/><select aria-label="Run to inspect" value={focus.id} onChange={e => setFocusId(e.target.value)}>
          {runs.map(run => <option key={run.id} value={run.id}>{policyLabels[run.controller] ?? run.controller} · Run {run.rng_run}</option>)}
        </select></label>
      </div>
      <div className="overview-grid"><TopologyPreview run={focus} onOpen={time => onReplay(focus.id, time)}/><EventLog run={focus} onReplay={onReplay}/></div>
    </section>}
    <div className="block-heading secondary-title"><h2>Scenario diagnostics</h2><button className="text-link" onClick={onCompare}>Policy comparison <ArrowUpRight size={15}/></button></div>
    <div className="overview-grid">
      <HandoverTimeline runs={runs} labels={policyLabels} onReplay={onReplay}/>
      <PolicyMeasures rows={summaries} onCompare={onCompare}/>
    </div>
  </div>;
}
