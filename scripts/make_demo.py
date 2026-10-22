"""Generate small SYNTHETIC pipeline fixtures, never experimental evidence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiori_pipeline.pipeline import SCHEMAS, write_csv


def generate(root):
    for policy in ("a3", "rf"):
        folder = Path(root) / policy
        folder.mkdir(parents=True, exist_ok=True)
        tables = {name: [] for name in SCHEMAS}
        tables["run.csv"] = [dict(zip(SCHEMAS["run.csv"].split(","), [f"SYNTHETIC_{policy}", policy, "test", "demo", "demo-config", "demo-pair", 1, 1, 30, "fixture-only", "SYNTHETIC", "fixture-only", 0, 5, "true"]))]
        tables["traffic.csv"] = [{"imsi": 1, "flow_id": "dl1", "direction": "DL", "packet_interval_s": 0.1}]
        for i in range(51):
            time = i / 10
            tables["mobility.csv"].append(dict(zip(SCHEMAS["mobility.csv"].split(","), [time, 1, time * 30 / 3.6, 0, 0, 30 / 3.6])))
            for cell in (1, 2, 3):
                tables["radio.csv"].append(dict(zip(SCHEMAS["radio.csv"].split(","), [time, 1, 1, cell, -80 + (time if cell == 2 else 0) - 5 * (cell - 1), -10, int(cell == 1)])))
            if i not in (10, 11, 12):
                tables["packets.csv"].append(dict(zip(SCHEMAS["packets.csv"].split(","), [time, 1, "dl1", "DL", i, 1000])))
        for time, attempt, source, target, event, reason in [(1, "h1", 1, 2, "START", ""), (1.2, "h1", 1, 2, "SUCCESS", ""), (1.5, "h2", 2, 1, "START", ""), (1.7, "h2", 2, 1, "SUCCESS", ""), (3, "h3", 1, 2, "START", ""), (3.2, "h3", 1, 2, "FAILURE", "SYNTHETIC_FAILURE")]:
            tables["handovers.csv"].append(dict(zip(SCHEMAS["handovers.csv"].split(","), [time, 1, attempt, source, target, event, reason])))
        for name, rows in tables.items():
            write_csv(folder / name, rows, SCHEMAS[name].split(","))


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else "examples/synthetic")
    print("Generated SYNTHETIC fixtures; A3 and RF data are intentionally identical.")
