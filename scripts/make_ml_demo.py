"""FABRICATED paired-action data for software tests, never ns-3 evidence."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiori_pipeline.ml import DECISIONS, OUTCOMES
from aiori_pipeline.pipeline import write_csv


def generate(folder):
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    decisions, outcomes = [], []
    for split_index, split in enumerate(("train", "validation", "test")):
        for group in range(4):
            for point in range(6):
                identity = f"SYNTHETIC_{split}_{group}_{point}"
                fingerprint = hashlib.sha256(identity.encode()).hexdigest()
                delta = (-6 if point % 2 == 0 else 6) + split_index * .17 + group * .013 + point * .001
                speed = 30 / 3.6 if group % 2 == 0 else 120 / 3.6
                decision = dict(zip(DECISIONS, [identity, f"SYNTHETIC_{split}_{group}", split, f"SYNTHETIC_route_{split}_{group}", "SYNTHETIC_config", 1, group+1, 1, 1, 2, 10+point, 10+point, fingerprint, "true", -80, -80+delta, delta, "" if point==0 else 1.0, 0 if point==0 else 1, speed, 0]))
                decisions.append(decision)
                for action in ("stay", "handover"):
                    gap = .1 if ((delta > 0) == (action == "handover")) else .2
                    outcomes.append(dict(zip(OUTCOMES, [identity, action, f"{identity}_{action}", "paired-action-v1-draft", fingerprint, 10+point, 11+point, "complete", 0, 0, gap, 3.0])))
    write_csv(root / "decisions.csv", decisions, DECISIONS)
    write_csv(root / "action_outcomes.csv", outcomes, OUTCOMES)
    return root


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv)>1 else "examples/ml_synthetic")
    print("Generated FABRICATED paired-action fixtures. Scores are software checks only.")
