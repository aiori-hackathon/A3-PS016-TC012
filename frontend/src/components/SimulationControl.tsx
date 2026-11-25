import { useEffect, useState } from "react";
import { Activity, AlertTriangle, ArrowLeftRight, ArrowUpRight, Check, ChevronDown, Clock3, LoaderCircle, Play, RadioTower, Server, Settings2, Terminal, Unplug } from "lucide-react";
import { controllerName } from "./recordedReplay";
import "./inspection.css";

type Controller = "a3" | "rule" | "ml" | "xgboost" | "logistic";
type JobStatus = "queued" | "running" | "completed" | "failed";
type JobResult = {
  controller: Controller;
  speed_kmh: number;
  rng_run: number;
  ho_starts: number;
  ho_successes: number;
  logged_ho_failures: number;
  received_packets_logged: number;
  handover_events: { time_s: string; imsi: string; cell_id: string; event: string; target_cell_id: string }[];
};
type Job = {
  job_id: string;
  status: JobStatus;
  error: string | null;
  result: JobResult | null;
};

const API = import.meta.env.VITE_API_BASE_URL as string | undefined;
const jobTitles: Record<JobStatus, string> = {
  queued: "Job queued", running: "Simulation running", completed: "Simulation completed", failed: "Simulation failed",
};

function JobOutput({ result }: { result: JobResult }) {
  const metrics = [
    ["Handover starts", result.ho_starts], ["Completed handovers", result.ho_successes],
    ["Logged HO failures", result.logged_ho_failures], ["Received packet records", result.received_packets_logged],
  ] as const;
  return <section className="inspect-card sim-output">
    <div className="inspect-head"><h2><ArrowLeftRight size={17}/>Job results</h2>
      <span className="inspect-aside">{result.controller === "xgboost" ? "XGBoost" : result.controller === "logistic" ? "Logistic Regression" : controllerName[result.controller]} · {result.speed_kmh} km/h · Run {result.rng_run}</span>
    </div>
    <div className="sim-metrics">
      {metrics.map(([name, value]) => <div key={name}><span>{name}</span><strong>{value.toLocaleString()}</strong></div>)}
    </div>
    <details className="inspect-details">
      <summary>Recorded events <span>{result.handover_events.length} entries <ChevronDown size={14}/></span></summary>
      {result.handover_events.length ? <div className="inspect-table-wrap" role="region" aria-label="Live job handover events" tabIndex={0}><table>
        <thead><tr><th>Time (s)</th><th>Event</th><th>UE (IMSI)</th><th>Cell</th><th>Target</th></tr></thead>
        <tbody>{result.handover_events.map((event, i) =>
          <tr key={i}><td>{Number(event.time_s).toFixed(4)}</td><td>{event.event}</td><td>{event.imsi}</td>
            <td>{event.cell_id}</td><td>{event.target_cell_id || "—"}</td></tr>)}</tbody>
      </table></div> : <p className="inspect-empty">No events were logged for this job.</p>}
    </details>
  </section>;
}

export default function SimulationControl() {
  const [controller, setController] = useState<Controller>("a3");
  const [speed, setSpeed] = useState(30);
  const [rngRun, setRngRun] = useState(11);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [missingJob, setMissingJob] = useState(false);
  const activeJob = !missingJob && (job?.status === "queued" || job?.status === "running");
  const busy = submitting || activeJob;

  useEffect(() => {
    if (!API || !job?.job_id || !activeJob) return;
    const jobId = job.job_id;
    const abort = new AbortController();
    let timeout: number | undefined;
    async function poll() {
      try {
        const response = await fetch(`${API}/api/jobs/${jobId}`, { signal: abort.signal });
        if (!response.ok) {
          if (response.status === 404) {
            setMissingJob(true);
            setError("The server no longer has a record of this job.");
            return;
          }
          throw new Error(`Job status returned HTTP ${response.status}.`);
        }
        const latest: Job = await response.json();
        if (abort.signal.aborted) return;
        setJob(latest);
        setError("");
        if (latest.status === "completed" || latest.status === "failed") return;
      } catch (err) {
        if (abort.signal.aborted) return;
        setError(`Status check interrupted. Retrying. ${err instanceof Error ? err.message : String(err)}`);
      }
      timeout = window.setTimeout(poll, 1500);
    }
    void poll();
    return () => { abort.abort(); window.clearTimeout(timeout); };
  }, [job?.job_id, activeJob]);

  async function startSimulation() {
    if (!API || busy) return;
    setSubmitting(true);
    setError("");
    setJob(null);
    setMissingJob(false);
    try {
      const response = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ controller, speed_kmh: speed, rng_run: rngRun }),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(`Simulation request failed (HTTP ${response.status}). ${message}`);
      }
      const data: Pick<Job, "job_id" | "status"> = await response.json();
      setJob({ ...data, error: null, result: null });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const status = missingJob ? "unavailable" : job?.status ?? (submitting ? "submitting" : "idle");
  const StatusIcon = busy ? LoaderCircle : status === "completed" ? Check :
    status === "failed" || status === "unavailable" ? AlertTriangle : API ? Terminal : Unplug;
  const title = missingJob ? "Job record unavailable" : job ? jobTitles[job.status] :
    submitting ? "Submitting request" : API ? "Awaiting a job" : "Simulation server required";
  const busyTitle = submitting ? "Submitting…" : job?.status === "queued" ? "Queued…" : "Running…";

  return <div className="inspection-pages sim-control">
    <div className="sim-workbench">
      <form className="inspect-card" onSubmit={e => { e.preventDefault(); void startSimulation(); }}>
        <div className="inspect-head"><h2><Settings2 size={17}/>Experiment configuration</h2></div>
        <fieldset className="sim-inputs" disabled={!API || busy}>
          <legend className="inspect-visually-hidden">Simulation parameters</legend>
          <label className="sim-controller">Handover controller
            <select value={controller} onChange={e => setController(e.target.value as Controller)}>
              <option value="a3">A3-RSRP</option><option value="rule">Rule-based</option><option value="ml">Random Forest</option>
              <option value="xgboost">XGBoost</option>
              <option value="logistic">Logistic Regression</option>
            </select>
          </label>
          <label>UE speed<select value={speed} onChange={e => setSpeed(Number(e.target.value))}>
            <option value={30}>30 km/h</option><option value={120}>120 km/h</option>
          </select></label>
          <label>RNG run<select value={rngRun} onChange={e => setRngRun(Number(e.target.value))}>
            <option value={11}>Run 11</option><option value={12}>Run 12</option>
          </select></label>
        </fieldset>
        <div className="sim-form-foot">
          <span><RadioTower size={15}/>3 LTE cells · 1 UE</span>
          <button type="submit" className="sim-run" disabled={!API || busy}>
            {busy ? <LoaderCircle size={16} className="inspect-spin"/> : <Play size={15}/>}
            {busy ? busyTitle : "Run simulation"}
          </button>
        </div>
      </form>
      <section className="inspect-card sim-monitor" aria-label="Job monitor">
        <div className="inspect-head"><h2><Activity size={17}/>Job monitor</h2>
          <span className="inspect-aside"><Server size={13}/>{API ? "API configured" : "Recorded mode"}</span>
        </div>
        <div className={`sim-job-status ${status}`}>
          <div className="sim-state-icon"><StatusIcon size={22} className={busy ? "inspect-spin" : ""}/></div>
          <strong role="status" aria-live="polite">{title}</strong>
          {job && <small className="sim-id">Job <code>{job.job_id}</code></small>}
          {!job && !busy && (API ? <p>Submit an experiment to follow its execution here.</p> :
            <><p>Connect the ns-3 backend to run new experiments.</p><a className="inspect-link" href="#topology">Explore a recorded replay <ArrowUpRight size={13}/></a></>)}
          {activeJob && <span className="sim-poll"><Clock3 size={13}/>Checking server status</span>}
        </div>
        {(error || job?.status === "failed") && <p className="sim-error" role="alert"><AlertTriangle size={16}/>
          {error || job?.error || "The simulation failed."}</p>}
      </section>
    </div>
    {job?.status === "completed" && job.result && <JobOutput result={job.result}/>}
  </div>;
}
