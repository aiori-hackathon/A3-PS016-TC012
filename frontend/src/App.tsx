import BenchmarkInsights from "./components/BenchmarkInsights";
import ModelEvaluation from "./components/ModelEvaluation";
import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowLeftRight, BarChart3, BrainCircuit,
  ChevronRight, Database, Download, LayoutDashboard,
  RadioTower, ShieldCheck, Zap
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, CartesianGrid,
  XAxis, YAxis, Tooltip
} from "recharts";
import NetworkTwin from "./components/NetworkTwin";
import "./App.css";
import SimulationControl from "./components/SimulationControl";
type Event = {
  time_s: number;
  cell_id: number;
  event: string;
  target_cell_id: number | null;
};

type Run = {
  id: string;
  controller: string;
  speed_kmh: number;
  rng_run: number;
  throughput_mbps: number;
  ho_successes: number;
  ho_failures: number;
  max_excess_gap_ms: number;
  gaps_over_5ms: number;
  skipped_sequences: number;
  pingpong: number;
  events: Event[];
};

type Summary = {
  controller: string;
  speed_kmh: number;
  mean_throughput_mbps: number;
  mean_max_excess_gap_ms: number;
  total_ho_successes: number;
  total_ho_failures: number;
  total_pingpong_5s: number;
};

type Benchmark = {
  summary: Summary[];
  runs: Run[];
  metadata: {
    source: string;
    nominal_packet_interval_ms: number;
    pingpong_window_s: number;
    model_status: string;
  };
};

const labels: Record<string, string> = {
  a3: "A3-RSRP",
  rule: "Rule-based",
  ml: "Random Forest"
};

const colors: Record<string, string> = {
  a3: "#58c9da",
  rule: "#edae83",
  ml: "#ae91ee"
};

const policies = ["a3", "rule", "ml"];

const navigation = [
  { id: "overview", name: "Network Overview", Icon: LayoutDashboard },
  { id: "simulation-control", name: "Simulation Control", Icon: Activity },
  { id: "topology", name: "Network Digital Twin", Icon: RadioTower },
  { id: "comparison", name: "Benchmark Comparison", Icon: BarChart3 },
  { id: "events", name: "Handover Events", Icon: ArrowLeftRight },
  { id: "methodology", name: "Model & Methodology", Icon: BrainCircuit },
  { id: "model-evaluation", name: "Model Evaluation", Icon: Activity },
];

export default function App() {
  const [data, setData] = useState<Benchmark | null>(null);
  const [error, setError] = useState("");
  const [speed, setSpeed] = useState(120);
  const [run, setRun] = useState("all");
  const [policy, setPolicy] = useState("ml");
  const [active, setActive] = useState("overview");

  useEffect(() => {
    fetch(import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/benchmark` : `${import.meta.env.BASE_URL}benchmark.json`)
      .then((response) => {
        if (!response.ok) throw new Error("Benchmark JSON not found");
        return response.json();
      })
      .then(setData)
      .catch((err) => setError(String(err)));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.runs.filter(
      (r) => r.speed_kmh === speed &&
        (run === "all" || r.rng_run === Number(run))
    );
  }, [data, speed, run]);

  const comparison = useMemo(() => policies.map((p) => {
    const selected = filtered.filter((r) => r.controller === p);
    const avg = (key: keyof Run) =>
      selected.length
        ? selected.reduce((total, r) => total + Number(r[key]), 0) /
          selected.length
        : 0;

    return {
      controller: labels[p],
      policy: p,
      throughput: Number(avg("throughput_mbps").toFixed(4)),
      gap: Number(avg("max_excess_gap_ms").toFixed(2)),
      successes: selected.reduce((n, r) => n + r.ho_successes, 0),
      failures: selected.reduce((n, r) => n + r.ho_failures, 0),
      pingpong: selected.reduce((n, r) => n + r.pingpong, 0),
      skipped: selected.reduce((n, r) => n + r.skipped_sequences, 0),
    };
  }), [filtered]);

  const events = useMemo(
    () => filtered
      .filter((r) => r.controller === policy)
      .flatMap((r) => r.events.map((e) => ({
        ...e,
        rng_run: r.rng_run
      })))
      .sort((a, b) => a.rng_run - b.rng_run || a.time_s - b.time_s),
    [filtered, policy]
  );

  const totalSuccess = filtered.reduce((n, r) => n + r.ho_successes, 0);
  const totalPingpong = filtered.reduce((n, r) => n + r.pingpong, 0);
  const totalFailures = filtered.reduce((n, r) => n + r.ho_failures, 0);

  const navigate = (id: string) => {
    setActive(id);
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  const exportCSV = () => {
    const columns = [
      "controller", "throughput", "gap",
      "successes", "failures", "pingpong", "skipped"
    ] as const;

    const content = [
      columns.join(","),
      ...comparison.map((r) =>
        columns.map((key) => r[key]).join(",")
      )
    ].join("\n");

    const blob = new Blob([content], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mobi-ho-${speed}kmh-${run}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return <main className="loading">Unable to load benchmark: {error}</main>;
  }

  if (!data) {
    return <main className="loading">Loading MOBI-HO benchmark data…</main>;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon"><RadioTower size={21} /></span>
          <div>
            <strong>MOBI-HO</strong>
            <small>LAB / AIORI-3</small>
          </div>
        </div>

        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {navigation.map(({ id, name, Icon }) => (
            <button
              key={id}
              className={`nav-item ${active === id ? "selected" : ""}`}
              onClick={() => navigate(id)}
            >
              <Icon size={17} />
              <span>{name}</span>
              {active === id && <ChevronRight size={15} />}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <span className="status-dot" />
          DATASET LOADED
          <p>12 verified simulation runs</p>
          <p>LTE · Three-cell topology</p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>{navigation.find(item => item.id === active)?.name ?? "Network Overview"}</strong>
          </div>
          <div className="top-right">
            <span className="data-tag"><Database size={13} /> RECORDED DATA</span>
            <span className="top-identity">PS-016 / LEVEL 2</span>
          </div>
        </header>

        <div className="content">
          <section id="overview" className={`section ${active === "overview" ? "page-active" : "page-hidden"}`}>
            <div className="page-heading">
              <div>
                <div className="eyebrow">CELLULAR MOBILITY INTELLIGENCE</div>
                <h1>Network Overview</h1>
                <p>Benchmarking LTE handover policies under high mobility</p>
              </div>
              <button className="export-button" onClick={exportCSV}>
                <Download size={15} /> Export results
              </button>
            </div>

            <div className="filterbar">
              <div className="filter-title"><Activity size={16} /> Experiment configuration</div>
              <label>
                UE speed
                <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                  <option value={30}>30 km/h</option>
                  <option value={120}>120 km/h</option>
                </select>
              </label>
              <label>
                RNG run
                <select value={run} onChange={(e) => setRun(e.target.value)}>
                  <option value="all">All runs</option>
                  <option value="11">Run 11</option>
                  <option value="12">Run 12</option>
                </select>
              </label>
            </div>

            <div className="kpis">
              <Metric icon={<Database size={18} />} label="Simulation runs"
                value={String(filtered.length)} detail="Selected configurations" />
              <Metric icon={<ArrowLeftRight size={18} />} label="Successful handovers"
                value={String(totalSuccess)} detail="Completed HO events" />
              <Metric icon={<ShieldCheck size={18} />} label="Logged HO failures"
                value={String(totalFailures)} detail="Not service-failure count" />
              <Metric icon={<Zap size={18} />} label="Ping-pong events"
                value={String(totalPingpong)} detail="5-second return window" />
            </div>
          </section>


          <section id="topology" className={`section ${active === "topology" ? "page-active" : "page-hidden"}`}>
            <div className="section-heading">
              <h2>Network Topology & Handover Replay</h2>
              <span>RECORDED SIMULATION</span>
            </div>
            <NetworkTwin runs={data.runs} />
          </section>
          <section id="simulation-control" className={`section ${active === "simulation-control" ? "page-active" : "page-hidden"}`}>
               <div className="section-heading">
                  <h2>Live Simulation Control</h2>
                   <span>NS-3 EXECUTION ENGINE</span>
                  </div>
          <SimulationControl />
         </section>
          <section id="comparison" className={`section ${active === "comparison" ? "page-active" : "page-hidden"}`}>
            <div className="section-heading">
              <h2>Controller Performance</h2>
              <span>AIORI-3 / COMPARATIVE ANALYSIS</span>
            </div>
            <div className="chart-grid">
              <div className="panel">
                <div className="panel-heading">
                  <div>
                    <h3>Application Throughput</h3>
                    <p>Mean received payload rate · Mbps</p>
                  </div>
                  <span className="panel-label">HIGHER IS BETTER</span>
                </div>
                <div className="chart-area">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={comparison} margin={{ top: 8, right: 15, left: -12, bottom: 0 }}>
                      <CartesianGrid stroke="#30343b" vertical={false} />
                      <XAxis dataKey="controller" stroke="#9297a2" fontSize={11} tickLine={false} axisLine={false} />
                      <YAxis stroke="#9297a2" fontSize={11} tickLine={false} axisLine={false} domain={[0, "auto"]} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="throughput" name="Mbps" radius={[3, 3, 0, 0]}
                        fill="#58c9da" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="panel">
                <div className="panel-heading">
                  <div>
                    <h3>Maximum Excess Reception Gap</h3>
                    <p>Mean of per-run maxima · milliseconds</p>
                  </div>
                  <span className="panel-label">LOWER IS BETTER</span>
                </div>
                <div className="chart-area">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={comparison} margin={{ top: 8, right: 15, left: -12, bottom: 0 }}>
                      <CartesianGrid stroke="#30343b" vertical={false} />
                      <XAxis dataKey="controller" stroke="#9297a2" fontSize={11} tickLine={false} axisLine={false} />
                      <YAxis stroke="#9297a2" fontSize={11} tickLine={false} axisLine={false} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="gap" name="Gap (ms)" fill="#ae91ee" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="panel table-panel">
              <div className="panel-heading">
                <div>
                  <h3>Policy Comparison</h3>
                  <p>Measured results for the selected scenario</p>
                </div>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Controller</th>
                      <th>Throughput</th>
                      <th>Max excess gap</th>
                      <th>Successful HOs</th>
                      <th>HO failures</th>
                      <th>Ping-pong</th>
                      <th>Skipped seq.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((r) => (
                      <tr key={r.policy}>
                        <td>
                          <span className="policy-dot" style={{ background: colors[r.policy] }} />
                          {r.controller}
                        </td>
                        <td>{r.throughput.toFixed(4)} Mbps</td>
                        <td>{r.gap.toFixed(1)} ms</td>
                        <td>{r.successes}</td>
                        <td>{r.failures}</td>
                        <td>{r.pingpong}</td>
                        <td>{r.skipped}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <BenchmarkInsights runs={data.runs} speed={speed} />
</section>

          <section id="events" className={`section ${active === "events" ? "page-active" : "page-hidden"}`}>
            <div className="section-heading">
              <h2>Handover Event Explorer</h2>
              <span>RECORDED LTE RRC EVENTS</span>
            </div>
            <div className="panel table-panel">
              <div className="panel-heading">
                <div>
                  <h3>Event History</h3>
                  <p>Timeline from handover_events.csv</p>
                </div>
                <label className="inline-select">
                  Policy
                  <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
                    {policies.map((p) =>
                      <option key={p} value={p}>{labels[p]}</option>
                    )}
                  </select>
                </label>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>RNG run</th>
                      <th>Time</th>
                      <th>Event</th>
                      <th>Cell ID</th>
                      <th>Target cell</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((e, i) => (
                      <tr key={`${e.rng_run}-${i}`}>
                        <td>{e.rng_run}</td>
                        <td>{e.time_s.toFixed(4)} s</td>
                        <td><span className={`event-badge ${e.event === "HO_SUCCESS" ? "success" : ""}`}>
                          {e.event}
                        </span></td>
                        <td>{e.cell_id}</td>
                        <td>{e.target_cell_id ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section id="methodology" className={`section ${active === "methodology" ? "page-active" : "page-hidden"}`}>
            <div className="section-heading">
              <h2>Model & Methodology</h2>
              <span>EXPERIMENTAL DISCLOSURES</span>
            </div>
            <div className="panel methodology">
              <div className="method-item">
                <h3>Simulation topology</h3>
                <p>Three LTE eNBs, one moving UE, 30/120 km/h, paired controller settings with RNG runs 11 and 12.</p>
              </div>
              <div className="method-item">
                <h3>Random Forest status</h3>
                <p>Exploratory model trained on a small related simulation dataset. Predictions and performance have not been independently validated for generalization.</p>
              </div>
              <div className="method-item">
                <h3>Reception gap diagnostic</h3>
                <p>Positive excess over expected sequence-number spacing at a nominal 10 ms packet interval. Not a direct radio outage measurement.</p>
              </div>
              <div className="method-item">
                <h3>Failure interpretation</h3>
                <p>Handover failure values reflect logged events only. End-to-end service failure monitoring has not been fully validated.</p>
              </div>
            </div>
          </section>
          <section
             id="model-evaluation"
             className={`section ${active === "model-evaluation" ? "page-active" : "page-hidden"}`}
            >
           <ModelEvaluation />
           </section>
          <footer>AIORI-3 · PS-016 · MOBI-HO Lab — Evidence-driven cellular handover benchmarking</footer>
        </div>
      </main>
    </div>
  );
}

const tooltipStyle = {
  backgroundColor: "#22252b",
  border: "1px solid #40434a",
  borderRadius: "5px",
  color: "#f1f2f4",
};

function Metric({
  icon, label, value, detail
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="metric">
      <div className="metric-head">{icon}<span>{label}</span></div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </div>
  );
}

