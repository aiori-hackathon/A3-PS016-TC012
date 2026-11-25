import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { FlowMode, TopologyNode, TwinRun } from "./recordedReplay";

type Point = { x: number; y: number };
type Props = {
  run: TwinRun;
  time: number;
  duration: number;
  serving: number | null;
  selection: TopologyNode | null;
  onSelect: (node: TopologyNode) => void;
  expanded?: boolean;
  flow?: FlowMode;
  playing?: boolean;
};

const cellColors = ["#62deda", "#7aa5fb", "#ad9bf5"];
const route = [
  { x: 48, y: 193 }, { x: 142, y: 167 }, { x: 241, y: 180 },
  { x: 355, y: 147 }, { x: 444, y: 163 }, { x: 548, y: 139 }, { x: 665, y: 158 },
];
const routeLength = route.slice(1).reduce(
  (sum, p, i) => sum + Math.hypot(p.x - route[i].x, p.y - route[i].y), 0,
);

function routePoint(fraction: number) {
  let remaining = fraction * routeLength;
  for (let i = 1; i < route.length; i++) {
    const start = route[i - 1];
    const end = route[i];
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    if (remaining <= length) {
      const part = remaining / length;
      return { x: start.x + part * (end.x - start.x), y: start.y + part * (end.y - start.y) };
    }
    remaining -= length;
  }
  return route[route.length - 1];
}

function packetPoint(points: Point[], fraction: number) {
  const offset = fraction * (points.length - 1);
  const index = Math.min(points.length - 2, Math.floor(offset));
  const start = points[index];
  const end = points[index + 1];
  return {
    x: start.x + (end.x - start.x) * (offset - index),
    y: start.y + (end.y - start.y) * (offset - index),
  };
}

function Tower() {
  return <>
    <ellipse cx="0" cy="2" rx="21" ry="6.5" fill="currentColor" opacity=".13"/>
    <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">
      <path d="M-11 0 L-2 -47 H2 L11 0 M-14 0 H14 M-8 -9 H8 M-6 -20 H6 M-4 -31 H4 M-9 -1 L7 -10 L-5 -20 L4 -30 L-2 -40 M9 -1 L-7 -10 L5 -20 L-4 -30 L2 -40"/>
      <path d="M0 -47 V-64 M-9 -45 H9 M-8 -55 H8"/>
      <rect x="-11" y="-59" width="4" height="15" rx="1.6" fill="currentColor" strokeWidth=".7"/>
      <rect x="7" y="-59" width="4" height="15" rx="1.6" fill="currentColor" strokeWidth=".7"/>
      <path d="M-16 -59 Q-22 -52 -16 -45 M16 -59 Q22 -52 16 -45" opacity=".8"/>
      <path d="M-21 -63 Q-31 -52 -21 -41 M21 -63 Q31 -52 21 -41" opacity=".44"/>
    </g>
    <circle cy="-64" r="2.4" fill="currentColor"/>
  </>;
}

export default function RadioTopology({
  run, time, duration, serving, selection, onSelect, expanded = false, flow = "off", playing = false,
}: Props) {
  const id = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const container = svgRef.current?.parentElement;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setCompact(entry.contentRect.width <= 490);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);
  const towerScale = compact ? 1.42 : 1;
  const groundOffset = compact ? 49 : 0;
  const routeOffset = compact ? 76 : 0;
  const ids = [...new Set([1, 2, 3, ...run.events.flatMap(event =>
    [event.cell_id, event.target_cell_id].filter((cell): cell is number => cell !== null && cell > 0),
  )])].sort((a, b) => a - b);
  const cells = ids.map((cell, i) => ({
    id: cell, x: 130 + i * 460 / (ids.length - 1),
    y: [137, 111, 133][i % 3] + groundOffset, color: cellColors[i % cellColors.length],
  }));
  const activeCell = cells.find(cell => cell.id === serving);
  const point = routePoint(time / duration);
  const device = { x: point.x, y: point.y + routeOffset };
  const host = { x: 262, y: -49 };
  const gateway = { x: 429, y: -49 };
  const packets = activeCell ? [host, gateway, { x: activeCell.x, y: activeCell.y - 40 * towerScale }, device] : [];
  const routePoints = route.map(p => `${p.x},${p.y + routeOffset}`).join(" ");
  const mapTop = expanded ? -80 : 0;
  const mapHeight = (compact ? 335 : 245) - mapTop;

  function nodeProps(key: TopologyNode, label: string) {
    return {
      role: "button", tabIndex: 0,
      "aria-label": label, "aria-pressed": selection === key,
      onClick: () => onSelect(key),
      onKeyDown: (event: KeyboardEvent<SVGGElement>) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          onSelect(key);
        }
      },
    };
  }

  return <svg ref={svgRef} className={`radio-map${expanded ? " expanded" : ""}${playing ? " is-playing" : ""}`}
    viewBox={`0 ${mapTop} 720 ${mapHeight}`} role="group"
    aria-label="Interactive schematic of the LTE radio network">
    <defs>
      <pattern id={id + "-mesh"} width="54" height="28" patternUnits="userSpaceOnUse">
        <path d="M-27 0 27 28 81 0 M-27 28 27 0 81 28" fill="none" stroke="#69849b" strokeWidth=".55"/>
        <circle cx="27" cy="0" r="1" fill="#7896aa"/>
      </pattern>
      <radialGradient id={id + "-ground"}>
        <stop offset="0" stopColor="#192d38"/><stop offset="1" stopColor="#0e151e"/>
      </radialGradient>
      {cells.map(cell => <radialGradient key={cell.id} id={id + "-cell-" + cell.id}>
        <stop offset="0" stopColor={cell.color} stopOpacity=".20"/>
        <stop offset="1" stopColor={cell.color} stopOpacity=".018"/>
      </radialGradient>)}
    </defs>
    <rect y={mapTop} width="720" height={mapHeight} fill={`url(#${id}-ground)`}/>
    <rect y={mapTop} width="720" height={mapHeight} fill={`url(#${id}-mesh)`} opacity=".28"/>
    <g className="map-contours" fill="none" stroke="#728995" strokeWidth=".7" opacity=".19">
      {[0, 1, 2, 3, 4, 5, 6].map(line => <g key={line}>
        <path transform={`translate(${line * 3 - 19} ${line * 6 - 6})`} d="M-54 102 C-16 106 15 91 23 70 S40 32 66 28 S97 17 122 -27"/>
        <path transform={`translate(${line * -4 + 9} ${line * -5 + 4})`} d="M545 288 C596 264 605 222 628 216 S657 208 677 189 S721 185 760 159"/>
      </g>)}
    </g>
    {expanded && <g className="map-core-links" fill="none" stroke="#657d93" strokeWidth="1.1" strokeDasharray="3 5">
      <path d={`M${host.x},${host.y} H${gateway.x}`}/>
      {cells.map(cell => <path key={cell.id} d={`M${gateway.x},${gateway.y + 13} L${cell.x},${cell.y - 55 * towerScale}`}/>)}
    </g>}
    <g aria-hidden="true">
      {cells.map(cell => <g key={cell.id} transform={`translate(${cell.x} ${cell.y})`}
        className={`map-coverage${serving === cell.id ? " is-serving" : ""}${selection === cell.id ? " is-inspected" : ""}`}
        style={{ color: cell.color }}>
        <ellipse rx="104" ry="38" fill={`url(#${id}-cell-${cell.id})`} stroke="currentColor" strokeWidth="1" strokeDasharray="4 5" opacity=".74"/>
        <ellipse rx="79" ry="29" fill="none" stroke="currentColor" strokeWidth="1.4" opacity=".52"/>
        <ellipse rx="51" ry="19" fill="none" stroke="currentColor" strokeWidth="1" opacity=".38"/>
        {playing && serving === cell.id && <ellipse className="map-wave" rx="40" ry="15" fill="none" stroke="currentColor" strokeWidth="1.2"/>}
      </g>)}
      <polyline points={routePoints} fill="none" stroke="#101923" strokeWidth="4"/>
      <polyline points={routePoints} fill="none" stroke="#c2d4e1" strokeWidth="1.3" strokeDasharray="4 5" opacity=".74"/>
      {activeCell && <path d={`M${activeCell.x} ${activeCell.y - 47 * towerScale} L${device.x} ${device.y}`} fill="none"
        stroke={activeCell.color} strokeWidth="1.2" strokeDasharray="2 4" opacity=".8"/>}
    </g>
    {expanded && flow !== "off" && packets.length > 0 && <g aria-hidden="true" className="map-packets">
      <polyline points={packets.map(p => `${p.x},${p.y}`).join(" ")} fill="none" stroke="#80cbd4" strokeWidth="1" opacity=".5"/>
      {(["dl", "ul"] as const).filter(direction => flow === "both" || flow === direction).map(direction =>
        [0, 0.5].map(offset => {
          const fraction = (time / 2.4 + offset) % 1;
          const p = packetPoint(packets, direction === "dl" ? fraction : 1 - fraction);
          return <circle key={direction + offset} cx={p.x} cy={p.y} r="3.3" fill={direction === "dl" ? "#79e4e0" : "#bc9bff"} stroke="#14222d"/>;
        }))}</g>}
    {expanded && ([["host", host, "Remote host"], ["epc", gateway, "EPC / PGW"]] as const).map(([key, pos, name]) =>
      <g key={key} className="radio-node map-core" transform={`translate(${pos.x} ${pos.y}) scale(${compact ? 1.32 : 1})`}
        {...nodeProps(key, "Inspect " + name)}>
        <rect className="core-shape" x="-53" y="-13" width="106" height="26" rx="5"/>
        <text textAnchor="middle" y="4.4">{name}</text>
      </g>)}
    {cells.map(cell => <g key={cell.id} className="radio-node map-tower" transform={`translate(${cell.x} ${cell.y}) scale(${towerScale})`}
      style={{ "--node-color": cell.color, color: cell.color } as CSSProperties}
      {...nodeProps(cell.id, `Inspect eNB ${cell.id}`)}>
      <rect x="-38" y="-76" width="76" height="109" fill="transparent"/>
      <Tower/>
      <g className="node-tag" transform="translate(0 22)">
        <rect x="-32" y="-9" width="64" height="18" rx="4"/>
        <text y="3.6" textAnchor="middle">eNB {String(cell.id).padStart(2, "0")}</text>
      </g>
    </g>)}
    <g className="radio-node map-ue" transform={`translate(${device.x} ${device.y}) scale(${compact ? 1.28 : 1})`}
      {...nodeProps("ue", "Inspect UE 1")}>
      <circle r="19" fill="transparent"/>
      <circle className="ue-halo" r="11" fill="#aaf7da" fillOpacity=".12" stroke="#aaf7da" strokeOpacity=".52"/>
      <circle r="4.4" fill="#bff6dd" stroke="#123d37" strokeWidth="1.6"/>
      <text y="24" textAnchor="middle">UE 1</text>
    </g>
  </svg>;
}
