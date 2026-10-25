"""Paired-action labels, grouped RF training and portable JSON inference.

Label preparation and JSON inference use only the standard library.
Training additionally requires the optional scikit-learn dependency.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import ContractError, require, write_csv

FEATURES = ["serving_rsrp_dbm", "candidate_rsrp_dbm", "rsrp_delta_db", "delta_slope_db_per_s", "trend_available", "speed_mps", "mobility_age_s"]
DECISIONS = ["decision_id", "group_id", "split", "scenario_id", "config_id", "seed", "rng_run", "imsi", "serving_cell_id", "candidate_cell_id", "decision_time_s", "feature_time_s", "predecision_hash", "synthetic", *FEATURES]
OUTCOMES = ["decision_id", "action", "run_id", "protocol_id", "predecision_hash", "window_start_s", "window_end_s", "status", "service_failures", "ping_pong_events", "total_excess_gap_s", "throughput_mbps"]
METRICS = ["service_failures", "ping_pong_events", "total_excess_gap_s", "throughput_mbps"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_csv(path, fields, optional_empty=()):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        require(bool(reader.fieldnames) and len(reader.fieldnames) == len(set(reader.fieldnames)), f"{path}: missing/duplicate headers")
        require(set(fields) <= set(reader.fieldnames), f"{path}: required columns: {','.join(fields)}")
        result = []
        for line, row in enumerate(reader, 2):
            require(None not in row and all(v is not None for v in row.values()), f"{path}:{line}: malformed CSV")
            row = {k: v.strip() for k, v in row.items()}
            require(all(row[k] != "" for k in fields if k not in optional_empty), f"{path}:{line}: empty required field")
            result.append(row)
    require(bool(result), f"{path}: no rows")
    return result


def number(value, name, minimum=None):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ContractError(f"Invalid number for {name}: {value}") from None
    require(math.isfinite(result) and (minimum is None or result >= minimum), f"Invalid {name}: {value}")
    return result


def integer(value, name):
    result = number(value, name, 0)
    require(result.is_integer(), f"{name} must be a nonnegative integer")
    return int(result)


def protocol(path):
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    require(bool(p.get("protocol_id")) and bool(p.get("followup_policy_id")), "Protocol IDs required")
    require(p.get("status") in {"draft", "frozen"}, "Protocol status must be draft or frozen")
    require(p.get("priority") == METRICS, "Unsupported label priority")
    for field in ("horizon_s", "action_hold_s", "ping_pong_window_s", "max_feature_age_s", "gap_margin_s", "throughput_margin_mbps"):
        p[field] = number(p.get(field), field, 0)
    require(0 < p["action_hold_s"] <= p["horizon_s"], "Invalid action hold/horizon")
    require(p["ping_pong_window_s"] > 0 and p["max_feature_age_s"] > 0, "Measurement windows must be positive")
    return p


def validate_decisions(rows, p):
    seen, groups = set(), {}
    for r in rows:
        require(r["decision_id"] not in seen, "Duplicate decision_id")
        seen.add(r["decision_id"])
        require(r["split"] in {"train", "validation", "test"}, "Invalid split")
        require(r["synthetic"] in {"true", "false"}, "Invalid synthetic flag")
        require(len(r["predecision_hash"]) == 64 and all(c in "0123456789abcdef" for c in r["predecision_hash"]), "predecision_hash must be lowercase SHA256")
        require(groups.setdefault(r["group_id"], r["split"]) == r["split"], "group_id crosses splits")
        for k in ("seed", "rng_run", "imsi", "serving_cell_id", "candidate_cell_id"):
            r[k] = integer(r[k], k)
        require(r["candidate_cell_id"] != r["serving_cell_id"], "Candidate equals serving cell")
        for k in FEATURES + ["decision_time_s", "feature_time_s"]:
            if k == "delta_slope_db_per_s" and r[k] == "":
                continue
            r[k] = number(r[k], k)
        require(r["decision_time_s"] >= r["feature_time_s"] >= 0, "Future feature or negative timestamp")
        require(r["decision_time_s"] - r["feature_time_s"] <= p["max_feature_age_s"] + 1e-9, "Stale feature snapshot")
        require(r["trend_available"] in {0, 1}, "Invalid trend_available")
        require((r["delta_slope_db_per_s"] != "") == bool(r["trend_available"]), "Trend flag/value mismatch")
        require(r["speed_mps"] > 0 and 0 <= r["mobility_age_s"] <= 0.5, "Invalid speed or mobility age")
        require(abs(r["rsrp_delta_db"] - (r["candidate_rsrp_dbm"] - r["serving_rsrp_dbm"])) <= 1e-5, "RSRP difference inconsistent")
    require(len({r["synthetic"] for r in rows}) == 1, "Cannot mix synthetic and real data")


def feature_fingerprint(row):
    values = [None if row[k] == "" else round(float(row[k]), 6) for k in FEATURES]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def check_splits(rows):
    """IDs and exact numeric features must never cross dataset splits."""
    seen = {key: {} for key in ("group_id", "predecision_hash", "feature_fingerprint")}
    for r in rows:
        for key, index in seen.items():
            value = feature_fingerprint(r) if key == "feature_fingerprint" else r[key]
            require(index.setdefault(value, r["split"]) == r["split"], f"Leakage: {key} crosses splits")


def fresh_output(path, inputs=()):
    out = Path(path).resolve()
    for source in inputs:
        source = Path(source).resolve()
        require(out != source and (not source.is_dir() or not out.is_relative_to(source)), "Output overlaps input")
    require(not out.exists() or (out.is_dir() and not any(out.iterdir())), f"Output already populated: {out}")
    out.mkdir(parents=True, exist_ok=True)
    return out


def label(decisions_path, outcomes_path, protocol_path, output):
    p = protocol(protocol_path)
    decisions = read_csv(decisions_path, DECISIONS, ["delta_slope_db_per_s"])
    validate_decisions(decisions, p)
    check_splits(decisions)
    outcomes = read_csv(outcomes_path, OUTCOMES, METRICS)
    by_id = defaultdict(dict)
    ids = {r["decision_id"] for r in decisions}
    run_ids = set()
    for row in outcomes:
        require(row["decision_id"] in ids, "Orphan outcome decision_id")
        require(row["action"] in {"stay", "handover"}, "Invalid action")
        require(row["action"] not in by_id[row["decision_id"]], "Duplicate action outcome")
        require(row["run_id"] not in run_ids, "Outcome run_id must be unique per action rollout")
        run_ids.add(row["run_id"])
        require(row["protocol_id"] == p["protocol_id"], "Outcome protocol mismatch")
        require(row["status"] in {"complete", "censored"}, "Invalid outcome status")
        for k in ("window_start_s", "window_end_s"):
            row[k] = number(row[k], k, 0)
        require(abs(row["window_end_s"] - row["window_start_s"] - p["horizon_s"]) < 1e-6, "Outcome horizon mismatch")
        if row["status"] == "complete":
            for k in METRICS:
                row[k] = integer(row[k], k) if k in METRICS[:2] else number(row[k], k, 0)
        by_id[row["decision_id"]][row["action"]] = row
    labelled = []
    for d in decisions:
        pair = by_id[d["decision_id"]]
        require(set(pair) == {"stay", "handover"}, f"Missing paired action for {d['decision_id']}")
        for o in pair.values():
            require(o["predecision_hash"] == d["predecision_hash"], "Predecision state/history mismatch")
            require(abs(o["window_start_s"] - d["decision_time_s"]) < 1e-6, "Outcome starts at wrong decision time")
        target, reason = -1, "tie"
        if any(o["status"] != "complete" for o in pair.values()):
            reason = "censored"
        else:
            for metric in METRICS:
                difference = pair["handover"][metric] - pair["stay"][metric]
                margin = p["gap_margin_s"] if metric == "total_excess_gap_s" else p["throughput_margin_mbps"] if metric == "throughput_mbps" else 0
                if abs(difference) > margin + 1e-12:
                    target = int(difference > 0) if metric == "throughput_mbps" else int(difference < 0)
                    reason = metric
                    break
        labelled.append(dict(d, label=target, label_reason=reason))
    out = fresh_output(output, [decisions_path, outcomes_path])
    write_csv(out / "labelled.csv", labelled, DECISIONS + ["label", "label_reason"])
    dump(out / "protocol.json", p)
    dump(out / "manifest.json", {"schema_version": 1, "synthetic": decisions[0]["synthetic"], "dataset_sha256": sha(out / "labelled.csv"), "protocol_sha256": sha(out / "protocol.json"), "sources": {"decisions_sha256": sha(decisions_path), "outcomes_sha256": sha(outcomes_path)}, "counts": {split: dict(Counter(str(r["label"]) for r in labelled if r["split"] == split)) for split in ("train", "validation", "test")}, "excluded_reasons": dict(Counter(r["label_reason"] for r in labelled if r["label"] == -1)), "note": "Labels reflect the declared protocol and supplied outcomes; paired-state claims require a simulator-side audit."})
    return labelled


def dataset(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    require(manifest["dataset_sha256"] == sha(folder / "labelled.csv"), "Dataset changed since labelling")
    require(manifest["protocol_sha256"] == sha(folder / "protocol.json"), "Protocol changed since labelling")
    p = protocol(folder / "protocol.json")
    rows = read_csv(folder / "labelled.csv", DECISIONS + ["label", "label_reason"], ["delta_slope_db_per_s"])
    validate_decisions(rows, p)
    check_splits(rows)
    require(manifest["synthetic"] == rows[0]["synthetic"], "Manifest/data synthetic mismatch")
    for r in rows:
        require(r["label"] in {"-1", "0", "1"}, "Invalid label")
        r["label"] = int(r["label"])
    return rows, manifest, p


def vector(row, medians=None):
    values = []
    for i, key in enumerate(FEATURES):
        value = row[key]
        if value == "":
            require(medians is not None, "Missing feature requires fitted imputation")
            value = medians[i]
        values.append(number(value, key))
    return values


def probability(model, row):
    require(model.get("schema_version") == 1 and model.get("features") == FEATURES, "Incompatible model schema")
    # sklearn decision trees compare float32 predictor inputs.
    values = [struct.unpack("f", struct.pack("f", v))[0] for v in vector(row, model["medians"])]
    probabilities = []
    for tree in model["trees"]:
        node = 0
        while tree["left"][node] != -1:
            node = tree["left"][node] if values[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
        probabilities.append(tree["probability_handover"][node])
    return statistics.mean(probabilities)


def scores(rows, probs, threshold):
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support
    truth = [r["label"] for r in rows]
    pred = [int(p >= threshold) for p in probs]
    precision, recall, f1, _ = precision_recall_fscore_support(truth, pred, average="binary", zero_division=0)
    group_accuracy = defaultdict(list)
    for r, y in zip(rows, pred):
        group_accuracy[r["group_id"]].append(int(y == r["label"]))
    return {"rows": len(rows), "groups": len(group_accuracy), "class_counts": dict(Counter(truth)), "threshold": threshold, "accuracy": float(accuracy_score(truth, pred)), "balanced_accuracy": float(balanced_accuracy_score(truth, pred)), "handover_precision": float(precision), "handover_recall": float(recall), "handover_f1": float(f1), "brier_score": float(brier_score_loss(truth, probs)), "confusion_matrix_rows_true_columns_predicted_stay_handover": confusion_matrix(truth, pred, labels=[0,1]).tolist(), "mean_group_accuracy": statistics.mean(statistics.mean(v) for v in group_accuracy.values())}


def train(folder, output, allow_synthetic=False, threshold=0.6, trees=128):
    require(0 < threshold < 1 and 1 <= trees <= 1000, "Invalid threshold/tree count")
    rows, manifest, p = dataset(folder)
    synthetic = manifest["synthetic"] == "true"
    require(not synthetic or allow_synthetic, "Synthetic training requires --allow-synthetic")
    require(synthetic or p["status"] == "frozen", "Freeze the experimental protocol before real-data training")
    selected = {split: [r for r in rows if r["split"] == split and r["label"] != -1] for split in ("train", "validation")}
    for split, items in selected.items():
        require({r["label"] for r in items} == {0,1}, f"{split} requires both labelled classes")
        require(len({r["group_id"] for r in items}) >= 2, f"{split} requires at least two scenario groups")
    try:
        import sklearn
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        raise ContractError("Install ML dependencies: python -m pip install -e .[ml]") from None
    fit = selected["train"]
    medians = []
    for key in FEATURES:
        values = [float(r[key]) for r in fit if r[key] != ""]
        medians.append(statistics.median(values) if values else 0.0)
    group_counts = Counter(r["group_id"] for r in fit)
    forest = RandomForestClassifier(n_estimators=trees, max_depth=8, min_samples_leaf=2, class_weight="balanced_subsample", random_state=42, n_jobs=1)
    forest.fit([vector(r, medians) for r in fit], [r["label"] for r in fit], sample_weight=[1 / group_counts[r["group_id"]] for r in fit])
    model = {"schema_version": 1, "features": FEATURES, "medians": medians, "threshold": threshold, "classes": ["stay", "handover"], "synthetic": synthetic, "protocol": p, "dataset_sha256": manifest["dataset_sha256"], "python_version": platform.python_version(), "sklearn_version": sklearn.__version__, "training_parameters": forest.get_params(), "fit_groups": sorted({r["group_id"] for r in fit}), "development_groups": sorted({r["group_id"] for split in selected.values() for r in split}), "development_predecision_hashes": sorted({r["predecision_hash"] for split in selected.values() for r in split}), "development_feature_fingerprints": sorted({feature_fingerprint(r) for split in selected.values() for r in split}), "trees": []}
    model.update(implementation_sha256=sha(__file__), source_hashes=manifest["sources"])
    handover_index = list(forest.classes_).index(1)
    for estimator in forest.estimators_:
        tree = estimator.tree_
        values = tree.value[:,0,:]
        probability_values = [float(v[handover_index] / sum(v)) for v in values]
        model["trees"].append({"left": tree.children_left.tolist(), "right": tree.children_right.tolist(), "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(), "probability_handover": probability_values})
    reports, golden = {}, []
    for split, items in selected.items():
        probs = [probability(model, r) for r in items]
        expected = forest.predict_proba([vector(r, medians) for r in items])[:,handover_index]
        require(max(abs(a-b) for a,b in zip(probs, expected)) < 1e-12, "JSON model prediction parity failed")
        reports[split] = scores(items, probs, threshold)
        if split == "validation":
            for r, prob in zip(items, probs):
                golden.append({"decision_id": r["decision_id"], "features": {k:r[k] for k in FEATURES}, "probability_handover": prob, "prediction": int(prob >= threshold)})
    reports.update(synthetic=synthetic, note="Synthetic scores test software only. Real classification scores do not establish network-policy improvement.", reserved_test_rows=sum(r["split"] == "test" for r in rows), excluded_unlabelled=sum(r["label"] == -1 for r in rows))
    out = fresh_output(output, [folder])
    dump(out / "model.json", model)
    dump(out / "training_report.json", reports)
    dump(out / "golden_predictions.json", golden)
    return reports


def evaluate(folder, model_path, output, allow_synthetic=False):
    rows, manifest, p = dataset(folder)
    model = json.loads(Path(model_path).read_text())
    require(model["protocol"] == p, "Model/dataset protocol mismatch")
    require(model["synthetic"] == (manifest["synthetic"] == "true"), "Model/dataset synthetic mismatch")
    require(not model["synthetic"] or allow_synthetic, "Synthetic evaluation requires --allow-synthetic")
    test = [r for r in rows if r["split"] == "test" and r["label"] != -1]
    require({r["label"] for r in test} == {0,1}, "Held-out test requires both labelled classes")
    require(len({r["group_id"] for r in test}) >= 2, "Held-out test requires at least two scenario groups")
    for r in test:
        require(r["group_id"] not in model["development_groups"], "Test group seen during development")
        require(r["predecision_hash"] not in model["development_predecision_hashes"], "Test state seen during development")
        require(feature_fingerprint(r) not in model["development_feature_fingerprints"], "Test features seen during development")
    probs = [probability(model, r) for r in test]
    report = scores(test, probs, model["threshold"])
    report.update(synthetic=model["synthetic"], model_sha256=sha(model_path), dataset_sha256=manifest["dataset_sha256"], note="Offline classification only; independent live A3/RF network-policy evaluation remains required.")
    out = fresh_output(output, [folder, model_path])
    dump(out / "test_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    lab = commands.add_parser("label")
    lab.add_argument("--decisions", required=True)
    lab.add_argument("--outcomes", required=True)
    lab.add_argument("--protocol", required=True)
    lab.add_argument("--output", required=True)
    fit = commands.add_parser("train")
    fit.add_argument("dataset")
    fit.add_argument("--output", required=True)
    fit.add_argument("--allow-synthetic", action="store_true")
    fit.add_argument("--threshold", type=float, default=0.6)
    fit.add_argument("--trees", type=int, default=128)
    test = commands.add_parser("evaluate")
    test.add_argument("dataset")
    test.add_argument("--model", required=True)
    test.add_argument("--output", required=True)
    test.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "label":
            rows = label(args.decisions, args.outcomes, args.protocol, args.output)
            print(json.dumps({"rows": len(rows), "labels": dict(Counter(r["label"] for r in rows))}))
        elif args.command == "train":
            print(json.dumps(train(args.dataset, args.output, args.allow_synthetic, args.threshold, args.trees), indent=2))
        else:
            print(json.dumps(evaluate(args.dataset, args.model, args.output, args.allow_synthetic), indent=2))
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
