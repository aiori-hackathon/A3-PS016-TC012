import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

BASE = Path.home() / "MOBI-HO-Lab"
NS3 = BASE / "ns-3.46.1"

CONTROLLERS = {
    "a3": "mobi-ho-integrated",
    "rule": "mobi-ho-rf",
    "ml": "mobi-ho-rf-live",
}

FILES = [
    "radio_measurements.csv",
    "handover_events.csv",
    "mobility.csv",
    "traffic_rx.csv",
    "packets.csv",
]

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run_case(output_root, policy, speed, run):
    name = f"{policy}_speed{speed}_run{run}"
    folder = output_root / name

    if folder.exists():
        raise RuntimeError(f"Refusing to overwrite {folder}")

    folder.mkdir(parents=True)

    program = CONTROLLERS[policy]
    source = NS3 / "scratch" / f"{program}.cc"

    options = (
        f"scratch/{program} "
        "--numberOfUes=1 "
        "--numberOfEnbs=3 "
        f"--speedKmh={speed} "
        "--rngSeed=1 "
        f"--rngRun={run} "
        "--disableDl=0 "
        "--disableUl=0"
    )

    if policy == "ml":
        options += " --pilotAction=none"

    command = ["./ns3", "run", options]

    result = subprocess.run(
        command,
        cwd=NS3,
        capture_output=True,
        text=True,
    )

    (folder / "simulation.log").write_text(
        result.stdout + "\n" + result.stderr
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed: see {folder / 'simulation.log'}"
        )

    for filename in FILES:
        src = NS3 / filename

        if not src.is_file():
            raise FileNotFoundError(
                f"{name}: missing {filename}"
            )

        shutil.copy2(src, folder / filename)

    metadata = {
        "controller": policy,
        "program": program,
        "speed_kmh": speed,
        "rng_seed": 1,
        "rng_run": run,
        "number_of_ues": 1,
        "number_of_enbs": 3,
        "disable_dl": False,
        "disable_ul": False,
        "command": command,
        "source_sha256": sha256(source),
    }

    if policy == "ml":
        metadata["model_header_sha256"] = sha256(
            NS3 / "scratch/rf_prototype.hpp"
        )
        metadata["model_status"] = (
            "exploratory_integration_prototype"
        )

    (folder / "run_config.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )

    print(f"PASS: {name}", flush=True)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--smoke", action="store_true",
    help="Three-controller test at 30 km/h, run 11"
)
args = parser.parse_args()

if args.smoke:
    output = BASE / "results/final_benchmark_smoke"
    scenarios = [(30, 11)]
else:
    output = BASE / "results/final_benchmark_v1"
    scenarios = [
        (speed, run)
        for speed in (30, 120)
        for run in (11, 12)
    ]

for speed, run in scenarios:
    for policy in CONTROLLERS:
        run_case(output, policy, speed, run)

print(f"\nSUCCESS: benchmark data saved in {output}")
