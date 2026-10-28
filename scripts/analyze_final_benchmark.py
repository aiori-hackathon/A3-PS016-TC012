import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path.home() / "MOBI-HO-Lab/results/final_benchmark_v1"
POLICIES = ("a3", "rule", "ml")
SPEEDS = (30, 120)
RUNS = (11, 12)

def load(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path, records, fields):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

# Use the same observation interval for all three policies
# and both RNG runs at each speed.
# Exclude the first second of simulation initialization.
windows = {}

for speed in SPEEDS:
    ends = []
    for run in RUNS:
        for policy in POLICIES:
            folder = ROOT / f"{policy}_speed{speed}_run{run}"
            mobility = load(folder / "mobility.csv")
            ends.append(float(mobility[-1]["time_s"]))

    windows[speed] = (1.0, min(ends))

records = []

for speed in SPEEDS:
    start, end = windows[speed]
    duration = end - start
    assert duration > 0

    for run in RUNS:
        for policy in POLICIES:
            folder = ROOT / f"{policy}_speed{speed}_run{run}"
            packets = load(folder / "packets.csv")
            events = load(folder / "handover_events.csv")

            selected = [
                p for p in packets
                if start <= float(p["time_s"]) < end
            ]

            received_bytes = sum(
                int(p["payload_bytes"]) for p in selected
            )

            throughput = (
                received_bytes * 8 / duration / 1_000_000
            )

            flows = defaultdict(list)

            for p in selected:
                key = (
                    p["imsi"],
                    p["flow_id"],
                    p["direction"]
                )
                flows[key].append(float(p["time_s"]))

            gaps = []

            for times in flows.values():
                times.sort()
                gaps.extend(
                    b - a for a, b in zip(times, times[1:])
                )

            # Diagnostic only: raw reception gaps, not RLFs.
            max_gap = max(gaps, default=0.0)
            gaps_over_100ms = sum(g > 0.1 for g in gaps)

            window_events = [
                e for e in events
                if start <= float(e["time_s"]) < end
            ]

            successes = sum(
                e["event"] == "HO_SUCCESS"
                for e in window_events
            )

            failures = sum(
                e["event"] == "HO_FAILURE"
                for e in window_events
            )

            starts = sum(
                e["event"] == "HO_START"
                for e in window_events
            )

            record = {
                "controller": policy,
                "speed_kmh": speed,
                "rng_run": run,
                "window_start_s": start,
                "window_end_s": end,
                "throughput_mbps": round(throughput, 6),
                "received_packets": len(selected),
                "ho_starts": starts,
                "ho_successes": successes,
                "ho_failures": failures,
                "max_interarrival_gap_s": round(max_gap, 6),
                "gaps_over_100ms": gaps_over_100ms,
                "service_failures": "",
            }

            records.append(record)

fields = list(records[0].keys())

write_csv(
    ROOT / "benchmark_per_run.csv",
    records,
    fields
)

summary = []

for speed in SPEEDS:
    for policy in POLICIES:
        subset = [
            r for r in records
            if r["speed_kmh"] == speed
            and r["controller"] == policy
        ]

        summary.append({
            "controller": policy,
            "speed_kmh": speed,
            "runs": len(subset),
            "mean_throughput_mbps": round(
                statistics.mean(
                    r["throughput_mbps"] for r in subset
                ), 6
            ),
            "total_ho_successes": sum(
                r["ho_successes"] for r in subset
            ),
            "total_ho_failures": sum(
                r["ho_failures"] for r in subset
            ),
            "mean_max_gap_s": round(
                statistics.mean(
                    r["max_interarrival_gap_s"]
                    for r in subset
                ), 6
            ),
            "total_gaps_over_100ms": sum(
                r["gaps_over_100ms"] for r in subset
            ),
        })

summary_fields = list(summary[0].keys())

write_csv(
    ROOT / "benchmark_summary.csv",
    summary,
    summary_fields
)

print("\n=== FINAL BENCHMARK SUMMARY ===")
for r in summary:
    print(
        f"{r['controller']:5s} "
        f"{r['speed_kmh']:3d} km/h | "
        f"Throughput={r['mean_throughput_mbps']:.4f} Mbps | "
        f"HO success={r['total_ho_successes']} | "
        f"HO failure={r['total_ho_failures']} | "
        f"Max gap mean={r['mean_max_gap_s']:.4f} s"
    )

print("\nSaved benchmark_per_run.csv")
print("Saved benchmark_summary.csv")
