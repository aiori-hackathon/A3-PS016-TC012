import RFDecisionInspector from "./RFDecisionInspector";


import { useEffect, useMemo, useState } from "react";
import {
  Play, Pause, RotateCcw, Network, Info
} from "lucide-react";

type HandoverEvent = {
  time_s: number;
  cell_id: number;
  event: string;
  target_cell_id: number | null;
};

export type TwinRun = {
  id: string;
  controller: string;
  speed_kmh: number;
  rng_run: number;
  events: HandoverEvent[];
};

type Props = {
  runs: TwinRun[];
};

const names: Record<string, string> = {
  a3: "A3-RSRP",
  rule: "Rule-based",
  ml: "Random Forest",
};


// MOBI-HO PACKET FLOW
type Point = { x: number; y: number };

function pointOnRoute(points: Point[], fraction: number): Point {
  const section = Math.min(
    points.length - 2,
    Math.floor(fraction * (points.length - 1))
  );

  const position = fraction * (points.length - 1) - section;
  const a = points[section];
  const b = points[section + 1];

  return {
    x: a.x + (b.x - a.x) * position,
    y: a.y + (b.y - a.y) * position,
  };
}

export default function NetworkTwin({ runs }: Props) {
  const [selectedId, setSelectedId] = useState("");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(5);
  // MOBI-HO NETWORK INSPECTOR
  const [selectedNode, setSelectedNode] = useState("ue");

  const [flowMode, setFlowMode] =
    useState<"both" | "dl" | "ul" | "off">("both");


  const selected = runs.find(
    (run) => run.id === selectedId
  ) ?? runs[0];

  const events = useMemo(
    () => [...(selected?.events ?? [])].sort(
      (a, b) => a.time_s - b.time_s
    ),
    [selected]
  );

  const duration = Math.max(
    10,
    ...events.map((event) => event.time_s + 4)
  );

  useEffect(() => {
    if (!playing) return;

    const timer = window.setInterval(() => {
      setTime((current) => {
        const next = Math.min(
          duration,
          current + rate * 0.1
        );

        if (next >= duration) {
          setPlaying(false);
        }

        return next;
      });
    }, 100);

    return () => window.clearInterval(timer);
  }, [playing, duration, rate]);

  useEffect(() => {
    setTime(0);
    setPlaying(false);
  }, [selected?.id]);

  if (!selected) {
    return <p>No recorded simulations available.</p>;
  }

  const completed = events.filter(
    (event) =>
      event.event === "HO_SUCCESS" &&
      event.time_s <= time
  );

  const connection = events.find(
    (event) => event.event === "CONNECTION_ESTABLISHED"
  );

  const serving = completed.length
    ? completed[completed.length - 1].cell_id
    : connection?.cell_id ?? 1;

  const nextEvent = events.find(
    (event) =>
      event.event === "HO_START" &&
      event.time_s > time
  );

  const lastEvent = [...events].reverse().find(
    (event) => event.time_s <= time
  );

  // Visual movement is illustrative. Cell association
  // changes only at recorded HO_SUCCESS timestamps.
  const progress = Math.min(time / duration, 1);
  const ueX = 170 + progress * 560;
  const cells = [170, 450, 730];

  const servingX = cells[serving - 1];

  const downlinkRoute: Point[] = [
    { x: 450, y: 48 },
    { x: 450, y: 108 },
    { x: servingX, y: 208 },
    { x: ueX, y: 317 },
  ];

  const uplinkRoute = [...downlinkRoute].reverse();

  // Illustrative packet animation, synchronized to replay time.
  const packetCycle = 1.8;
  const packetOffsets = [0, 0.33, 0.66];

  const packetPositions = (route: Point[]) =>
    packetOffsets.map((offset) => {
      const fraction = ((time / packetCycle + offset) % 1 + 1) % 1;
      return pointOnRoute(route, fraction);
    });


  return (
    <div className="twin-panel">
      <div className="twin-head">
        <div>
          <h3><Network size={17} /> Network Digital Twin</h3>
          <p>Recorded LTE topology and handover replay</p>
        </div>

        <select
          value={selected.id}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {runs.map((run) => (
            <option key={run.id} value={run.id}>
              {names[run.controller]} · {run.speed_kmh} km/h
              · Run {run.rng_run}
            </option>
          ))}
        </select>
      </div>

      <div className="network-inspector">
        <div className="inspector-heading">
          <strong>Network Element Inspector</strong>
          <span>Selected: {selectedNode.toUpperCase()}</span>
        </div>

        {selectedNode === "ue" ? (
          <div className="inspector-grid">
            <div><small>Device</small><b>UE · IMSI 1</b></div>
            <div><small>Speed</small><b>{selected.speed_kmh} km/h</b></div>
            <div><small>Serving cell</small><b>Cell {serving}</b></div>
            <div><small>Completed HOs at replay time</small>
              <b>{completed.length}</b></div>
          </div>
        ) : selectedNode.startsWith("enb") ? (
          <div className="inspector-grid">
            <div><small>Base station</small>
              <b>eNB {selectedNode.slice(3)}</b></div>
            <div><small>Cell identifier</small>
              <b>{selectedNode.slice(3)}</b></div>
            <div><small>Association status</small>
              <b>{serving === Number(selectedNode.slice(3))
                ? "Serving UE" : "Neighbor cell"}</b></div>
            <div><small>Completed handovers into cell</small>
              <b>{completed.filter(e =>
                e.cell_id === Number(selectedNode.slice(3))
              ).length}</b></div>
          </div>
        ) : (
          <div className="inspector-grid">
            <div><small>Network element</small>
              <b>{selectedNode === "epc"
                ? "LTE EPC / PGW" : "Remote Host"}</b></div>
            <div><small>Role</small>
              <b>{selectedNode === "epc"
                ? "User-plane gateway" : "Application traffic endpoint"}</b>
            </div>
            <div><small>Visualization</small>
              <b>Logical network topology</b></div>
            <div><small>Per-hop packet traces</small>
              <b>Not available</b></div>
          </div>
        )}
      </div>

      <svg
        className="twin-diagram"
        viewBox="0 0 900 390"
        role="img"
        aria-label="LTE topology with three base stations, EPC, remote host and moving user equipment"
      >
        <defs>
          <linearGradient id="cellGlow">
            <stop offset="0" stopColor="#47bfe8" stopOpacity=".20"/>
            <stop offset="1" stopColor="#47bfe8" stopOpacity="0"/>
          </linearGradient>
        </defs>

        {/* Packet route and EPC */}
        <g fill="none" stroke="#606e80" strokeWidth="2">
          <path d="M450 48 V87"/>
          <path d="M450 131 V158 H170 V182"/>
          <path d="M450 158 V182"/>
          <path d="M450 158 H730 V182"/>
          <path
            d="M170 211 H730"
            strokeDasharray="7 6"
            opacity=".5"
          />
        </g>

        <rect x="375" y="13" width="150" height="36"
          rx="6" fill="#263c4e" stroke="#587a97"/>
        <text x="450" y="35" textAnchor="middle"
          fill="#e4eef7" fontSize="14">
          Remote Host
        </text>

        <rect x="390" y="86" width="120" height="45"
          rx="6" fill="#303649" stroke="#75809a"/>
        <text x="450" y="105" textAnchor="middle"
          fill="#e4eef7" fontSize="13">
          EPC / PGW
        </text>
        <text x="450" y="120" textAnchor="middle"
          fill="#9baac1" fontSize="10">
          User-plane gateway
        </text>

        {cells.map((x, index) => {
          const active = serving === index + 1;

          return (
            <g key={index}>
              {active && (
                <circle cx={x} cy="208" r="82"
                  fill="url(#cellGlow)" />
              )}
              <circle
                cx={x}
                cy="208"
                r="27"
                fill={active ? "#184e5c" : "#293342"}
                stroke={active ? "#5dd7e9" : "#657184"}
                strokeWidth={active ? 3 : 1.5}
              />
              <path
                d={`M${x} 190 V226
                    M${x-12} 199 Q${x} 187 ${x+12} 199
                    M${x-17} 195 Q${x} 177 ${x+17} 195`}
                fill="none"
                stroke="#d7edf7"
                strokeWidth="2"
              />
              <text x={x} y="249"
                textAnchor="middle"
                fontSize="13"
                fill="#e2e8f0">
                eNB {index + 1}
              </text>
              <text x={x} y="265"
                textAnchor="middle"
                fontSize="11"
                fill={active ? "#73e2c6" : "#8b96a8"}>
                {active ? "SERVING CELL" : "NEIGHBOR"}
              </text>
            </g>
          );
        })}

        <path d="M115 317 H785"
          stroke="#465364" strokeWidth="3"
          strokeDasharray="7 6"/>

        <line
          x1={cells[serving - 1]}
          y1="272"
          x2={ueX}
          y2="315"
          stroke="#52d8b5"
          strokeDasharray="6 5"
          strokeWidth="2"
        />


        {/* Animated illustrative packet routes */}
        {flowMode !== "off" && (
          <g>
            {(flowMode === "both" || flowMode === "dl") && (
              <g>
                <path
                  d={`M450 48 L450 108 L${servingX} 208 L${ueX} 317`}
                  stroke="#5ad3ee"
                  strokeWidth="2"
                  strokeDasharray="5 6"
                  strokeOpacity=".75"
                  fill="none"
                />
                {packetPositions(downlinkRoute).map((p, i) => (
                  <circle
                    key={`dl-${i}`}
                    cx={p.x}
                    cy={p.y}
                    r="5"
                    fill="#5ad3ee"
                    stroke="#d6f7ff"
                    strokeWidth="1"
                    className="flow-particle"
                  />
                ))}
              </g>
            )}

            {(flowMode === "both" || flowMode === "ul") && (
              <g>
                {packetPositions(uplinkRoute).map((p, i) => (
                  <circle
                    key={`ul-${i}`}
                    cx={p.x}
                    cy={p.y}
                    r="4"
                    fill="#54dcb8"
                    stroke="#d8fff2"
                    strokeWidth="1"
                    className="flow-particle"
                  />
                ))}
              </g>
            )}
          </g>
        )}

        {/* UE movement over the replay timeline */}
        <g transform={`translate(${ueX}, 317)`}>
          <circle r="17"
            fill="#1e5148"
            stroke="#52d8b5"
            strokeWidth="2.5"
          />
          <rect x="-6" y="-10" width="12" height="20"
            rx="3" fill="none" stroke="#e5fff6"
            strokeWidth="1.5"/>
          <circle cy="6" r="1.2" fill="#e5fff6"/>
          <text y="34" textAnchor="middle"
            fontSize="12" fill="#8de6d2">
            UE 1
          </text>
        </g>

        <text x="18" y="380"
          fontSize="11" fill="#8c9aac">
          Illustrative UE position · serving-cell state from recorded events
        </text>

        {/* Clickable topology inspection targets */}
        <g className="twin-hit-targets">
          <rect x="375" y="13" width="150" height="36"
            fill="transparent" role="button" tabIndex={0}
            aria-label="Inspect Remote Host"
            onClick={() => setSelectedNode("host")}
            onKeyDown={(e) => {
              if (e.key === "Enter") setSelectedNode("host");
            }}
          />
          <rect x="390" y="86" width="120" height="45"
            fill="transparent" role="button" tabIndex={0}
            aria-label="Inspect EPC gateway"
            onClick={() => setSelectedNode("epc")}
            onKeyDown={(e) => {
              if (e.key === "Enter") setSelectedNode("epc");
            }}
          />
          {cells.map((x, i) => (
            <circle key={i} cx={x} cy="208" r="32"
              fill="transparent" role="button" tabIndex={0}
              aria-label={`Inspect eNB ${i + 1}`}
              onClick={() => setSelectedNode(`enb${i + 1}`)}
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  setSelectedNode(`enb${i + 1}`);
              }}
            />
          ))}
          <circle cx={ueX} cy="317" r="25"
            fill="transparent" role="button" tabIndex={0}
            aria-label="Inspect UE 1"
            onClick={() => setSelectedNode("ue")}
            onKeyDown={(e) => {
              if (e.key === "Enter") setSelectedNode("ue");
            }}
          />
        </g>
      </svg>


      <div className="flow-toolbar">
        <div className="flow-legend">
          <span><i className="flow-dot dl" /> Downlink</span>
          <span><i className="flow-dot ul" /> Uplink</span>
        </div>

        <label>
          Packet visualization
          <select
            value={flowMode}
            onChange={(e) =>
              setFlowMode(
                e.target.value as "both" | "dl" | "ul" | "off"
              )
            }
          >
            <option value="both">DL + UL</option>
            <option value="dl">Downlink only</option>
            <option value="ul">Uplink only</option>
            <option value="off">Hide packets</option>
          </select>
        </label>
      </div>

      <div className="twin-playback">
        <button onClick={() => setPlaying(!playing)}>
          {playing ? <Pause size={16}/> : <Play size={16}/>}
          {playing ? "Pause" : "Play"}
        </button>

        <button
          onClick={() => {
            setTime(0);
            setPlaying(false);
          }}
          title="Restart"
        >
          <RotateCcw size={16}/>
        </button>

        <input
          aria-label="Simulation time"
          type="range"
          min="0"
          max={duration}
          step=".1"
          value={time}
          onChange={(e) => {
            setTime(Number(e.target.value));
            setPlaying(false);
          }}
        />

        <strong>{time.toFixed(1)}s</strong>

        <select
          aria-label="Playback speed"
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
        >
          <option value={1}>1×</option>
          <option value={5}>5×</option>
          <option value={10}>10×</option>
          <option value={20}>20×</option>
        </select>
      </div>



      <RFDecisionInspector
        selectedRunId={selected.id}
        replayTime={time}
      />

      <div className="twin-details">
        <span>Serving cell: <b>{serving}</b></span>
        <span>
          Last event: <b>{lastEvent?.event ?? "INITIALIZING"}</b>
        </span>
        <span>
          Next HO: <b>{
            nextEvent
              ? `${nextEvent.time_s.toFixed(2)}s`
              : "None recorded"
          }</b>
        </span>
      </div>

      <p className="twin-note">
        <Info size={14}/>
        The moving UE and topology links are illustrative.
        Serving-cell changes follow recorded HO_SUCCESS events.
        Intermediate packet-hop traces are not available.
      </p>
    </div>
  );
}

