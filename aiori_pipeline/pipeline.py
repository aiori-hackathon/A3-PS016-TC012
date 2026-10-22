"""Strict CSV contract and deterministic, dependency-free offline evaluation."""
import argparse
import bisect
import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCHEMAS = {
    "run.csv": "run_id,policy,split,scenario_id,config_id,pair_id,seed,rng_run,speed_kmh,ns3_version,radio_model,git_commit,observation_start_s,observation_end_s,synthetic",
    "traffic.csv": "imsi,flow_id,direction,packet_interval_s",
    "radio.csv": "time_s,imsi,serving_cell_id,measured_cell_id,rsrp_dbm,rsrq_db,is_serving_cell",
    "mobility.csv": "time_s,imsi,x_m,y_m,z_m,speed_mps",
    "handovers.csv": "time_s,imsi,attempt_id,source_cell_id,target_cell_id,event,failure_reason",
    "packets.csv": "time_s,imsi,flow_id,direction,sequence,payload_bytes",
}
INTS = {"imsi", "serving_cell_id", "measured_cell_id", "source_cell_id", "target_cell_id", "seed", "rng_run", "sequence", "payload_bytes"}
FLOATS = {"time_s", "speed_kmh", "observation_start_s", "observation_end_s", "packet_interval_s", "rsrp_dbm", "rsrq_db", "x_m", "y_m", "z_m", "speed_mps"}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def read_table(folder, name):
    path = folder / name
    require(path.is_file(), f"Missing required file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        require(len(fields) == len(set(fields)), f"{name}: duplicate headers")
        missing = set(SCHEMAS[name].split(",")) - set(fields)
        require(not missing, f"{name}: missing fields {sorted(missing)}")
        rows = []
        for line, row in enumerate(reader, 2):
            require(None not in row and all(v is not None for v in row.values()), f"{name}:{line}: malformed row")
            row = {k: v.strip() for k, v in row.items()}
            for field in SCHEMAS[name].split(","):
                require(row[field] != "" or field == "failure_reason", f"{name}:{line}: empty {field}")
                try:
                    if field in INTS:
                        row[field] = int(row[field])
                        require(row[field] >= 0, f"{name}:{line}: negative {field}")
                    if field in FLOATS:
                        row[field] = float(row[field])
                        require(math.isfinite(row[field]), f"{name}:{line}: nonfinite {field}")
                except ValueError as exc:
                    raise ContractError(f"{name}:{line}: invalid {field}: {row[field]}") from exc
            rows.append(row)
    return rows


def flow_key(row):
    return row["imsi"], row["flow_id"], row["direction"]


def load_run(folder):
    tables = {name: read_table(Path(folder), name) for name in SCHEMAS}
    require(len(tables["run.csv"]) == 1, "run.csv: exactly one metadata row required")
    meta = tables["run.csv"][0]
    require(meta["policy"] in {"a3", "rf"}, "policy must be a3 or rf")
    require(meta["split"] in {"train", "validation", "test"}, "Invalid split")
    require(meta["synthetic"] in {"true", "false"}, "synthetic must be true or false")
    require(0 <= meta["observation_start_s"] < meta["observation_end_s"], "Invalid observation window")
    require(meta["speed_kmh"] > 0, "speed_kmh must be positive")
    flows = {}
    for row in tables["traffic.csv"]:
        key = flow_key(row)
        require(key not in flows, f"Duplicate flow {key}")
        require(row["direction"] in {"DL", "UL"}, "direction must be DL or UL")
        require(row["packet_interval_s"] > 0, "packet_interval_s must be positive")
        flows[key] = row
    require(bool(flows), "traffic.csv: at least one flow required")
    ues = {key[0] for key in flows}
    seen = set()
    for row in tables["packets.csv"]:
        key = flow_key(row)
        require(key in flows, f"Unknown packet flow: {key}")
        identity = key + (row["sequence"],)
        require(identity not in seen, f"Duplicate received packet: {identity}")
        seen.add(identity)
        require(row["payload_bytes"] > 0, "payload_bytes must be positive")
    for name in ("radio.csv", "mobility.csv", "handovers.csv", "packets.csv"):
        for row in tables[name]:
            require(row["time_s"] >= 0, f"{name}: negative timestamp")
            require(row["imsi"] in ues, f"{name}: unknown IMSI {row['imsi']}")
        tables[name].sort(key=lambda row: row["time_s"])
    for name, fields in (("radio.csv", ("time_s", "imsi", "measured_cell_id")), ("mobility.csv", ("time_s", "imsi"))):
        identities = [tuple(r[f] for f in fields) for r in tables[name]]
        require(len(identities) == len(set(identities)), f"{name}: duplicate measurements")
    for row in tables["radio.csv"]:
        require(row["is_serving_cell"] in {"0", "1"}, "is_serving_cell must be 0 or 1")
        require((row["is_serving_cell"] == "1") == (row["serving_cell_id"] == row["measured_cell_id"]), "Radio serving-cell identity mismatch")
    require(all(r["speed_mps"] >= 0 for r in tables["mobility.csv"]), "Negative mobility speed")
    attempts = {}
    active = {}
    for row in tables["handovers.csv"]:
        key = row["imsi"], row["attempt_id"]
        require(row["source_cell_id"] != row["target_cell_id"], "Handover source equals target")
        require(row["event"] in {"START", "SUCCESS", "FAILURE"}, "Invalid handover event")
        if row["event"] == "START":
            require(key not in attempts, f"Duplicate attempt start: {key}")
            require(row["imsi"] not in active, "Overlapping handovers for one UE")
            attempts[key] = {"start": row, "end": None}
            active[row["imsi"]] = key
        else:
            require(key in attempts and attempts[key]["end"] is None, f"Unmatched or duplicate terminal event: {key}")
            start = attempts[key]["start"]
            require(all(row[f] == start[f] for f in ("source_cell_id", "target_cell_id")), f"Attempt cells changed: {key}")
            require(row["event"] != "FAILURE" or bool(row["failure_reason"]), "Failure reason required")
            attempts[key]["end"] = row
            active.pop(row["imsi"], None)
    return meta, tables, attempts


def causal_features(tables, max_age):
    """One row per complete radio timestamp, using only past/current values."""
    mobility = defaultdict(list)
    for row in tables["mobility.csv"]:
        mobility[row["imsi"]].append(row)
    times = {ue: [r["time_s"] for r in rows] for ue, rows in mobility.items()}
    snapshots = defaultdict(list)
    for row in tables["radio.csv"]:
        snapshots[row["time_s"], row["imsi"]].append(row)
    output, rejected, previous = [], [], {}
    for (time, ue), rows in sorted(snapshots.items()):
        serving = [r for r in rows if r["is_serving_cell"] == "1"]
        neighbours = [r for r in rows if r["is_serving_cell"] == "0"]
        index = bisect.bisect_right(times.get(ue, []), time) - 1
        reason = None
        if len(serving) != 1 or not neighbours or len({r["serving_cell_id"] for r in rows}) != 1:
            reason = "incomplete_or_inconsistent_radio_snapshot"
        elif index < 0 or time - mobility[ue][index]["time_s"] > max_age:
            reason = "missing_or_stale_past_mobility"
        if reason:
            rejected.append({"time_s": time, "imsi": ue, "reason": reason})
            continue
        source = serving[0]
        target = max(neighbours, key=lambda r: (r["rsrp_dbm"], -r["measured_cell_id"]))
        delta = target["rsrp_dbm"] - source["rsrp_dbm"]
        key = ue, source["measured_cell_id"], target["measured_cell_id"]
        prior = previous.get(key)
        slope = (delta - prior[1]) / (time - prior[0]) if prior and time > prior[0] else None
        previous[key] = time, delta
        output.append({"time_s": time, "imsi": ue, "serving_cell_id": source["measured_cell_id"], "candidate_cell_id": target["measured_cell_id"], "serving_rsrp_dbm": source["rsrp_dbm"], "candidate_rsrp_dbm": target["rsrp_dbm"], "rsrp_delta_db": delta, "delta_slope_db_per_s": slope, "trend_available": int(slope is not None), "speed_mps": mobility[ue][index]["speed_mps"], "mobility_age_s": time - mobility[ue][index]["time_s"]})
    return output, rejected


def evaluate(meta, tables, attempts, ping_window):
    start, stop = meta["observation_start_s"], meta["observation_end_s"]
    selected = [a for a in attempts.values() if start <= a["start"]["time_s"] < stop]
    terminal = lambda a: a["end"] if a["end"] and a["end"]["time_s"] <= stop else None
    failures = sum(bool(terminal(a) and terminal(a)["event"] == "FAILURE") for a in selected)
    successes = sum(bool(terminal(a) and terminal(a)["event"] == "SUCCESS") for a in selected)
    censored = len(selected) - failures - successes
    ping, last = 0, {}
    # Include pre-window successes for boundary context; count returns in-window.
    for a in sorted((a for a in attempts.values() if a["end"] and a["end"]["event"] == "SUCCESS"), key=lambda a: a["end"]["time_s"]):
        row, end = a["start"], a["end"]["time_s"]
        prev = last.get(row["imsi"])
        if prev and start <= end < stop and row["source_cell_id"] == prev[1] and row["target_cell_id"] == prev[0] and end - prev[2] <= ping_window:
            ping += 1
        last[row["imsi"]] = row["source_cell_id"], row["target_cell_id"], end
    packet_groups = defaultdict(list)
    for row in tables["packets.csv"]:
        packet_groups[flow_key(row)].append(row)
    flow_metrics, interruptions = [], []
    for flow in tables["traffic.csv"]:
        key = flow_key(flow)
        packets = packet_groups[key]
        received = [r for r in packets if start <= r["time_s"] < stop]
        throughput = sum(r["payload_bytes"] for r in received) * 8 / (stop - start) / 1e6
        flow_metrics.append({"imsi": key[0], "flow_id": key[1], "direction": key[2], "received_packets": len(received), "throughput_mbps": throughput})
        packet_times = [r["time_s"] for r in packets]
        for a in selected:
            row = a["start"]
            if row["imsi"] != key[0]:
                continue
            index = bisect.bisect_left(packet_times, row["time_s"])
            before = packet_times[index - 1] if index else None
            after = packet_times[index] if index < len(packet_times) else None
            valid = before is not None and after is not None and before >= start and after < stop
            gap = after - before if valid else None
            interruptions.append({"imsi": key[0], "flow_id": key[1], "direction": key[2], "attempt_id": row["attempt_id"], "status": "observed" if valid else "censored", "packet_gap_s": gap, "excess_gap_s": max(0.0, gap - flow["packet_interval_s"]) if valid else None, "rrc_duration_s": terminal(a)["time_s"] - row["time_s"] if terminal(a) else None})
    excess = [r["excess_gap_s"] for r in interruptions if r["status"] == "observed"]
    metrics = dict(meta)
    metrics.update(handover_attempts=len(selected), handover_successes=successes, handover_failures=failures, censored_attempts=censored, handover_failure_rate=failures / (successes + failures) if successes + failures else None, ping_pong_events=ping, ping_pong_window_s=ping_window, throughput_mbps=sum(r["throughput_mbps"] for r in flow_metrics), mean_excess_gap_s=statistics.mean(excess) if excess else None, observed_interruption_samples=len(excess), censored_interruption_samples=len(interruptions) - len(excess))
    return metrics, flow_metrics, interruptions


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


FEATURE_FIELDS = "run_id,split,time_s,imsi,serving_cell_id,candidate_cell_id,serving_rsrp_dbm,candidate_rsrp_dbm,rsrp_delta_db,delta_slope_db_per_s,trend_available,speed_mps,mobility_age_s".split(",")


def process(folder, output, max_age=0.5, ping_window=1.0):
    require(max_age > 0 and ping_window > 0 and math.isfinite(max_age) and math.isfinite(ping_window), "Windows must be finite and positive")
    meta, tables, attempts = load_run(folder)
    features, rejected = causal_features(tables, max_age)
    for row in features:
        row.update(run_id=meta["run_id"], split=meta["split"])
    metrics, flows, interruptions = evaluate(meta, tables, attempts, ping_window)
    metrics.update(feature_rows=len(features), rejected_feature_rows=len(rejected), max_mobility_age_s=max_age)
    out = Path(output)
    require(not out.resolve().is_relative_to(Path(folder).resolve()), "Output must be outside the input folder")
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_csv(out / "features.csv", features, FEATURE_FIELDS)
    write_csv(out / "rejected_features.csv", rejected, ["time_s", "imsi", "reason"])
    write_csv(out / "flow_metrics.csv", flows, ["imsi", "flow_id", "direction", "received_packets", "throughput_mbps"])
    write_csv(out / "interruptions.csv", interruptions, ["imsi", "flow_id", "direction", "attempt_id", "status", "packet_gap_s", "excess_gap_s", "rrc_duration_s"])
    return metrics


def compare(paths, output):
    metrics = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    require(bool(metrics), "No metrics supplied")
    require(len({m["run_id"] for m in metrics}) == len(metrics), "Duplicate run IDs")
    require(all(m["split"] == "test" for m in metrics), "Comparison requires held-out test runs")
    require(len({m["synthetic"] for m in metrics}) == 1, "Cannot mix synthetic and simulation runs")
    pairs = defaultdict(dict)
    for m in metrics:
        key = m["scenario_id"], m["speed_kmh"], m["pair_id"]
        require(m["policy"] not in pairs[key], f"Duplicate policy in pair {key}")
        pairs[key][m["policy"]] = m
    groups = defaultdict(list)
    for key, pair in pairs.items():
        require(set(pair) == {"a3", "rf"}, f"Incomplete pair {key}")
        a, b = pair["a3"], pair["rf"]
        for field in ("config_id", "radio_model", "seed", "rng_run", "observation_start_s", "observation_end_s", "ns3_version", "git_commit", "ping_pong_window_s", "max_mobility_age_s"):
            require(a[field] == b[field], f"Pair {key}: mismatched {field}")
        groups[key[:2]].append((a, b))
    result = []
    for (scenario, speed), group in sorted(groups.items()):
        require(len({(a["seed"], a["rng_run"]) for a, _ in group}) == len(group), "Repeated random seed/run within evaluation group")
        group.sort(key=lambda pair: pair[0]["pair_id"])
        for metric in ("handover_failures", "handover_failure_rate", "ping_pong_events", "mean_excess_gap_s", "throughput_mbps"):
            values = [(a[metric], b[metric]) for a, b in group if a[metric] is not None and b[metric] is not None]
            diffs = [b - a for a, b in values]
            low = high = None
            if len(diffs) >= 2:
                rng = random.Random(42)
                boot = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(2000))
                low, high = boot[49], boot[1949]
            result.append({"scenario_id": scenario, "speed_kmh": speed, "synthetic": group[0][0]["synthetic"], "metric": metric, "total_pairs": len(group), "valid_pairs": len(values), "a3_mean": statistics.mean(a for a, _ in values) if values else None, "rf_mean": statistics.mean(b for _, b in values) if values else None, "mean_rf_minus_a3": statistics.mean(diffs) if diffs else None, "bootstrap_95_low": low, "bootstrap_95_high": high})
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out, result, list(result[0]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("run_folder")
    proc = commands.add_parser("process")
    proc.add_argument("run_folder")
    proc.add_argument("--output", required=True)
    proc.add_argument("--max-mobility-age-s", type=float, default=0.5)
    proc.add_argument("--ping-pong-window-s", type=float, default=1.0)
    comp = commands.add_parser("compare")
    comp.add_argument("metrics", nargs="+")
    comp.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            meta, _, _ = load_run(args.run_folder)
            print(f"VALID: {meta['run_id']} (synthetic={meta['synthetic']})")
        elif args.command == "process":
            print(json.dumps(process(args.run_folder, args.output, args.max_mobility_age_s, args.ping_pong_window_s), indent=2))
        else:
            print(f"Wrote {len(compare(args.metrics, args.output))} comparison rows")
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
