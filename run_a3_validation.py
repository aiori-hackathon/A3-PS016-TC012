
#!/usr/bin/env python3
"""Generate and evaluate four real ns-3 A3 validation runs."""

import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path.home() / "MOBI-HO-Lab"
NS3 = ROOT / "ns-3.46.1"
REPO = ROOT / "A3-PS016-TC012"
RESULTS = ROOT / "results"
SOURCE = NS3 / "scratch/mobi-ho-integrated.cc"

CSV_FILES = [
    "radio.csv",
    "mobility.csv",
    "handovers.csv",
    "packets.csv",
    "traffic.csv",
]

FIELDS = [
    "run_id", "policy", "split", "scenario_id",
    "config_id", "pair_id", "seed", "rng_run",
    "speed_kmh", "ns3_version", "radio_model",
    "git_commit", "observation_start_s",
    "observation_end_s", "synthetic",
]

EXPERIMENTS = [
    (30, 11),
    (30, 12),
    (120, 11),
    (120, 12),
]


def execute(command, cwd, log_path=None):
    print("RUN:", " ".join(map(str, command)), flush=True)

    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if log_path:
        log_path.write_text(result.stdout)

    if result.returncode != 0:
        print(result.stdout[-4000:])
        raise RuntimeError(
            f"Command failed: {' '.join(map(str, command))}"
        )

    return result.stdout


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    commit = execute(
        ["git", "rev-parse", "HEAD"], REPO
    ).strip()

    # Ensure the simulator matches the exact committed source.
    committed_source = subprocess.run(
        ["git", "show", "HEAD:src/ns3/mobi-ho-integrated.cc"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout

    if SOURCE.read_bytes() != committed_source:
        raise RuntimeError(
            "The local ns-3 simulator differs from the "
            "committed GitHub version. Commit and sync "
            "the source before running experiments."
        )

    source_hash = sha256(SOURCE)

    print("Git commit:", commit)
    print("Simulator SHA256:", source_hash)

    for speed, rng_run in EXPERIMENTS:
        seed = 1
        run_id = f"a3_linear_{speed}_s{seed}_r{rng_run}"
        folder = RESULTS / run_id

        # Never silently overwrite an existing experiment.
        if folder.exists():
            raise FileExistsError(
                f"{folder} already exists. "
                "Preserve or move it before rerunning."
            )

        folder.mkdir(parents=True)

        # Matches the current C++ simTime formula.
        sim_time = 450.0 / (speed / 3.6) + 2.0

        command = [
            "./ns3",
            "run",
            (
                "scratch/mobi-ho-integrated "
                f"--speedKmh={speed} "
                f"--rngSeed={seed} "
                f"--rngRun={rng_run}"
            ),
        ]

        print(f"\n=== {run_id} ===", flush=True)

        execute(
            command,
            NS3,
            folder / "simulation.log",
        )

        # Archive simulator output immediately.
        for filename in CSV_FILES:
            source_file = NS3 / filename

            if not source_file.is_file():
                raise FileNotFoundError(source_file)

            shutil.copy2(source_file, folder / filename)

        metadata = {
            "run_id": run_id,
            "policy": "a3",
            "split": "validation",
            "scenario_id": "linear",
            "config_id": "lte3cell_linear_200m_udp10ms_v1",
            "pair_id": f"linear_{speed}_s{seed}_r{rng_run}",
            "seed": seed,
            "rng_run": rng_run,
            "speed_kmh": speed,
            "ns3_version": "3.46.1",
            "radio_model": "ns-3 LTE/EPC",
            "git_commit": commit,
            "observation_start_s": 0.0,
            "observation_end_s": sim_time,
            "synthetic": "false",
        }

        with (folder / "run.csv").open(
            "w", newline=""
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=FIELDS
            )
            writer.writeheader()
            writer.writerow(metadata)

        settings = {
            "run_id": run_id,
            "command": command,
            "cwd": str(NS3),
            "git_commit": commit,
            "simulator_source_sha256": source_hash,
            "speed_kmh": speed,
            "rng_seed": seed,
            "rng_run": rng_run,
            "configured_udp_interval_s": 0.01,
            "lte_scheduler": "ns3::RrFfMacScheduler",
            "simulation_time_s": sim_time,
            "simulator_stop_time_s": sim_time + 0.02,
            "observation_start_s": 0.0,
            "observation_end_s": sim_time,
            "rng_stream_assignments": (
                "Not explicitly documented; verify "
                "ns-3 object stream assignments."
            ),
            "radio_channel_configuration": (
                "Inspect committed simulator and resolved "
                "ns-3 defaults before final reporting."
            ),
            "measurement_window_note": (
                "Initial integration convention includes "
                "traffic startup. Review before final evaluation."
            ),
        }

        (folder / "run_config.json").write_text(
            json.dumps(settings, indent=2) + "\n"
        )

        execute(
            [
                "python3", "-m", "aiori_pipeline",
                "validate", str(folder),
            ],
            REPO,
            folder / "validation.log",
        )

        output = REPO / "output" / run_id

        execute(
            [
                "python3", "-m", "aiori_pipeline",
                "process", str(folder),
                "--output", str(output),
            ],
            REPO,
            folder / "processing.log",
        )

        print(f"SUCCESS: {run_id}", flush=True)

    print("\nAll four A3 validation runs completed.")


if __name__ == "__main__":
    main()
