import csv
import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

REPO = Path(__file__).resolve().parents[1]
NS3 = REPO.parent / "ns-3.46.1"
OUTPUT = REPO / "backend" / "job_results"

PROGRAMS = {
    "a3": "mobi-ho-integrated",
    "rule": "mobi-ho-rf",
    "ml": "mobi-ho-rf-live",
}

OUTPUT_FILES = (
    "radio_measurements.csv",
    "handover_events.csv",
    "mobility.csv",
    "traffic_rx.csv",
    "packets.csv",
)

TIMEOUT_SECONDS = 180
MAX_JOBS_IN_MEMORY = 30

router = APIRouter(prefix="/api/jobs", tags=["Simulation Jobs"])
lock = threading.Lock()
jobs = {}


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controller: Literal["a3", "rule", "ml"]
    speed_kmh: Literal[30, 120]
    rng_run: Literal[11, 12]


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def execute_job(job_id, config):
    folder = OUTPUT / job_id
    folder.mkdir(parents=True, exist_ok=False)

    program = PROGRAMS[config.controller]
    options = (
        f"scratch/{program} "
        "--numberOfUes=1 "
        "--numberOfEnbs=3 "
        f"--speedKmh={config.speed_kmh} "
        "--rngSeed=1 "
        f"--rngRun={config.rng_run} "
        "--disableDl=0 "
        "--disableUl=0"
    )
    if config.controller == "ml":
        options += " --pilotAction=none"

    command = ["./ns3", "run", options]

    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = time.time()

        if not (NS3 / "ns3").is_file():
            raise RuntimeError("ns-3 executable not found")

        # Only one API simulation executes at a time.
        # ns-3 writes fixed filenames to its working directory.
        completed = subprocess.run(
            command,
            cwd=NS3,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )

        (folder / "simulation.log").write_text(
            completed.stdout + "\n" + completed.stderr
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"ns-3 exited with code {completed.returncode}"
            )

        started = jobs[job_id]["started_at"]
        for filename in OUTPUT_FILES:
            source = NS3 / filename
            if not source.is_file():
                raise RuntimeError(f"Missing output: {filename}")

            if source.stat().st_mtime < started - 2:
                raise RuntimeError(
                    f"Output not refreshed: {filename}"
                )

            shutil.copy2(source, folder / filename)

        events = read_csv(folder / "handover_events.csv")
        packets = read_csv(folder / "packets.csv")

        starts = sum(
            row["event"] == "HO_START" for row in events
        )
        successes = sum(
            row["event"] == "HO_SUCCESS" for row in events
        )
        failures = sum(
            row["event"] == "HO_FAILURE" for row in events
        )

        result = {
            "job_id": job_id,
            "controller": config.controller,
            "speed_kmh": config.speed_kmh,
            "rng_run": config.rng_run,
            "ho_starts": starts,
            "ho_successes": successes,
            "logged_ho_failures": failures,
            "received_packets_logged": len(packets),
            "handover_events": events,
            "interpretation": (
                "Logged ns-3 results, not verified "
                "end-to-end service-failure measurements."
            ),
        }

        (folder / "result.json").write_text(
            json.dumps(result, indent=2)
        )
        jobs[job_id]["result"] = result
        jobs[job_id]["status"] = "completed"

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = "Simulation exceeded timeout"

    except Exception as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)

    finally:
        jobs[job_id]["finished_at"] = time.time()
        lock.release()


@router.post("", status_code=202)
def create_job(config: SimulationRequest):
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="A simulation is already running",
        )

    try:
        if len(jobs) >= MAX_JOBS_IN_MEMORY:
            raise HTTPException(
                status_code=429,
                detail="Job limit reached; restart backend "
                       "after preserving results",
            )

        job_id = uuid.uuid4().hex
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "controller": config.controller,
            "speed_kmh": config.speed_kmh,
            "rng_run": config.rng_run,
            "result": None,
            "error": None,
        }

        worker = threading.Thread(
            target=execute_job,
            args=(job_id, config),
            daemon=True,
        )
        worker.start()

        return {
            "job_id": job_id,
            "status": "queued",
        }
    except Exception:
        lock.release()
        raise


@router.get("/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(
            status_code=404,
            detail="Unknown job ID",
        )
    return jobs[job_id]
