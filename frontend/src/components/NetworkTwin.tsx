import { useState } from "react";
import { Activity, ArrowLeftRight, ChevronRight, Clock3, Cpu, Pause, Play, RadioTower, RotateCcw, Smartphone, Unplug } from "lucide-react";
import RFDecisionInspector from "./RFDecisionInspector";
import RadioTopology from "./RadioTopology";
import {
  controllerName, eventLabel, useRecordedReplay,
  type FlowMode, type TopologyNode, type TwinRun,
} from "./recordedReplay";
import "./replay.css";

export type { TwinRun } from "./recordedReplay";

type Props = {
  runs: TwinRun[];
  initialRunId: string;
  initialTime?: number;
  visible: boolean;
};

function Inspector({ node, serving, run, eventCount }: {
  node: TopologyNode; serving: number | null; run: TwinRun; eventCount: number;
}) {
  if (node === "host" || node === "epc") {
    return <div className="replay-inspector-row">
      <Cpu size={18} aria-hidden="true"/><div><strong>{node === "host" ? "Remote host" : "EPC / PGW"}</strong>
        <span>{node === "host" ? "Application traffic endpoint" : "LTE user-plane gateway"}</span></div>
      <small>Logical network element</small>
    </div>;
  }
  if (typeof node === "number") {
    return <div className="replay-inspector-row">
      <RadioTower size={18} aria-hidden="true"/><div><strong>eNB {String(node).padStart(2, "0")}</strong>
        <span>LTE base station · Cell {node}</span></div>
      <small>{serving === node ? "Serving UE 1" : "Neighbour cell"} · {eventCount} completed handovers into cell</small>
    </div>;
  }
  return <div className="replay-inspector-row">
    <Smartphone size={18} aria-hidden="true"/><div><strong>UE 1</strong><span>IMSI 1 · {run.speed_kmh} km/h</span></div>
    <small>{serving === null ? "Awaiting connection" : `Serving cell ${serving}`} · {eventCount} completed handovers</small>
  </div>;
}

function TwinPlayer({ run, visible, initialTime }: { run: TwinRun; visible: boolean; initialTime: number }) {
  const replay = useRecordedReplay(run, visible, initialTime);
  const [node, setNode] = useState<TopologyNode>("ue");
  const [flow, setFlow] = useState<FlowMode>("both");
  const completed = replay.reached.filter(e => e.event === "HO_SUCCESS");
  const next = replay.events.find(e => e.event === "HO_START" && e.time_s > replay.time);
  const lastEvent = replay.reached.at(-1);
  const progress = replay.time / replay.duration * 100;

  return <>
    <div className="replay-workspace">
      <section className="replay-map-panel" aria-label="Network topology and playback">
        <header className="replay-panel-head">
          <div className="radio-title"><RadioTower size={18} aria-hidden="true"/><h3>Network topology</h3></div>
          <label className="replay-flow-select">Packet flow
            <select value={flow} onChange={e => setFlow(e.target.value as FlowMode)}>
              <option value="both">DL + UL</option><option value="dl">Downlink</option>
              <option value="ul">Uplink</option><option value="off">Hidden</option>
            </select>
          </label>
        </header>
        <div className="replay-map-canvas">
          <RadioTopology run={run} time={replay.time} duration={replay.duration}
            serving={replay.serving} playing={replay.playing && visible}
            selection={node} onSelect={setNode} expanded flow={flow}/>
        </div>
        <div className="replay-map-caption">
          <div className="replay-flow-legend">
            <span><i/>Downlink</span><span><i/>Uplink</span>
          </div>
          <span>Position and packet paths are illustrative.</span>
        </div>
        <div className="twin-playback replay-transport">
          <button type="button" className="replay-toggle" onClick={replay.togglePlayback}
            aria-label={replay.playing ? "Pause replay" : "Play replay"}>
            {replay.playing ? <Pause size={15}/> : <Play size={15}/>}
            {replay.playing ? "Pause" : "Play"}
          </button>
          <button type="button" className="replay-restart" title="Restart replay" aria-label="Restart replay"
            onClick={() => replay.seek(0)}><RotateCcw size={15}/></button>
          <input className="radio-seek" aria-label="Simulation time" type="range" min="0" max={replay.duration} step=".001"
            value={replay.time} onChange={e => replay.seek(Number(e.target.value))}
            style={{ backgroundImage: `linear-gradient(to right, var(--map-aqua) ${progress}%, var(--map-track) 0)` }}/>
          <strong className="replay-time">{replay.time.toFixed(2)} s</strong>
          <select aria-label="Playback speed" value={replay.rate} onChange={e => replay.setRate(Number(e.target.value))}>
            {[1, 5, 10, 20].map(speed => <option key={speed} value={speed}>{speed}×</option>)}
          </select>
        </div>
        <Inspector node={node} serving={replay.serving} run={run} eventCount={
          typeof node === "number" ? completed.filter(e => e.cell_id === node).length : completed.length
        }/>
      </section>
      <aside className="replay-chapters">
        <header className="replay-panel-head"><div className="radio-title"><Clock3 size={17} aria-hidden="true"/><h3>Recorded events</h3></div>
          <span className="replay-event-count">{replay.events.length}</span>
        </header>
        {replay.events.length > 0 ? <ol>
          {replay.events.map((event, index) => {
            const current = index === replay.reached.length - 1;
            return <li key={`${event.time_s}-${index}`}><button type="button"
              className={`replay-chapter${current ? " is-current" : ""}${event.time_s <= replay.time ? " is-reached" : ""}`}
              aria-current={current ? "step" : undefined} onClick={() => replay.seek(event.time_s)}
              aria-label={`Seek to ${eventLabel(event)} at ${event.time_s.toFixed(4)} seconds`}>
              <i aria-hidden="true"/><span><strong>{eventLabel(event)}</strong>
                <small>{event.target_cell_id === null ? `Cell ${event.cell_id}` : `Cell ${event.cell_id} → ${event.target_cell_id}`} · {event.time_s.toFixed(4)} s</small></span>
              <ChevronRight size={14} aria-hidden="true"/>
            </button></li>;
          })}
        </ol> : <p>No handover or connection events in this run.</p>}
        <div className="replay-next-event"><ArrowLeftRight size={14} aria-hidden="true"/>
          {next ? `Next handover at ${next.time_s.toFixed(3)} s` : "No further handover starts recorded"}
        </div>
      </aside>
    </div>
    <p className="replay-state-note"><Activity size={14} aria-hidden="true"/>
      {lastEvent ? `Latest recorded event · ${eventLabel(lastEvent)} at ${lastEvent.time_s.toFixed(4)} s` : "Awaiting the first recorded event."}
    </p>
    <RFDecisionInspector selectedRunId={run.id} replayTime={replay.time}/>
  </>;
}

export default function NetworkTwin({ runs, initialRunId, initialTime = 0, visible }: Props) {
  const [selection, setSelection] = useState({ id: initialRunId, time: initialTime });
  const run = runs.find(item => item.id === selection.id) ?? runs[0];

  if (!run) return <div className="replay-unavailable"><Unplug size={18}/>No recorded simulations available.</div>;

  return <div className="replay-view">
    <div className="twin-head replay-run-picker">
      <label>Replay recording
        <select aria-label="Recorded run to replay" value={run.id} onChange={e => setSelection({ id: e.target.value, time: 0 })}>
          {runs.map(item => <option key={item.id} value={item.id}>
            {controllerName[item.controller] ?? item.controller} · {item.speed_kmh} km/h · Run {item.rng_run}
          </option>)}
        </select>
      </label>
    </div>
    <TwinPlayer key={run.id} run={run} visible={visible} initialTime={run.id === selection.id ? selection.time : 0}/>
  </div>;
}
