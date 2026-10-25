import csv
import json
import tempfile
import unittest
from pathlib import Path

from aiori_pipeline.ml import DECISIONS, OUTCOMES, dataset, evaluate, label, probability, train
from aiori_pipeline.pipeline import ContractError, write_csv
from scripts.make_ml_demo import generate


class MLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = generate(self.root / "raw")
        self.protocol = self.root / "protocol.json"
        self.protocol.write_text(Path("configs/ml_protocol.json").read_text())

    def rewrite(self, name, mutate):
        path = self.raw / name
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        mutate(rows)
        write_csv(path, rows, DECISIONS if name == "decisions.csv" else OUTCOMES)

    def labels(self):
        return label(self.raw / "decisions.csv", self.raw / "action_outcomes.csv", self.protocol, self.root / "dataset")

    def test_balanced_fixture_labels(self):
        rows = self.labels()
        self.assertEqual(len(rows), 72)
        self.assertEqual(sum(r["label"] == 1 for r in rows), 36)
        self.assertTrue(all(r["label_reason"] == "total_excess_gap_s" for r in rows))

    def test_missing_action_rejected(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows.pop())
        with self.assertRaisesRegex(ContractError, "Missing paired"):
            self.labels()

    def test_duplicate_action_rejected(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows.append(dict(rows[0])))
        with self.assertRaisesRegex(ContractError, "Duplicate action"):
            self.labels()

    def test_state_mismatch_rejected(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[0].update(predecision_hash="0"*64))
        with self.assertRaisesRegex(ContractError, "state/history"):
            self.labels()

    def test_future_features_rejected(self):
        self.rewrite("decisions.csv", lambda rows: rows[0].update(feature_time_s="11"))
        with self.assertRaisesRegex(ContractError, "Future feature"):
            self.labels()

    def test_stale_features_rejected(self):
        self.rewrite("decisions.csv", lambda rows: rows[0].update(feature_time_s="9"))
        with self.assertRaisesRegex(ContractError, "Stale"):
            self.labels()

    def test_group_split_leakage_rejected(self):
        self.rewrite("decisions.csv", lambda rows: rows[24].update(group_id=rows[0]["group_id"]))
        with self.assertRaisesRegex(ContractError, "group_id crosses"):
            self.labels()

    def test_duplicate_features_across_splits_rejected(self):
        from aiori_pipeline.ml import FEATURES
        self.rewrite("decisions.csv", lambda rows: rows[24].update({k: rows[0][k] for k in FEATURES}))
        with self.assertRaisesRegex(ContractError, "feature_fingerprint"):
            self.labels()

    def test_censoring_excludes_label(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[0].update(status="censored", total_excess_gap_s=""))
        rows = self.labels()
        self.assertEqual(rows[0]["label"], -1)
        self.assertEqual(rows[0]["label_reason"], "censored")

    def test_tie_is_not_a_stay_label(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[0].update(total_excess_gap_s=rows[1]["total_excess_gap_s"]))
        rows = self.labels()
        self.assertEqual(rows[0]["label"], -1)
        self.assertEqual(rows[0]["label_reason"], "tie")

    def test_failure_priority_over_throughput(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[1].update(service_failures="1", throughput_mbps="100"))
        rows = self.labels()
        self.assertEqual(rows[0]["label"], 0)
        self.assertEqual(rows[0]["label_reason"], "service_failures")

    def test_horizon_mismatch_rejected(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[0].update(window_end_s="12"))
        with self.assertRaisesRegex(ContractError, "horizon"):
            self.labels()

    def test_dataset_tampering_rejected(self):
        self.labels()
        path = self.root / "dataset" / "labelled.csv"
        path.write_text(path.read_text()+"\n")
        with self.assertRaisesRegex(ContractError, "changed since"):
            dataset(self.root / "dataset")

    def test_synthetic_requires_explicit_flag(self):
        self.labels()
        with self.assertRaisesRegex(ContractError, "allow-synthetic"):
            train(self.root / "dataset", self.root / "model")

    def test_no_overwrite(self):
        self.labels()
        with self.assertRaisesRegex(ContractError, "already populated"):
            self.labels()

    def test_train_export_and_heldout_evaluation(self):
        self.labels()
        report = train(self.root / "dataset", self.root / "model", allow_synthetic=True, trees=16)
        self.assertTrue(report["synthetic"])
        self.assertNotIn("test", report)
        self.assertEqual(report["reserved_test_rows"], 24)
        model_path = self.root / "model" / "model.json"
        model = json.loads(model_path.read_text())
        golden = json.loads((model_path.parent / "golden_predictions.json").read_text())
        for item in golden:
            self.assertAlmostEqual(probability(model, item["features"]), item["probability_handover"])
        final = evaluate(self.root / "dataset", model_path, self.root / "evaluation", allow_synthetic=True)
        self.assertEqual(final["rows"], 24)
        self.assertGreaterEqual(final["balanced_accuracy"], 0.9)

    def test_json_prediction_rejects_bad_schema(self):
        with self.assertRaisesRegex(ContractError, "schema"):
            probability({}, {})

    def test_mixed_synthetic_and_real_rejected(self):
        self.rewrite("decisions.csv", lambda rows: rows[0].update(synthetic="false"))
        with self.assertRaisesRegex(ContractError, "mix synthetic"):
            self.labels()

    def test_real_training_requires_frozen_protocol(self):
        self.rewrite("decisions.csv", lambda rows: [r.update(synthetic="false") for r in rows])
        self.labels()
        with self.assertRaisesRegex(ContractError, "Freeze"):
            train(self.root / "dataset", self.root / "model")

    def test_manifest_cannot_disguise_synthetic_data(self):
        self.labels()
        path = self.root / "dataset" / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["synthetic"] = "false"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ContractError, "synthetic mismatch"):
            train(self.root / "dataset", self.root / "model")

    def test_throughput_breaks_gap_tie(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[1].update(total_excess_gap_s=rows[0]["total_excess_gap_s"], throughput_mbps="3.1"))
        rows = self.labels()
        self.assertEqual(rows[0]["label"], 1)
        self.assertEqual(rows[0]["label_reason"], "throughput_mbps")

    def test_nonfinite_outcomes_rejected(self):
        self.rewrite("action_outcomes.csv", lambda rows: rows[0].update(throughput_mbps="NaN"))
        with self.assertRaisesRegex(ContractError, "throughput"):
            self.labels()

    def test_single_class_training_rejected(self):
        def force_stay(rows):
            for r in rows:
                if "_train_" in r["decision_id"]:
                    r["service_failures"] = "1" if r["action"] == "handover" else "0"
        self.rewrite("action_outcomes.csv", force_stay)
        self.labels()
        with self.assertRaisesRegex(ContractError, "both labelled classes"):
            train(self.root / "dataset", self.root / "model", allow_synthetic=True)

    def test_test_group_cannot_be_a_development_group(self):
        self.labels()
        train(self.root / "dataset", self.root / "model", allow_synthetic=True, trees=4)
        path = self.root / "model" / "model.json"
        model = json.loads(path.read_text())
        model["development_groups"].append("SYNTHETIC_test_0")
        path.write_text(json.dumps(model))
        with self.assertRaisesRegex(ContractError, "Test group seen"):
            evaluate(self.root / "dataset", path, self.root / "evaluation", allow_synthetic=True)


if __name__ == "__main__":
    unittest.main()
