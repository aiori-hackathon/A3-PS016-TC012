import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parent / "results" / "final_benchmark_v1"
DEST = REPO / "frontend/public/rf_decisions.json"

def read_events(path):
    with path.open(newline="") as file:
        return list(csv.DictReader(file))

export = {}
total = 0

for speed in (30, 120):
    for run in (11, 12):
        name = f"ml_speed{speed}_run{run}"
        folder = SOURCE / name
        log_path = folder / "simulation.log"
        events_path = folder / "handover_events.csv"

        if not log_path.is_file() or not events_path.is_file():
            raise SystemExit(f"Missing benchmark data: {name}")

        decisions = []
        events = read_events(events_path)

        for line in log_path.read_text().splitlines():
            if "RF AUTONOMOUS " not in line:
                continue

            # Extract key=value fields from actual simulator logs.
            fields = {}
            for token in line.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key] = value

            required = (
                "time", "imsi", "serving", "candidate",
                "delta", "valid", "action"
            )

            if any(key not in fields for key in required):
                raise ValueError(f"Malformed RF log: {line}")

            score = (
                float(fields["probability"])
                if "probability" in fields else None
            )

            timestamp = float(fields["time"])
            candidate = int(fields["candidate"])
            action = fields["action"]

            if action not in ("STAY", "HANDOVER", "INVALID"):
                raise ValueError(f"Unknown action: {action}")

            completed_at = None

            if action == "HANDOVER":
                # Match a subsequent recorded successful HO.
                matches = [
                    float(event["time_s"])
                    for event in events
                    if event["event"] == "HO_SUCCESS"
                    and int(event["imsi"]) == int(fields["imsi"])
                    and int(event["cell_id"]) == candidate
                    and timestamp <= float(event["time_s"])
                    <= timestamp + 1.0
                ]

                if matches:
                    completed_at = min(matches)

            decisions.append({
                "time_s": timestamp,
                "imsi": int(fields["imsi"]),
                "serving_cell": int(fields["serving"]),
                "candidate_cell": candidate,
                "rsrp_delta_db": float(fields["delta"]),
                "valid": fields["valid"] == "1",
                "handover_score": score,
                "action": action,
                "ho_completed_at_s": completed_at,
            })

        export[name] = decisions
        total += len(decisions)
        print(f"{name}: {len(decisions)} RF decisions")

if total == 0:
    raise SystemExit("ERROR: No RF AUTONOMOUS records found")

DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(json.dumps(export, indent=2) + "\n")

print(f"\nPASS: Exported {total} real RF decisions")
print(f"Saved: {DEST}")
