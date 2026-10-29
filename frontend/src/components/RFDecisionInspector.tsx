import DonutBreakdown from "./DonutBreakdown";
import { useEffect, useMemo, useState } from "react";
import { BrainCircuit, CheckCircle2, Clock3 } from "lucide-react";

type Decision = {
  time_s: number;
  imsi: number;
  serving_cell: number;
  candidate_cell: number;
  rsrp_delta_db: number;
  valid: boolean;
  handover_score: number | null;
  action: "STAY" | "HANDOVER" | "INVALID";
  ho_completed_at_s: number | null;
};

type DecisionData = Record<string, Decision[]>;

type Props = {
  selectedRunId: string;
  replayTime: number;
};

export default function RFDecisionInspector({
  selectedRunId,
  replayTime,
}: Props) {
  const [data, setData] = useState<DecisionData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(import.meta.env.VITE_API_BASE_URL ? `${import.meta.env.VITE_API_BASE_URL}/api/rf-decisions` : `${import.meta.env.BASE_URL}rf_decisions.json`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("RF decision export is missing");
        }
        return response.json() as Promise<DecisionData>;
      })
      .then(setData)
      .catch((err) => setError(String(err)));
  }, []);

  const decisions = useMemo(
    () => data?.[selectedRunId] ?? [],
    [data, selectedRunId]
  );

  const visible = useMemo(
    () => decisions.filter((d) => d.time_s <= replayTime),
    [decisions, replayTime]
  );

  const current = visible.at(-1);

  if (!selectedRunId.startsWith("ml_")) {
    return (
      <section className="rf-inspector">
        <h3><BrainCircuit size={17} /> AI Decision Inspector</h3>
        <p>
          Select a Random Forest simulation in the Network
          Digital Twin to inspect recorded ML decisions.
          A3 and Rule-based use different policies.
        </p>
      </section>
    );
  }

  return (
    <section className="rf-inspector">
      <div className="rf-header">
        <div>
          <h3><BrainCircuit size={17} /> AI Decision Inspector</h3>
          <p>Autonomous Random Forest · Recorded ns-3 inference</p>
        </div>
        <span className="rf-mode">RF PROTOTYPE</span>
      </div>

      {error && <p className="rf-error">{error}</p>}

      {!error && !data && <p>Loading recorded RF decisions…</p>}

      {data && (
        <>

          <DonutBreakdown
            title="RF Decision Distribution"
            subtitle="All recorded recommendations in this selected simulation"
            items={[
              {
                name: "STAY",
                value: decisions.filter(d => d.action === "STAY").length,
                color: "#edae83",
              },
              {
                name: "HANDOVER",
                value: decisions.filter(d => d.action === "HANDOVER").length,
                color: "#59d9b6",
              },
              {
                name: "INVALID",
                value: decisions.filter(d => d.action === "INVALID").length,
                color: "#ed8b84",
              },
            ]}
          />

          <div className="rf-stats">
            <div>
              <small>Decisions in run</small>
              <strong>{decisions.length}</strong>
            </div>
            <div>
              <small>Decisions reached in replay</small>
              <strong>{visible.length}</strong>
            </div>
            <div>
              <small>Current replay time</small>
              <strong>{replayTime.toFixed(1)} s</strong>
            </div>
          </div>

          {!current ? (
            <p className="rf-empty">
              <Clock3 size={15} />
              No RF decision yet at this replay time.
              Press Play or seek forward.
            </p>
          ) : (
            <>
              <div className="rf-current">
                <div>
                  <small>Last recorded recommendation</small>
                  <strong className="rf-action">
                    {current.action}
                  </strong>
                </div>
                <div>
                  <small>Serving → Candidate</small>
                  <strong>
                    Cell {current.serving_cell} → {current.candidate_cell}
                  </strong>
                </div>
                <div>
                  <small>HANDOVER score</small>
                  <strong>
                    {current.handover_score === null
                      ? "N/A"
                      : current.handover_score.toFixed(6)}
                  </strong>
                </div>
                <div>
                  <small>RSRP delta</small>
                  <strong>{current.rsrp_delta_db.toFixed(3)} dB</strong>
                </div>
                <div>
                  <small>Decision timestamp</small>
                  <strong>{current.time_s.toFixed(3)} s</strong>
                </div>
                <div>
                  <small>Prediction validity</small>
                  <strong>{current.valid ? "Valid" : "Invalid"}</strong>
                </div>
              </div>

              <p className="rf-completion">
                <CheckCircle2 size={15} />
                {current.action !== "HANDOVER"
                  ? "No handover requested by this recommendation"
                  : current.ho_completed_at_s === null
                    ? "No matching completed HO recorded within 1 second"
                    : current.ho_completed_at_s <= replayTime
                      ? `HO completed at ${current.ho_completed_at_s.toFixed(4)} s`
                      : `HO completion recorded at ${current.ho_completed_at_s.toFixed(4)} s (ahead in replay)`}
              </p>
            </>
          )}

          <div className="rf-table-wrap">
            <table className="rf-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Cells</th>
                  <th>RSRP Δ</th>
                  <th>Score</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {visible.slice(-12).reverse().map((d, i) => (
                  <tr key={`${d.time_s}-${i}`}>
                    <td>{d.time_s.toFixed(2)}s</td>
                    <td>{d.serving_cell} → {d.candidate_cell}</td>
                    <td>{d.rsrp_delta_db.toFixed(3)} dB</td>
                    <td>
                      {d.handover_score === null
                        ? "N/A"
                        : d.handover_score.toFixed(4)}
                    </td>
                    <td>
                      <span className={
                        d.action === "HANDOVER"
                          ? "rf-hand"
                          : "rf-stay"
                      }>
                        {d.action}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="rf-disclaimer">
        Scores are exploratory model outputs, not calibrated
        confidence or network success probabilities.
        Completion times are matched against recorded HO_SUCCESS events.
      </p>
    </section>
  );
}
