import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, Radio, RotateCcw, SlidersHorizontal } from "lucide-react";
import { type Benchmark, exportComparison, summarizeControllers } from "./benchmark";
import { pageFromHash, type PageId } from "./pages";
import WorkspaceNav from "./components/WorkspaceNav";
import NetworkOverview from "./components/NetworkOverview";
import NetworkTwin from "./components/NetworkTwin";
import BenchmarkInsights from "./components/BenchmarkInsights";
import ModelEvaluation from "./components/ModelEvaluation";
import SimulationControl from "./components/SimulationControl";
import { Events, Methodology } from "./components/BenchmarkPages";
import "./App.css";
import "./workspace.css";

const api = import.meta.env.VITE_API_BASE_URL;

export default function App() {
  const [data, setData] = useState<Benchmark | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [speed, setSpeed] = useState(120);
  const [rng, setRng] = useState("all");
  const [page, setPage] = useState(pageFromHash);
  const [replay, setReplay] = useState({ id: "", time: 0, revision: 0 });
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const abort = new AbortController();
    fetch(api ? `${api}/api/benchmark` : `${import.meta.env.BASE_URL}benchmark.json`, { signal: abort.signal })
      .then(response => {
        if (!response.ok) throw new Error(`Benchmark request returned HTTP ${response.status}`);
        return response.json() as Promise<Benchmark>;
      })
      .then(benchmark => {
        setData(benchmark);
        setSpeed(current => benchmark.runs.some(r => r.speed_kmh === current) ? current : benchmark.runs[0]?.speed_kmh ?? current);
      })
      .catch((err: Error) => { if (!abort.signal.aborted) setError(err.message); });
    return () => abort.abort();
  }, [reload]);

  useEffect(() => {
    const onLocation = () => {
      setPage(pageFromHash());
      window.scrollTo({ top: 0, behavior: "instant" });
      mainRef.current?.focus({ preventScroll: true });
    };
    window.addEventListener("hashchange", onLocation);
    return () => window.removeEventListener("hashchange", onLocation);
  }, []);

  useEffect(() => { document.title = `${page.title} · MOBI-HO Lab`; }, [page.title]);

  function navigate(id: PageId) {
    if (window.location.hash.slice(1) !== id) window.location.hash = id;
    else window.scrollTo({ top: 0, behavior: "instant" });
  }

  function openReplay(id: string, time = 0) {
    setReplay(previous => ({ id, time, revision: previous.revision + 1 }));
    navigate("topology");
  }

  if (error || !data) {
    return <main className="loading" role={error ? "alert" : "status"}>
      <Radio className="loading-radio" size={38}/><h1>{error ? "Benchmark unavailable" : "Opening the workspace"}</h1>
      <p>{error || "Loading recorded benchmark data…"}</p>
      {error && <button className="primary-action" onClick={() => { setError(""); setReload(n => n + 1); }}><RotateCcw size={15}/>Try again</button>}
    </main>;
  }

  const speeds = [...new Set(data.runs.map(r => r.speed_kmh))].sort((a, b) => a - b);
  const availableRng = [...new Set(data.runs.filter(r => r.speed_kmh === speed).map(r => r.rng_run))].sort((a, b) => a - b);
  const sameRng = data.runs.filter(r => rng === "all" || r.rng_run === Number(rng));
  const filtered = sameRng.filter(r => r.speed_kmh === speed);
  const summaries = summarizeControllers(filtered);
  const hasFilters = ["overview", "comparison", "events"].includes(page.id);

  return <div className="shell">
    <WorkspaceNav page={page} navigate={navigate} apiConnected={Boolean(api)} runCount={data.runs.length}/>
    <main className="main" id="workspace-content" ref={mainRef} tabIndex={-1}>
      <div className="content">
        <div className="page-heading" key={page.id}>
          <div><h1>{page.title}</h1><p>{page.description}</p></div>
          {(page.id === "overview" || page.id === "comparison") &&
            <button className="primary-action export-button" disabled={!filtered.length} onClick={() => exportComparison(summaries, speed, rng)}>
              <Download size={15}/>Export CSV
            </button>}
        </div>
        {hasFilters && <div className="filterbar" aria-label="Scenario filters">
          <div className="filter-scope"><SlidersHorizontal size={16}/><span>Scenario</span></div>
          <span className="filter-divider"/>
          <div className="speed-filter"><span>UE speed</span><div className="segmented" role="group" aria-label="UE speed">
            {speeds.map(s => <button type="button" key={s} aria-pressed={s === speed} onClick={() => {
              setSpeed(s);
              if (rng !== "all" && !data.runs.some(r => r.speed_kmh === s && r.rng_run === Number(rng))) setRng("all");
            }}>{s} <small>km/h</small></button>)}
          </div></div>
          <label className="rng-filter"><span>RNG run</span><span className="select-wrap"><select value={rng} onChange={event => setRng(event.target.value)}>
            <option value="all">All runs</option>
            {availableRng.map(n => <option value={n} key={n}>Run {n}</option>)}
          </select><ChevronDown size={13}/></span></label>
          <span className="scope-count"><i/>{filtered.length} of {data.runs.length} runs</span>
        </div>}
        {page.id === "overview" && <NetworkOverview runs={filtered} summaries={summaries} pingpongWindow={data.metadata.pingpong_window_s}
          onReplay={openReplay} onCompare={() => navigate("comparison")}/>}
        <div hidden={page.id !== "topology"}>
          <NetworkTwin key={replay.revision} runs={data.runs} initialRunId={replay.id} initialTime={replay.time} visible={page.id === "topology"}/>
        </div>
        {page.id === "comparison" && <BenchmarkInsights runs={sameRng} speed={speed} summaries={summaries}/>}
        {page.id === "events" && <Events runs={filtered} onReplay={openReplay}/>}
        {page.id === "methodology" && <Methodology benchmark={data}/>}
        {page.id === "model-evaluation" && <ModelEvaluation/>}
        <div hidden={page.id !== "simulation-control"}><SimulationControl/></div>
        <footer className="workspace-footer"><span><Radio size={13}/>MOBI-HO Lab</span><span>AIORI-3 <i/> PS-016</span></footer>
      </div>
    </main>
  </div>;
}
