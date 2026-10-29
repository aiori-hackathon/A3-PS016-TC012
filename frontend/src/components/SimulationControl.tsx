
import { useEffect, useState } from "react";
import { Play, Server, CheckCircle2, AlertCircle } from "lucide-react";

type Controller = "a3" | "rule" | "ml";
type JobStatus = "queued" | "running" | "completed" | "failed";

type JobResult = {
  controller: Controller;
  speed_kmh: number;
  rng_run: number;
  ho_starts: number;
  ho_successes: number;
  logged_ho_failures: number;
  received_packets_logged: number;
  handover_events: Array<{
    time_s: string;
    imsi: string;
    cell_id: string;
    event: string;
    target_cell_id: string;
  }>;
};

type Job = {
  job_id: string;
  status: JobStatus;
  error: string | null;
  result: JobResult | null;
};

const API = import.meta.env.VITE_API_BASE_URL as string | undefined;

export default function SimulationControl() {
  const [controller, setController] = useState<Controller>("a3");
  const [speed, setSpeed] = useState(30);
  const [rngRun, setRngRun] = useState(11);

  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const busy = submitting ||
    job?.status === "queued" ||
    job?.status === "running";

  useEffect(() => {
    if (!API || !job?.job_id || !busy || submitting) return;

    const jobId = job.job_id;
    let cancelled = false;

    async function checkStatus() {
      try {
        const response = await fetch(
          `${API}/api/jobs/${jobId}`
        );

        if (!response.ok) {
          throw new Error(`Job status HTTP ${response.status}`);
        }

        const data: Job = await response.json();

        if (!cancelled) {
          setJob(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
        }
      }
    }

    void checkStatus();

    const timer = window.setInterval(() => {
      void checkStatus();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, busy, submitting]);

  async function startSimulation() {
    if (!API || busy) return;

    setError("");
    setJob(null);
    setSubmitting(true);

    try {
      const response = await fetch(`${API}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          controller,
          speed_kmh: speed,
          rng_run: rngRun,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(
          `Simulation request failed (${response.status}): ${detail}`
        );
      }

      const data: { job_id: string; status: JobStatus } =
        await response.json();

      setJob({
        job_id: data.job_id,
        status: data.status,
        error: null,
        result: null,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="sim-control">
      <div className="sim-header">
        <div>
          <h3><Server size={18} /> Simulation Control Center</h3>
          <p>Launch an actual ns-3 LTE handover experiment</p>
        </div>
        <span className="sim-local">LOCAL EXECUTION</span>
      </div>

      {!API && (
        <p className="sim-error">
          Live simulation API is not configured.
          Recorded benchmark visualization remains available.
        </p>
      )}

      <div className="sim-inputs">
        <label>
          Controller
          <select
            value={controller}
            disabled={busy}
            onChange={(e) =>
              setController(e.target.value as Controller)
            }
          >
            <option value="a3">A3-RSRP</option>
            <option value="rule">Rule-based</option>
            <option value="ml">Random Forest</option>
          </select>
        </label>

        <label>
          UE Speed
          <select
            value={speed}
            disabled={busy}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            <option value={30}>30 km/h</option>
            <option value={120}>120 km/h</option>
          </select>
        </label>

        <label>
          RNG Run
          <select
            value={rngRun}
            disabled={busy}
            onChange={(e) => setRngRun(Number(e.target.value))}
          >
            <option value={11}>Run 11</option>
            <option value={12}>Run 12</option>
          </select>
        </label>

        <button
          className="sim-run"
          disabled={!API || busy}
          onClick={() => void startSimulation()}
        >
          <Play size={16} />
          {busy ? "Running…" : "Run Simulation"}
        </button>
      </div>

      {job && (
        <div className="sim-job">
          <div className="sim-job-head">
            <strong>Execution status</strong>
            <span className={`sim-status ${job.status}`}>
              {job.status.toUpperCase()}
            </span>
          </div>

          <p className="sim-id">Job ID: {job.job_id}</p>

          {busy && (
            <p>ns-3 is executing. Checking the job status automatically…</p>
          )}

          {job.status === "failed" && (
            <p className="sim-error">
              <AlertCircle size={15} /> {job.error ?? "Simulation failed"}
            </p>
          )}

          {job.status === "completed" && job.result && (
            <>
              <p className="sim-success">
                <CheckCircle2 size={16} />
                New ns-3 simulation completed successfully
              </p>

              <div className="sim-metrics">
                <div>
                  <small>Handover requests</small>
                  <strong>{job.result.ho_starts}</strong>
                </div>
                <div>
                  <small>Successful handovers</small>
                  <strong>{job.result.ho_successes}</strong>
                </div>
                <div>
                  <small>Logged HO failures</small>
                  <strong>{job.result.logged_ho_failures}</strong>
                </div>
                <div>
                  <small>Received packet records</small>
                  <strong>
                    {job.result.received_packets_logged.toLocaleString()}
                  </strong>
                </div>
              </div>

              <h4>New handover events</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Event</th>
                      <th>Cell</th>
                      <th>Target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.result.handover_events.map((event, index) => (
                      <tr key={index}>
                        <td>{Number(event.time_s).toFixed(3)} s</td>
                        <td>{event.event}</td>
                        <td>{event.cell_id}</td>
                        <td>{event.target_cell_id || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {error && <p className="sim-error">{error}</p>}

      <p className="sim-disclaimer">
        Only approved controllers, speeds and RNG runs are accepted.
        Jobs execute on the local ns-3 backend. New job results are
        separate from the original 12-run benchmark.
      </p>
    </div>
  );
}
