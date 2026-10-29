import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parent / "results" / "final_benchmark_v1"
DEST = REPO / "frontend" / "public" / "benchmark.json"

def read(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

summary = read(SOURCE / "benchmark_summary.csv")
per_run = read(SOURCE / "benchmark_per_run.csv")
excess = {
    row["scenario"]: row
    for row in read(SOURCE / "excess_gap_results.csv")
}

runs = []

for row in per_run:
    key = (
        f"{row['controller']}_speed"
        f"{row['speed_kmh']}_run{row['rng_run']}"
    )

    events = read(SOURCE / key / "handover_events.csv")
    gap = excess[key]

    # Completed A -> B -> A returns within five seconds.
    serving = {}
    histories = {}
    pingpong = 0

    for event in sorted(events, key=lambda e: float(e["time_s"])):
        imsi = event["imsi"]
        cell = int(event["cell_id"])
        t = float(event["time_s"])

        if event["event"] == "CONNECTION_ESTABLISHED":
            serving[imsi] = cell

        elif event["event"] == "HO_SUCCESS":
            previous = serving.get(imsi)
            history = histories.setdefault(imsi, [])

            if previous is not None and previous != cell:
                if history:
                    old_t, old_source, old_target = history[-1]
                    if (old_source == cell
                            and old_target == previous
                            and 0 <= t - old_t <= 5):
                        pingpong += 1

                history.append((t, previous, cell))

            serving[imsi] = cell

    runs.append({
        "id": key,
        "controller": row["controller"],
        "speed_kmh": int(row["speed_kmh"]),
        "rng_run": int(row["rng_run"]),
        "throughput_mbps": float(row["throughput_mbps"]),
        "ho_successes": int(row["ho_successes"]),
        "ho_failures": int(row["ho_failures"]),
        "max_excess_gap_ms": float(gap["max_excess_gap_ms"]),
        "gaps_over_5ms": int(gap["excess_gaps_over_5ms"]),
        "skipped_sequences": int(gap["sequence_numbers_skipped"]),
        "pingpong": pingpong,
        "events": [
            {
                "time_s": float(e["time_s"]),
                "cell_id": int(e["cell_id"]),
                "event": e["event"],
                "target_cell_id": (
                    int(e["target_cell_id"])
                    if e["target_cell_id"] else None
                ),
            }
            for e in events
        ],
    })

data = {
    "summary": [
        {
            **{
                k: (
                    float(v) if k in (
                        "mean_throughput_mbps",
                        "mean_max_excess_gap_ms",
                    ) else int(v) if k in (
                        "speed_kmh",
                        "total_ho_successes",
                        "total_ho_failures",
                        "total_pingpong_5s",
                    ) else v
                )
                for k, v in row.items()
            }
        }
        for row in summary
    ],
    "runs": runs,
    "metadata": {
        "source": "Recorded ns-3 LTE simulations",
        "nominal_packet_interval_ms": 10,
        "pingpong_window_s": 5,
        "model_status": "Exploratory RF prototype",
    },
}

DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(json.dumps(data, indent=2) + "\n")

assert len(runs) == 12
assert len(summary) == 6

print(f"PASS: Exported {len(runs)} runs and {len(summary)} summaries")
print(f"Saved: {DEST}")
