"""Fit XGBoost and Logistic Regression on verified packet-preference pilot rows."""

import argparse
import json
import math
import statistics
from pathlib import Path

import numpy as np
import sklearn
import xgboost
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

from .ml import FEATURES, dump, fresh_output, scores, sha
from .prototype import THRESHOLD, UNITS, prepare, training_data


def tree_nodes(native_tree):
    nodes = []

    def visit(node):
        index = len(nodes)
        nodes.append(None)
        if "leaf" in node:
            nodes[index] = [-1, float(node["leaf"]), -1, -1]
        else:
            children = {child["nodeid"]: child for child in node["children"]}
            left = visit(children[node["yes"]])
            right = visit(children[node["no"]])
            nodes[index] = [int(node["split"][1:]), float(node["split_condition"]), left, right]
        return index

    visit(native_tree)
    return nodes


def portable_scores(x, trees, linear):
    margin = np.float32(0)
    for tree in trees:
        feature, value, left, right = tree[0]
        while feature >= 0:
            index = left if np.float32(x[feature]) < np.float32(value) else right
            feature, value, left, right = tree[index]
        margin = np.float32(margin + np.float32(value))
    linear_margin = linear["intercept"] + sum(
        coeff * (value - mean) / scale
        for value, coeff, mean, scale in zip(x, linear["coefficients"], linear["means"], linear["scales"])
    )
    return [1 / (1 + math.exp(-float(z))) for z in (margin, linear_margin)]


def training_metrics(rows, prediction):
    metrics = scores(rows, prediction, THRESHOLD)
    metrics["handover_average_precision"] = float(average_precision_score(
        [row["label"] for row in rows], prediction,
    ))
    return metrics


def export_cpp(out, artifact, probes, native):
    def literals(values):
        return ", ".join(repr(float(value)) for value in values)

    offsets, nodes = [], []
    for tree in artifact["models"]["xgboost"]["trees"]:
        offset = len(nodes)
        offsets.append(offset)
        for feature, value, left, right in tree:
            nodes.append(f"    {{{feature}, {value!r}f, {left + offset}, {right + offset}}}")
    linear = artifact["models"]["logistic"]
    serialized_nodes = ",\n".join(nodes)
    (out / "handover_prototypes.hpp").write_text("""// Generated model export. C++17. Scores are exploratory.
#pragma once
#include <array>
#include <cmath>
#include <cstddef>

namespace aiori_prototypes {
struct Node { int feature; float value; int left; int right; };
struct Result { bool valid; double score; int action; };
using Input = std::array<double, 7>;
""" + f"""inline constexpr double threshold = {artifact['threshold']};
inline constexpr double missingSlope = {artifact['missing_slope_median']};
inline constexpr double intercept = {linear['intercept']};
inline constexpr Input coefficients = {{{literals(linear['coefficients'])}}};
inline constexpr Input means = {{{literals(linear['means'])}}};
inline constexpr Input scales = {{{literals(linear['scales'])}}};
inline constexpr int offsets[] = {{{', '.join(map(str, offsets))}}};
inline constexpr Node nodes[] = {{
{serialized_nodes}
}};
""" + """
inline std::array<Result, 2> Predict(Input x) {
    const Result invalid{false, 0.0, -1};
    if (x[4] == 0.0) x[3] = missingSlope;
    for (double value : x) {
        if (!std::isfinite(static_cast<float>(value))) return {invalid, invalid};
    }
    if ((x[4] != 0 && x[4] != 1) || std::abs(x[1] - x[0] - x[2]) > 1e-5 ||
        x[5] <= 0 || x[6] < 0 || x[6] > 0.5) return {invalid, invalid};

    float treeMargin = 0;
    for (int index : offsets) {
        while (nodes[index].feature >= 0) {
            const auto &node = nodes[index];
            index = static_cast<float>(x[node.feature]) < node.value ? node.left : node.right;
        }
        treeMargin += nodes[index].value;
    }

    double linearMargin = intercept;
    for (std::size_t i = 0; i < x.size(); ++i) {
        linearMargin += coefficients[i] * ((x[i] - means[i]) / scales[i]);
    }
    auto result = [](double margin) {
        const double score = 1.0 / (1.0 + std::exp(-margin));
        return Result{true, score, static_cast<int>(score >= threshold)};
    };
    return {result(treeMargin), result(linearMargin)};
}
} // namespace aiori_prototypes
""", encoding="utf-8")

    cases = []
    for x, prediction in zip(probes, native):
        if abs(x[1] - x[0] - x[2]) <= 1e-5:
            values = literals(x) if x[4] else literals(x[:3]) + ", missing, " + literals(x[4:])
            cases.append(f"    {{{{{values}}}, {{{literals(prediction)}}}}}")
    valid_count = len(cases)
    (out / "prototype_parity.cpp").write_text("""#include "handover_prototypes.hpp"
#include <iostream>
#include <limits>
int main() {
    using namespace aiori_prototypes;
    const auto missing = std::numeric_limits<double>::quiet_NaN();
    const struct { Input x; std::array<double, 2> scores; } cases[] = {
""" + ",\n".join(cases) + """
    };
    for (const auto &item : cases) {
        const auto outputs = Predict(item.x);
        for (std::size_t i = 0; i < outputs.size(); ++i) {
            if (!outputs[i].valid || std::abs(outputs[i].score - item.scores[i]) > 1e-6 ||
                outputs[i].action != int(item.scores[i] >= threshold)) return 1;
        }
    }
    auto bad = cases[0].x;
    bad[5] = 0.0;
    for (const auto &result : Predict(bad)) if (result.valid || result.action != -1) return 1;
    std::cout << "PASS (" << sizeof(cases) / sizeof(cases[0]) << " score and action cases)\\n";
}
""", encoding="utf-8")
    return valid_count


def train(dataset, output):
    rows, report, protocol = training_data(dataset)
    out = fresh_output(output, [dataset])
    medians = [statistics.median([float(row[key]) for row in rows if row[key] != ""] or [0.0])
               for key in FEATURES]
    x = np.array([[prepare(row, medians)[key] for key in FEATURES] for row in rows])
    y = np.array([row["label"] for row in rows])
    weights = np.array([row["sample_weight"] for row in rows])

    boosted = xgboost.XGBClassifier(
        objective="binary:logistic", base_score=0.5, boost_from_average=0,
        n_estimators=24, max_depth=2, learning_rate=0.2, min_child_weight=0.05,
        reg_lambda=1.0, tree_method="hist", n_jobs=1, random_state=42,
    ).fit(x, y, sample_weight=weights)
    scaler = StandardScaler().fit(x, sample_weight=weights)
    logreg = LogisticRegression(max_iter=2000).fit(scaler.transform(x), y, sample_weight=weights)
    trees = [tree_nodes(json.loads(tree)) for tree in boosted.get_booster().get_dump(dump_format="json")]
    linear = {
        "intercept": float(logreg.intercept_[0]), "coefficients": logreg.coef_[0].tolist(),
        "means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
    }

    # Probe real inputs, unavailable slopes, and both sides of each tree threshold.
    scenarios = x.tolist()
    for vector in x.tolist():
        vector[3:5] = [medians[3], 0]
        scenarios.append(vector)
    for tree in trees:
        for feature, threshold, _, _ in tree:
            if feature >= 0:
                split = np.float32(threshold)
                for boundary in (np.nextafter(split, np.float32(-np.inf)), split, np.nextafter(split, np.float32(np.inf))):
                    probe = x[0].copy()
                    probe[feature] = boundary
                    if feature in (0, 1):
                        probe[2] = probe[1] - probe[0]
                    elif feature == 2:
                        probe[1] = probe[0] + probe[2]
                    scenarios.append(probe.tolist())

    probes = np.unique(scenarios, axis=0)
    native = np.column_stack([boosted.predict_proba(probes)[:, 1], logreg.predict_proba(scaler.transform(probes))[:, 1]])
    replayed = np.array([portable_scores(vector, trees, linear) for vector in probes])
    max_error = np.max(np.abs(replayed - native), axis=0)
    if not np.all(max_error <= 1e-6) or not np.array_equal(native >= THRESHOLD, replayed >= THRESHOLD):
        raise RuntimeError(f"Portable inference failed parity. Maximum errors {max_error}")

    xgb_predictions = boosted.predict_proba(x)[:, 1]
    lr_predictions = logreg.predict_proba(scaler.transform(x))[:, 1]
    unique_examples = {}
    for vector, label in zip(x, y):
        example = unique_examples.setdefault(tuple(vector), {"features": vector.tolist(), "class_counts": {"0": 0, "1": 0}})
        example["class_counts"][str(label)] += 1
    dataset_sha = sha(Path(dataset) / "training.csv")
    artifact = {
        "schema_version": 1,
        "model_status": "integration_prototype_unvalidated",
        "label_scope": report["label_scope"],
        "protocol_id": protocol["protocol_id"],
        "dataset_sha256": dataset_sha,
        "dataset_report_sha256": sha(Path(dataset) / "dataset_report.json"),
        "features": [{"name": name, "unit": unit} for name, unit in zip(FEATURES, UNITS)],
        "missing_slope_median": medians[3],
        "threshold": THRESHOLD,
        "threshold_tuned": False,
        "training_weighting": "Each repeated feature vector contributes a total weight of one",
        "training_rows": len(rows),
        "unique_feature_vectors": len(unique_examples),
        "conflicting_feature_vectors": sum(all(example["class_counts"].values()) for example in unique_examples.values()),
        "class_counts": report["primary_training"]["class_counts"],
        "validation_metrics": None,
        "test_metrics": None,
        "parity_case_count": len(probes),
        "models": {
            "xgboost": {"id": f"xgboost-packet-v1-{dataset_sha[:12]}", "trees": trees,
                        "training_metrics": training_metrics(rows, xgb_predictions), "parity_max_error": float(max_error[0])},
            "logistic": {"id": f"logistic-packet-v1-{dataset_sha[:12]}", **linear,
                         "training_metrics": training_metrics(rows, lr_predictions), "parity_max_error": float(max_error[1])},
        },
        "examples": list(unique_examples.values()),
        "fit": {"xgboost_version": xgboost.__version__, "sklearn_version": sklearn.__version__,
                "xgboost_parameters": boosted.get_params(), "logistic_parameters": logreg.get_params()},
    }
    # sklearn/XGBoost use NaN as an internal missing-value configuration sentinel.
    del artifact["fit"]["xgboost_parameters"]["missing"]
    boosted.save_model(out / "xgboost.json")
    artifact["cpp_parity_cases"] = export_cpp(out, artifact, probes, native)
    dump(out / "handover-prototypes.json", artifact)
    dump(out / "parity.json", [{"features": vector.tolist(), "scores": prediction.tolist()}
                               for vector, prediction in zip(probes, native)])
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = train(args.dataset, args.output)
    print(json.dumps({name: model[name] for name in ("training_rows", "unique_feature_vectors", "class_counts", "dataset_sha256", "parity_case_count")}))


if __name__ == "__main__":
    main()
