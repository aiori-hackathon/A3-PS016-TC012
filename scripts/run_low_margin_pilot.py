
from pathlib import Path
import csv
import json
import shutil
import subprocess

ROOT = Path.home() / "MOBI-HO-Lab"
NS3 = ROOT / "ns-3.46.1"
OUTPUT = ROOT / "results" / "low_margin_pilot_v2"

SCENARIOS = [
    # speed, RNG run, boundary, decision time
    (30, 11, 1, 12.5),  # 0-1 dB
    (30, 11, 1, 13.5),  # 1-3 dB
    (30, 11, 2, 36.5),  # 0-1 dB
    (30, 11, 2, 37.5),  # 1-3 dB

    (30, 12, 1, 12.5),
    (30, 12, 1, 13.5),
    (30, 12, 2, 36.5),
    (30, 12, 2, 37.5),

    (120, 11, 1, 3.3),
    (120, 11, 1, 3.5),
    (120, 11, 2, 9.3),
    (120, 11, 2, 9.5),

    (120, 12, 1, 3.3),
    (120, 12, 1, 3.5),
    (120, 12, 2, 9.3),
    (120, 12, 2, 9.5),
]

FILES = [
    "radio.csv",
    "mobility.csv",
    "handovers.csv",
    "packets.csv",
    "traffic.csv",
    
    "pilot_decision_features.csv",
]

def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def execute(speed, run, boundary, decision_time, action):
    name = (
    f"speed{speed}_run{run}_b{boundary}"
    f"_t{str(decision_time).replace('.', 'p')}_{action}"
      )
    folder = OUTPUT / name
    folder.mkdir(parents=True, exist_ok=True)

    command = (
        "scratch/mobi-ho-paired "
        f"--speedKmh={speed} "
        "--rngSeed=1 "
        f"--rngRun={run} "
        f"--pilotAction={action} "
        f"--pilotBoundary={boundary} "
        f"--pilotDecisionTime={decision_time}"
    )

    result = subprocess.run(
        ["./ns3", "run", command],
        cwd=NS3,
        capture_output=True,
        text=True,
    )

    (folder / "simulation.log").write_text(
        result.stdout + "\n" + result.stderr
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Simulation failed: {name}. Check simulation.log"
        )

    if f"PILOT DECISION: {action.upper()}" not in result.stdout:
        raise RuntimeError(
            f"Pilot action did not activate: {name}"
        )

    for filename in FILES:
        source = NS3 / filename

        if not source.exists():
            raise FileNotFoundError(
                f"Missing {filename} for {name}"
            )

        shutil.copy2(source, folder / filename)

    features = read_csv(folder / "pilot_decision_features.csv")

    if len(features) != 1:
        raise RuntimeError(
            f"Expected 1 feature row: {name}"
        )

    row = features[0]

    if (
        row["pilot_action"] != action
        or int(row["serving_cell_id"]) != boundary
        or abs(float(row["decision_time_s"]) - decision_time) > 1e-6
    ):
        raise RuntimeError(
            f"Feature record mismatch: {name}"
        )

    config = {
        "speed_kmh": speed,
        "rng_seed": 1,
        "rng_run": run,
        "boundary": boundary,
        "decision_time_s": decision_time,
        "action": action,
        "horizon_s": 1.0,
        "action_hold_s": 0.2,
    }

    (folder / "run_config.json").write_text(
        json.dumps(config, indent=2)
    )

    return folder, row

def validate_pair(stay_folder, ho_folder, stay_row, ho_row, time):
    a = dict(stay_row)
    b = dict(ho_row)

    a.pop("pilot_action")
    b.pop("pilot_action")

    if a != b:
        raise RuntimeError("Paired feature records differ")

    for filename in (
        "radio.csv",
        "mobility.csv",
        "handovers.csv",
        "packets.csv",
    ):
        def prefix(folder):
            return [
                row for row in read_csv(folder / filename)
                if float(row["time_s"]) < time
            ]

        if prefix(stay_folder) != prefix(ho_folder):
            raise RuntimeError(
                f"Paired histories differ: {filename}"
            )

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for speed, run, boundary, time in SCENARIOS:
        print(
            f"\nTesting speed={speed}, "
            f"run={run}, boundary={boundary}",
            flush=True,
        )

        stay_folder, stay_row = execute(
            speed, run, boundary, time, "stay"
        )

        ho_folder, ho_row = execute(
            speed, run, boundary, time, "handover"
        )

        validate_pair(
            stay_folder, ho_folder,
            stay_row, ho_row, time
        )

        print("PASS: Matched pilot pair", flush=True)

    print("\nSUCCESS: All 32 low-margin rollouts saved and validated.")

if __name__ == "__main__":
    main()

