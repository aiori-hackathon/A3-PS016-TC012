import { useState } from "react";
import { ArrowUpRight, Pause, Play, RadioTower } from "lucide-react";
import RadioTopology from "./RadioTopology";
import { controllerName, useRecordedReplay, type TopologyNode, type TwinRun } from "./recordedReplay";
import "./replay.css";

type Props = { run: TwinRun; onOpen: (time: number) => void };

function Preview({ run, onOpen }: Props) {
  const firstConnection = run.events.find(e => e.event === "CONNECTION_ESTABLISHED");
  const replay = useRecordedReplay(run, true, firstConnection?.time_s ?? 0);
  const [inspected, setInspected] = useState<TopologyNode | null>(null);
  const controller = controllerName[run.controller] ?? run.controller;
  let status = replay.serving === null ? "Awaiting connection" : `UE 1 on cell ${replay.serving}`;
  if (typeof inspected === "number") {
    status = `Cell ${inspected} · ${inspected === replay.serving ? "Serving UE 1" : "Neighbour"}`;
  }

  return <section className="radio-preview" aria-label="Radio topology preview">
    <header className="radio-preview-head">
      <div className="radio-title"><RadioTower size={18} aria-hidden="true"/><h2>Radio topology</h2></div>
      <button type="button" className="radio-open" onClick={() => onOpen(replay.time)}>Open replay <ArrowUpRight size={14}/></button>
    </header>
    <div className="radio-map-stage">
      <div className="radio-map-key" aria-label="Map legend">
        <span><i/>Serving link</span><span><i/>UE route</span>
      </div>
      <RadioTopology run={run} time={replay.time} duration={replay.duration} serving={replay.serving}
        playing={replay.playing} selection={inspected} onSelect={setInspected}/>
      <div className="radio-map-scope">
        <span>{controller} <b>·</b> {run.speed_kmh} km/h <b>·</b> Run {run.rng_run}</span>
        <span>Logical layout</span>
      </div>
    </div>
    <footer className="radio-preview-transport">
      <button type="button" className="radio-preview-play" onClick={replay.togglePlayback}
        aria-label={replay.playing ? "Pause topology preview" : "Play topology preview"}>
        {replay.playing ? <Pause size={14}/> : <Play size={14}/>}
      </button>
      <span className="preview-clock">{replay.time.toFixed(2)} s</span>
      <input type="range" className="radio-seek" aria-label="Topology preview time"
        min={0} max={replay.duration} step=".001" value={replay.time} onChange={e => replay.seek(Number(e.target.value))}
        style={{ backgroundImage: `linear-gradient(to right, var(--map-aqua) ${replay.time / replay.duration * 100}%, var(--map-track) 0)` }}/>
      <span className="radio-inspection">{status}</span>
    </footer>
  </section>;
}

export default function TopologyPreview(props: Props) {
  return <Preview key={props.run.id} {...props}/>;
}
