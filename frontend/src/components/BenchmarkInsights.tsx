import { useState } from "react";
import { ChartNoAxesCombined, Table2 } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { policyColors, type BenchmarkRun, type ControllerSummary, average } from "../benchmark";
import PolicyMeasures from "./PolicyMeasures";
import DonutBreakdown from "./DonutBreakdown";

type Props = { runs: BenchmarkRun[]; speed: number; summaries: ControllerSummary[] };

export default function BenchmarkInsights({ runs, speed, summaries }: Props) {
  const [grouping, setGrouping] = useState<"speed" | "run">("speed");
  const selected = runs.filter(r => r.speed_kmh === speed);
  const chartRuns = grouping === "speed" ? runs : selected;
  const groupKey = grouping === "speed" ? "speed_kmh" : "rng_run";
  const groups = [...new Set(chartRuns.map(r => r[groupKey]))].sort((a, b) => a - b);
  const chart = groups.map(group => ({
    group: grouping === "speed" ? `${group} km/h` : `Run ${group}`,
    ...Object.fromEntries(summaries.map(({ policy }) => [
      policy, average(chartRuns.filter(r => r[groupKey] === group && r.controller === policy).map(r => r.throughput_mbps)),
    ])),
  }));
  const throughput = chartRuns.map(r => r.throughput_mbps);
  const from = throughput.length ? Math.floor((Math.min(...throughput) - 0.005) * 100) / 100 : 0;
  const to = throughput.length ? Math.ceil((Math.max(...throughput) + 0.005) * 100) / 100 : 1;

  return <div className="comparison-stack page-in">
    <div className="comparison-grid">
      <PolicyMeasures rows={summaries}/>
      <section className="surface">
        <div className="surface-head"><h2><ChartNoAxesCombined size={17}/>Throughput profile</h2>
          <div className="segmented small" role="group" aria-label="Throughput grouping">
            <button aria-pressed={grouping === "speed"} onClick={() => setGrouping("speed")}>By speed</button>
            <button aria-pressed={grouping === "run"} onClick={() => setGrouping("run")}>By run</button>
          </div>
        </div>
        <p className="chart-note">{grouping === "speed" ? "Mean throughput across speeds" : `Recorded throughput at ${speed} km/h`} · Mbps, zoomed scale</p>
        <div className="chart-area">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chart} margin={{ top: 12, left: -7, right: 28, bottom: 6 }}>
              <CartesianGrid stroke="#2c3643" vertical={false} strokeDasharray="2 5"/>
              <XAxis dataKey="group" tickLine={false} axisLine={false} stroke="#a5b2c2" fontSize={12} tickMargin={10} padding={{ left: 22, right: 22 }}/>
              <YAxis domain={[from, to]} tickFormatter={(n: number) => n.toFixed(2)} tickLine={false} axisLine={false} stroke="#a5b2c2" fontSize={12} width={55}/>
              <Tooltip contentStyle={{ backgroundColor: "#17212c", border: "1px solid #3c4a59", borderRadius: 8 }}
                formatter={(value: unknown) => typeof value === "number" ? `${value.toFixed(4)} Mbps` : "—"}/>
              <Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 12, paddingTop: 10 }}/>
              {summaries.map(({ policy, controller }) => <Line key={policy} dataKey={policy} name={controller} stroke={policyColors[policy]}
                isAnimationActive={false} strokeWidth={grouping === "speed" ? 2 : 0}
                dot={{ r: 4, fill: policyColors[policy] }} activeDot={{ r: 6 }}/>)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
    <section className="surface">
      <div className="surface-head"><h2><Table2 size={17}/>Controller comparison</h2><span className="count-tag">{selected.length} runs</span></div>
      <div className="table-scroll"><table className="numeric-table"><thead><tr>
        <th>Controller</th><th>Throughput (Mbps)</th><th>Max excess gap (ms)</th><th>Successful HOs</th><th>Logged failures</th><th>Ping-pong</th><th>Skipped seq.</th>
      </tr></thead><tbody>{summaries.map(r => <tr key={r.policy}>
        <td><i className="policy-dot" style={{ background: policyColors[r.policy] }}/>{r.controller}</td>
        <td>{r.throughput.toFixed(4)}</td><td>{r.gap.toFixed(1)}</td><td>{r.successes}</td><td>{r.failures}</td><td>{r.pingpong}</td><td>{r.skipped}</td>
      </tr>)}</tbody></table></div>
      <p className="panel-footnote">Throughput and maximum excess gap are means per run. Event and sequence columns are totals. Skipped sequences are a reception diagnostic.</p>
    </section>
    <DonutBreakdown title="Handover outcomes" subtitle={`Logged events at ${speed} km/h across the selected runs`}
      items={[
        { name: "Completed", value: summaries.reduce((n, r) => n + r.successes, 0), color: "#65dcd2" },
        { name: "Logged failures", value: summaries.reduce((n, r) => n + r.failures, 0), color: "#ef9c95" },
      ]}/>
  </div>;
}
