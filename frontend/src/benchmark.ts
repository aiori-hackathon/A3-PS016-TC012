import { controllerName, type TwinRun } from "./components/recordedReplay";

export type BenchmarkRun = TwinRun & {
  throughput_mbps: number;
  ho_successes: number;
  ho_failures: number;
  max_excess_gap_ms: number;
  gaps_over_5ms: number;
  skipped_sequences: number;
  pingpong: number;
  pingpong_1s: number;
};

export type Benchmark = {
  runs: BenchmarkRun[];
  metadata: {
    source: string;
    nominal_packet_interval_ms: number;
    pingpong_window_s: number;
    model_status: string;
  };
};

export const policyLabels = controllerName;

export const policyColors: Record<string, string> = {
  a3: "#65dcd2",
  rule: "#89b2f2",
  ml: "#b29af4",
};

export function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

export function summarizeControllers(runs: BenchmarkRun[]) {
  const present = new Set(runs.map(run => run.controller));
  const policies = [...new Set([...Object.keys(policyLabels), ...present])];
  return policies.filter(policy => present.has(policy)).map(policy => {
    const selected = runs.filter(run => run.controller === policy);
    const total = (key: "ho_successes" | "ho_failures" | "pingpong" | "skipped_sequences") =>
      selected.reduce((sum, run) => sum + run[key], 0);
    const firstCompletions = selected.flatMap(run => {
      const successes = run.events.filter(event => event.event === "HO_SUCCESS");
      return successes.length ? [Math.min(...successes.map(event => event.time_s))] : [];
    });
    return {
      policy,
      controller: policyLabels[policy] ?? policy,
      throughput: Number(average(selected.map(run => run.throughput_mbps))!.toFixed(4)),
      gap: Number(average(selected.map(run => run.max_excess_gap_ms))!.toFixed(2)),
      successes: total("ho_successes"),
      failures: total("ho_failures"),
      pingpong: total("pingpong"),
      skipped: total("skipped_sequences"),
      meanGapCount: average(selected.map(run => run.gaps_over_5ms)),
      meanSkipped: average(selected.map(run => run.skipped_sequences)),
      firstCompletion: average(firstCompletions),
    };
  });
}

export type ControllerSummary = ReturnType<typeof summarizeControllers>[number];

export function exportComparison(rows: ControllerSummary[], speed: number, rng: string) {
  const columns = ["controller", "throughput", "gap", "successes", "failures", "pingpong", "skipped"] as const;
  const content = [
    columns.join(","),
    ...rows.map(row => columns.map(column => row[column]).join(",")),
  ].join("\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `mobi-ho-${speed}kmh-${rng}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
