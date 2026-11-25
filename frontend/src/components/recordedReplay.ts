import { useEffect, useMemo, useState } from "react";

export type HandoverEvent = {
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

export type TopologyNode = "ue" | "host" | "epc" | number;
export type FlowMode = "both" | "dl" | "ul" | "off";

export const controllerName: Record<string, string> = {
  a3: "A3-RSRP", ml: "Random Forest", rule: "Rule-based",
};

export function eventLabel(event: HandoverEvent) {
  switch (event.event) {
    case "CONNECTION_ESTABLISHED": return "Connection established";
    case "HO_START": return "Handover started";
    case "HO_SUCCESS": return "Handover completed";
    case "HO_FAILURE": return "Handover failed";
    default: return event.event.replaceAll("_", " ").toLowerCase();
  }
}

export function useRecordedReplay(run: TwinRun, visible: boolean, startTime = 0) {
  const events = useMemo(
    () => [...run.events].sort((a, b) => a.time_s - b.time_s),
    [run.events],
  );
  // The benchmark provides event times. Include a short tail so the final
  // attachment can be inspected after the last recorded transition.
  const duration = Math.max(10, (events.at(-1)?.time_s ?? 0) + 4);
  const [time, setTime] = useState(Math.min(duration, Math.max(0, startTime)));
  const [wantsPlayback, setWantsPlayback] = useState(false);
  const [rate, setRate] = useState(5);
  const playing = wantsPlayback && time < duration;

  useEffect(() => {
    if (!visible || !playing) return;
    let previous = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const step = ((now - previous) / 1000) * rate;
      previous = now;
      setTime(current => Math.min(duration, current + step));
    }, 80);
    return () => window.clearInterval(timer);
  }, [visible, playing, rate, duration]);

  const reached = events.filter(e => e.time_s <= time);
  const association = reached.filter(
    e => e.event === "CONNECTION_ESTABLISHED" || e.event === "HO_SUCCESS",
  ).at(-1);
  const serving = association?.cell_id ?? null;

  function seek(next: number) {
    setWantsPlayback(false);
    setTime(Math.max(0, Math.min(duration, next)));
  }

  function togglePlayback() {
    if (time >= duration) setTime(0);
    setWantsPlayback(!playing);
  }

  return { time, rate, setRate, playing, togglePlayback, seek, events, reached, serving, duration };
}
