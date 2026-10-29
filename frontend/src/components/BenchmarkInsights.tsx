import DonutBreakdown from "./DonutBreakdown";

import { useMemo } from "react";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line,
  CartesianGrid, XAxis, YAxis, Tooltip, Legend
} from "recharts";

type Event = {
  time_s: number;
  event: string;
  cell_id: number;
  target_cell_id: number | null;
};

type Run = {
  id: string;
  controller: string;
  speed_kmh: number;
  rng_run: number;
  throughput_mbps: number;
  max_excess_gap_ms: number;
  gaps_over_5ms: number;
  skipped_sequences: number;
  ho_successes: number;
  ho_failures: number;
  pingpong: number;
  events: Event[];
};

type Props = {
  runs: Run[];
  speed: number;
};

const controllers = ["a3", "rule", "ml"];

const labels: Record<string, string> = {
  a3: "A3-RSRP",
  rule: "Rule-based",
  ml: "Random Forest",
};

const colors: Record<string, string> = {
  a3: "#58c9da",
  rule: "#edae83",
  ml: "#ae91ee",
};

const tooltipStyle = {
  backgroundColor: "#22252b",
  border: "1px solid #414853",
  borderRadius: 5,
  color: "#f1f2f4",
};

function average(numbers: number[]) {
  return numbers.length
    ? numbers.reduce((a, b) => a + b, 0) / numbers.length
    : 0;
}

function ChartPanel({
  title, subtitle, children
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel benchmark-chart-panel">
      <div className="panel-heading">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
      </div>
      <div className="benchmark-chart-area">
        {children}
      </div>
    </div>
  );
}

export default function BenchmarkInsights({ runs, speed }: Props) {
  const throughputBySpeed = useMemo(
    () => [30, 120].map(s => {
      const result: Record<string, number | string> = {
        speed: `${s} km/h`,
      };

      controllers.forEach(policy => {
        const items = runs.filter(
          r => r.speed_kmh === s && r.controller === policy
        );
        result[policy] = average(
          items.map(r => r.throughput_mbps)
        );
      });
      return result;
    }),
    [runs]
  );

  const diagnostics = useMemo(() => {
    return controllers.map(policy => {
      const items = runs.filter(
        r => r.speed_kmh === speed && r.controller === policy
      );

      return {
        name: labels[policy],
        policy,
        gaps: average(items.map(r => r.gaps_over_5ms)),
        skipped: average(items.map(r => r.skipped_sequences)),
        firstHandover: average(
          items
            .map(r => r.events
              .filter(e => e.event === "HO_SUCCESS")
              .sort((a, b) => a.time_s - b.time_s)[0]?.time_s
            )
            .filter((t): t is number => t !== undefined)
        ),
      };
    });
  }, [runs, speed]);

  const runComparison = useMemo(() => {
    const runIds = [...new Set(
      runs.filter(r => r.speed_kmh === speed)
        .map(r => r.rng_run)
    )].sort((a, b) => a - b);

    return runIds.map(runId => {
      const result: Record<string, number | string> = {
        run: `Run ${runId}`
      };

      controllers.forEach(policy => {
        result[policy] = runs.find(
          r => r.rng_run === runId &&
               r.speed_kmh === speed &&
               r.controller === policy
        )?.throughput_mbps ?? 0;
      });

      return result;
    });
  }, [runs, speed]);

  return (
    <div className="benchmark-insights">
      <div className="section-heading">
        <h2>Advanced Benchmark Analytics</h2>
        <span>RECORDED NS-3 DATA</span>
      </div>


      <div className="donut-section">
        <DonutBreakdown
          title="Handover Outcomes"
          subtitle={`Logged results at ${speed} km/h · all recorded RNG runs`}
          items={[
            {
              name: "Successful",
              value: runs
                .filter(r => r.speed_kmh === speed)
                .reduce((n, r) => n + r.ho_successes, 0),
              color: "#59d9b6",
            },
            {
              name: "Logged failures",
              value: runs
                .filter(r => r.speed_kmh === speed)
                .reduce((n, r) => n + r.ho_failures, 0),
              color: "#ed8b84",
            },
          ]}
        />
      </div>

      <div className="chart-grid">
        <ChartPanel
          title="Throughput Across Mobility Speeds"
          subtitle="Mean throughput · Mbps · ZOOMED Y-axis (3.10–3.30)"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={throughputBySpeed}>
              <CartesianGrid stroke="#333943" vertical={false}/>
              <XAxis dataKey="speed" stroke="#a0a8b4" fontSize={11}/>
              <YAxis stroke="#a0a8b4" fontSize={11} domain={[3.1, 3.3]} allowDataOverflow={false}/>
              <Tooltip contentStyle={tooltipStyle}/>
              <Legend/>
              {controllers.map(p =>
                <Bar
                  key={p}
                  dataKey={p}
                  name={labels[p]}
                  fill={colors[p]}
                  radius={[3, 3, 0, 0]}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel
          title={`Excess Reception Gaps · ${speed} km/h`}
          subtitle="Mean number of gaps over 5 ms per run · lower is better"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={diagnostics}>
              <CartesianGrid stroke="#333943" vertical={false}/>
              <XAxis dataKey="name" stroke="#a0a8b4" fontSize={11}/>
              <YAxis stroke="#a0a8b4" fontSize={11}/>
              <Tooltip contentStyle={tooltipStyle}/>
              <Bar dataKey="gaps" name="Gap events" fill="#ae91ee"/>
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel
          title={`Skipped Sequence Diagnostics · ${speed} km/h`}
          subtitle="Mean skipped sequence numbers per run · not verified packet loss"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={diagnostics}>
              <CartesianGrid stroke="#333943" vertical={false}/>
              <XAxis dataKey="name" stroke="#a0a8b4" fontSize={11}/>
              <YAxis stroke="#a0a8b4" fontSize={11}/>
              <Tooltip contentStyle={tooltipStyle}/>
              <Bar dataKey="skipped" name="Skipped sequences" fill="#edae83"/>
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel
          title={`First Completed Handover · ${speed} km/h`}
          subtitle="Mean first HO_SUCCESS timestamp · seconds · not a quality score"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={diagnostics}>
              <CartesianGrid stroke="#333943" vertical={false}/>
              <XAxis dataKey="name" stroke="#a0a8b4" fontSize={11}/>
              <YAxis stroke="#a0a8b4" fontSize={11}/>
              <Tooltip contentStyle={tooltipStyle}/>
              <Bar
                dataKey="firstHandover"
                name="First completion (s)"
                fill="#58c9da"
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>

      <div className="panel benchmark-run-panel">
        <div className="panel-heading">
          <div>
            <h3>Run-to-Run Throughput Comparison</h3>
            <p>
              Zoomed Y-axis (3.10–3.30 Mbps). Compare runs without relying
              only on averages
            </p>
          </div>
        </div>
        <div className="benchmark-chart-area">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={runComparison}>
              <CartesianGrid stroke="#333943" vertical={false}/>
              <XAxis dataKey="run" stroke="#a0a8b4" fontSize={11}/>
              <YAxis stroke="#a0a8b4" fontSize={11} domain={[3.1, 3.3]} allowDataOverflow={false}/>
              <Tooltip contentStyle={tooltipStyle}/>
              <Legend/>
              {controllers.map(p =>
                <Line
                  key={p}
                  dataKey={p}
                  name={labels[p]}
                  stroke={colors[p]}
                  strokeWidth={3}
                  dot={{ r: 5 }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <p className="benchmark-method-note">
        Methodology: two recorded RNG runs per controller and speed.
        Reception-gap values are endpoint timing diagnostics.
        Skipped sequence numbers do not independently establish
        packet loss. Earlier handover completion is not necessarily
        better network performance. The RF model remains exploratory.
      </p>
    </div>
  );
}
