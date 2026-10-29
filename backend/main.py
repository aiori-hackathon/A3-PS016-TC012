import json
from pathlib import Path
from backend.simulation_jobs import router as simulation_router
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public"

app = FastAPI(
    title="MOBI-HO Lab API",
    version="1.0.0",
    description="Cellular handover benchmarking API"
)

# Local React development server only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET","POST"],
    allow_headers=["Accept", "Content-Type"],
)


def read_json(filename: str):
    path = DATA_DIR / filename

    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Benchmark export unavailable: {filename}"
        )

    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail="Benchmark export could not be read"
        )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "MOBI-HO Lab",
        "mode": "recorded_data"
    }


@app.get("/api/benchmark")
def benchmark():
    return read_json("benchmark.json")


@app.get("/api/rf-decisions")
def rf_decisions():
    return read_json("rf_decisions.json")


@app.get("/api/scenarios")
def scenarios():
    data = read_json("benchmark.json")

    return {
        "controllers": ["a3", "rule", "ml"],
        "speeds_kmh": [30, 120],
        "runs": sorted({
            item["rng_run"]
            for item in data["runs"]
        }),
        "total_recorded_runs": len(data["runs"]),
    }
app.include_router(simulation_router)

