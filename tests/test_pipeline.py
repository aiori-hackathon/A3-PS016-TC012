import csv
import json
import tempfile
import unittest
from pathlib import Path

from aiori_pipeline.pipeline import ContractError, causal_features, compare, load_run, process, write_csv, SCHEMAS
from scripts.make_demo import generate


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        generate(self.root / "raw")
        self.raw = self.root / "raw" / "a3"

    def rewrite(self, name, mutate):
        with (self.raw / name).open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        mutate(rows)
        write_csv(self.raw / name, rows, SCHEMAS[name].split(","))

    def test_known_metrics(self):
        m = process(self.raw, self.root / "processed")
        self.assertEqual(m["handover_attempts"], 3)
        self.assertEqual(m["handover_failures"], 1)
        self.assertAlmostEqual(m["handover_failure_rate"], 1 / 3)
        self.assertEqual(m["ping_pong_events"], 1)
        self.assertAlmostEqual(m["throughput_mbps"], 47 * 1000 * 8 / 5 / 1e6)
        self.assertAlmostEqual(m["mean_excess_gap_s"], 0.1)
        self.assertEqual(m["synthetic"], "true")

    def test_future_mobility_is_never_used(self):
        _, tables, _ = load_run(self.raw)
        tables["mobility.csv"] = [r for r in tables["mobility.csv"] if r["time_s"] >= 0.5]
        features, rejected = causal_features(tables, 0.5)
        self.assertTrue(all(r["time_s"] >= 0.5 for r in features))
        self.assertEqual(len(rejected), 5)

    def test_missing_terminal_is_censored(self):
        self.rewrite("handovers.csv", lambda rows: rows.pop())
        m = process(self.raw, self.root / "out")
        self.assertEqual(m["censored_attempts"], 1)
        self.assertEqual(m["handover_failures"], 0)

    def test_no_packets_is_censored_not_zero_interruption(self):
        self.rewrite("packets.csv", lambda rows: rows.clear())
        m = process(self.raw, self.root / "out")
        self.assertIsNone(m["mean_excess_gap_s"])
        self.assertEqual(m["censored_interruption_samples"], 3)
        self.assertEqual(m["throughput_mbps"], 0)

    def test_duplicate_packets_rejected(self):
        self.rewrite("packets.csv", lambda rows: rows.append(dict(rows[0])))
        with self.assertRaisesRegex(ContractError, "Duplicate received"):
            load_run(self.raw)

    def test_bad_numeric_data_rejected(self):
        self.rewrite("radio.csv", lambda rows: rows[0].update(rsrp_dbm="NaN"))
        with self.assertRaises(ContractError):
            load_run(self.raw)

    def test_terminal_without_start_rejected(self):
        self.rewrite("handovers.csv", lambda rows: rows.pop(0))
        with self.assertRaisesRegex(ContractError, "Unmatched"):
            load_run(self.raw)

    def test_pairing_and_config_mismatch(self):
        outputs = []
        for policy in ("a3", "rf"):
            out = self.root / policy
            process(self.root / "raw" / policy, out)
            outputs.append(out / "metrics.json")
        result = compare(outputs, self.root / "comparison.csv")
        self.assertTrue(all(r["mean_rf_minus_a3"] == 0 for r in result))
        self.assertTrue(all(r["bootstrap_95_low"] is None for r in result))
        data = json.loads(outputs[1].read_text())
        data["config_id"] = "different"
        outputs[1].write_text(json.dumps(data))
        with self.assertRaisesRegex(ContractError, "mismatched config_id"):
            compare(outputs, self.root / "bad.csv")

    def test_test_split_required(self):
        self.rewrite("run.csv", lambda rows: rows[0].update(split="train"))
        process(self.raw, self.root / "out")
        with self.assertRaisesRegex(ContractError, "held-out"):
            compare([self.root / "out" / "metrics.json"], self.root / "bad.csv")

    def test_missing_file_is_actionable(self):
        (self.raw / "traffic.csv").unlink()
        with self.assertRaisesRegex(ContractError, "traffic.csv"):
            load_run(self.raw)

    def test_raw_folder_cannot_be_output(self):
        with self.assertRaisesRegex(ContractError, "outside"):
            process(self.raw, self.raw / "derived")

    def test_incomplete_pair_rejected(self):
        process(self.raw, self.root / "out")
        with self.assertRaisesRegex(ContractError, "Incomplete pair"):
            compare([self.root / "out" / "metrics.json"], self.root / "bad.csv")

    def test_bootstrap_is_paired_and_deterministic(self):
        base = process(self.raw, self.root / "out")
        paths = []
        for i in range(3):
            for policy in ("a3", "rf"):
                item = dict(base, run_id=f"{policy}_{i}", policy=policy, pair_id=f"pair{i}", rng_run=i + 1)
                item["throughput_mbps"] = 10 + i + (2 if policy == "rf" else 0)
                path = self.root / f"{policy}_{i}.json"
                path.write_text(json.dumps(item))
                paths.append(path)
        result = compare(paths, self.root / "comparison.csv")
        throughput = next(r for r in result if r["metric"] == "throughput_mbps")
        self.assertEqual(throughput["mean_rf_minus_a3"], 2)
        self.assertEqual(throughput["bootstrap_95_low"], 2)
        self.assertEqual(throughput["bootstrap_95_high"], 2)
        self.assertEqual(result, compare(list(reversed(paths)), self.root / "again.csv"))


if __name__ == "__main__":
    unittest.main()
