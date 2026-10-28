"""Explicit integration-only RF fitting for observed packet-preference pilots.

This separate path never relaxes ml.train's independent validation requirements.
"""
import argparse
import csv
import json
import math
import platform
import re
import statistics
import struct
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .ml import (DECISIONS, FEATURES, dump, feature_fingerprint, fresh_output, integer,
                 number, probability, read_csv, scores, sha, validate_decisions)
from .packet_labels import EXTRA, load_protocol
from .pipeline import ContractError, require

THRESHOLD = .6
UNITS = ['dBm', 'dBm', 'dB', 'dB/s', '0 or 1', 'm/s', 's']


def prepare(row, medians):
    """The online contract: unavailable slope is imputed; other missing inputs fail."""
    values = {k:row.get(k) for k in FEATURES}
    trend = integer(values['trend_available'], 'trend_available')
    require(trend in {0, 1}, 'Invalid trend_available')
    if not trend:
        values['delta_slope_db_per_s'] = medians[3]
    for key in FEATURES:
        values[key] = number(values[key], key)
    require(abs(values['rsrp_delta_db']-(values['candidate_rsrp_dbm']-values['serving_rsrp_dbm'])) <= 1e-5,
            'Inconsistent RSRP difference')
    require(values['speed_mps'] > 0 and 0 <= values['mobility_age_s'] <= .5, 'Invalid speed/mobility age')
    try:
        require(all(math.isfinite(struct.unpack('f',struct.pack('f',v))[0]) for v in values.values()), 'Input overflows float32')
    except OverflowError:
        raise ContractError('Input overflows float32') from None
    return values


def predict(model, row):
    try:
        features = prepare(row, model['medians'])
        p = probability(model, features)
    except (ContractError, KeyError, OverflowError, ValueError):
        return {'valid':False, 'probability_handover':None, 'prediction':None}
    return {'valid':True, 'probability_handover':p, 'prediction':int(p >= model['threshold'])}


def training_data(folder, allow_synthetic=False):
    root = Path(folder)
    report = json.loads((root/'dataset_report.json').read_text(encoding='utf-8'))
    require(report.get('schema_version') == 1 and report.get('label_scope') == 'observed_packet_performance_only', 'Not a packet-preference dataset')
    require(type(report.get('synthetic')) is bool, 'Invalid dataset synthetic flag')
    require(not report['synthetic'] or allow_synthetic, 'Synthetic prototype requires --allow-synthetic')
    for name in ('training.csv','protocol.json'):
        require(report['files_sha256'].get(name) == sha(root/name), f'{name}: dataset checksum changed')
    p = load_protocol(root/'protocol.json')
    require(report['protocol_id'] == p['protocol_id'], 'Dataset/protocol mismatch')
    rows = read_csv(root/'training.csv', DECISIONS+EXTRA,
                    ['delta_slope_db_per_s','stay_service_failures','handover_service_failures'])
    validate_decisions(rows, {'max_feature_age_s':.2})
    require(all(r['synthetic'] == str(report['synthetic']).lower() for r in rows), 'Synthetic flag mismatch')
    for r in rows:
        require(r['training_eligible'] == 'true' and r['split'] == 'train', 'Only explicitly eligible training rows may be fitted')
        require(r['label_protocol_id'] == p['protocol_id'], 'Row label objective mismatch')
        require(r['label'] in {'0','1'}, 'Prototype requires actionable binary labels')
        r['label'] = int(r['label'])
        require(re.fullmatch(r'[0-9a-f]{64}',r['verified_source_sha256']) is not None, 'Missing verified simulator source hash')
        require(r['feature_fingerprint'] == feature_fingerprint(r), 'Feature fingerprint changed')
        r['sample_weight'] = number(r['sample_weight'],'sample_weight',0)
        require(r['sample_weight'] > 0, 'Training weights must be positive')
    require({r['label'] for r in rows} == {0,1}, 'Prototype requires both observed classes')
    totals = defaultdict(float)
    for r in rows:
        totals[r['feature_fingerprint']] += r['sample_weight']
    require(all(abs(v-1.) < 1e-9 for v in totals.values()), 'Each repeated feature vector must have total weight one')
    require(report['primary_training']['rows'] == len(rows), 'Training count mismatch')
    require(report['primary_training']['class_counts'] == dict(Counter(str(r['label']) for r in rows)), 'Training class-count mismatch')
    return rows, report, p


def forest_json(forest):
    index = list(forest.classes_).index(1)
    result = []
    for estimator in forest.estimators_:
        t = estimator.tree_
        result.append({'left':t.children_left.tolist(), 'right':t.children_right.tolist(),
                       'feature':t.feature.tolist(), 'threshold':t.threshold.tolist(),
                       'probability_handover':[float(v[index]/sum(v)) for v in t.value[:,0,:]]})
    return result


def cpp_header(model):
    nodes, offsets = [], []
    for tree in model['trees']:
        offsets.append(len(nodes))
        for i in range(len(tree['left'])):
            nodes.append('    {'+','.join([str(tree['left'][i]),str(tree['right'][i]),str(tree['feature'][i]),
                                           repr(tree['threshold'][i]),repr(tree['probability_handover'][i])])+'}')
    medians = ','.join(repr(v) for v in model['medians'])
    return '''// Generated integration prototype. Unvalidated packet-performance objective.
// Do not edit simulator code to generate this file. C++17 or newer.
#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>

namespace aiori_rf_prototype {
static_assert(std::numeric_limits<float>::is_iec559 && std::numeric_limits<float>::digits == 24,
              "Inference requires IEEE-754 binary32 float");
inline constexpr std::size_t kFeatureCount = 7;
inline constexpr const char* kModelId = "'''+model['model_id']+'''";
inline constexpr double kThreshold = '''+repr(model['threshold'])+''';
inline constexpr std::array<double,7> kMedians = {{'''+medians+'''}};
struct Node { int left; int right; int feature; double threshold; double p; };
inline constexpr Node kNodes[] = {
'''+',\n'.join(nodes)+'''
};
inline constexpr std::size_t kOffsets[] = {'''+','.join(map(str,offsets))+'''};
struct Prediction { bool valid; double probability_handover; int action; };
// Feature order is recorded in preprocessing.json. action=-1 means no valid prediction.
inline Prediction Predict(std::array<double,7> x) noexcept {
    const Prediction invalid{false, std::numeric_limits<double>::quiet_NaN(), -1};
    if (x[4] != 0.0 && x[4] != 1.0) return invalid;
    if (x[4] == 0.0) x[3] = kMedians[3];
    for (double value : x) if (!std::isfinite(value)) return invalid;
    if (std::abs(x[2]-(x[1]-x[0])) > 1e-5 || x[5] <= 0.0 || x[6] < 0.0 || x[6] > 0.5)
        return invalid;
    // sklearn compares float32 predictor inputs against double tree thresholds.
    for (double& value : x) {
        value = static_cast<float>(value);
        if (!std::isfinite(value)) return invalid;
    }
    double sum = 0.0;
    for (std::size_t offset : kOffsets) {
        int node = 0;
        while (kNodes[offset+node].left != -1) {
            const Node& n = kNodes[offset+node];
            node = x[n.feature] <= n.threshold ? n.left : n.right;
        }
        sum += kNodes[offset+node].p;
    }
    const double p = sum / (sizeof(kOffsets)/sizeof(kOffsets[0]));
    return Prediction{true, p, p >= kThreshold ? 1 : 0};
}
} // namespace aiori_rf_prototype
'''


def parity_cpp(golden):
    lines = []
    for item in golden:
        x = ','.join('std::numeric_limits<double>::quiet_NaN()' if item['features'][k] is None else repr(item['features'][k]) for k in FEATURES)
        valid = item['valid']
        p = repr(item['probability_handover']) if valid else '0.0'
        action = str(item['prediction']) if valid else '-1'
        lines.append('    {"'+item['id']+'", {{'+x+'}}, '+str(valid).lower()+', '+p+', '+action+'}')
    return '''#include "rf_prototype.hpp"
#include <iostream>
struct Check { const char* id; std::array<double,7> x; bool valid; double p; int action; };
int main() {
    const Check checks[] = {
'''+',\n'.join(lines)+'''
    };
    for (const auto& c : checks) {
        auto prediction = aiori_rf_prototype::Predict(c.x);
        if (prediction.valid != c.valid || prediction.action != c.action ||
            (c.valid && std::abs(prediction.probability_handover-c.p) > 1e-12)) {
            std::cerr << "FAIL " << c.id << "\\n"; return 1;
        }
    }
    std::cout << "PASS: C++ inference matches golden predictions\\n";
    return 0;
}
'''


def train_prototype(folder, output, allow_synthetic=False):
    rows, dataset_report, p = training_data(folder, allow_synthetic)
    try:
        import sklearn
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        raise ContractError('Install the optional ML dependencies before fitting') from None
    medians = [statistics.median(float(r[k]) for r in rows if r[k] != '')
               if any(r[k] != '' for r in rows) else 0. for k in FEATURES]
    xs = [[prepare(r,medians)[k] for k in FEATURES] for r in rows]
    forest = RandomForestClassifier(n_estimators=128,max_depth=8,min_samples_leaf=2,
                                    class_weight='balanced_subsample',random_state=42,n_jobs=1)
    forest.fit(xs,[r['label'] for r in rows],sample_weight=[r['sample_weight'] for r in rows])
    model = {'schema_version':1, 'model_id':'rf-prototype-packet-v1-'+sha(Path(folder)/'training.csv')[:12],
             'model_status':'integration_prototype_unvalidated', 'label_scope':'observed_packet_performance_only',
             'features':FEATURES,'classes':['stay','handover'],'medians':medians,'threshold':THRESHOLD,
             'synthetic':dataset_report['synthetic'], 'protocol':p,'trees':forest_json(forest),
             'dataset_sha256':sha(Path(folder)/'training.csv'), 'dataset_report_sha256':sha(Path(folder)/'dataset_report.json'),
             'implementation_sha256':sha(__file__), 'python_version':platform.python_version(),
             'sklearn_version':sklearn.__version__,'training_parameters':forest.get_params(),
             'fit_groups':sorted({r['group_id'] for r in rows}),
             'fit_predecision_hashes':sorted({r['predecision_hash'] for r in rows}),
             'fit_feature_fingerprints':sorted({feature_fingerprint(r) for r in rows}),
             'verified_simulator_source_sha256':sorted({r['verified_source_sha256'] for r in rows}),
             'independent_validation_available':False, 'service_failure_aware':False,
             'probability_interpretation':'Uncalibrated RF weighted-leaf class score; not a guarantee of action benefit.'}
    expected = forest.predict_proba(xs)[:,list(forest.classes_).index(1)]
    actual = [predict(model,r)['probability_handover'] for r in rows]
    error = max(abs(a-b) for a,b in zip(actual,expected))
    require(error < 1e-12,'Exported JSON/sklearn prediction parity failed')
    golden, seen = [], set()
    for r in rows:
        fp = feature_fingerprint(r)
        if fp not in seen:
            seen.add(fp)
            features = {k:None if r[k] == '' else float(r[k]) for k in FEATURES}
            golden.append({'id':'training-state-'+str(len(golden)), 'kind':'observed_training_input',
                           'features':features, **predict(model,features)})
    missing = dict(golden[0]['features'], delta_slope_db_per_s=None, trend_available=0.)
    invalid = dict(golden[0]['features'], serving_rsrp_dbm=None)
    for name, features in [('missing-trend-fixture',missing),('invalid-serving-fixture',invalid)]:
        result = predict(model,features)
        if result['valid']:
            x = [[prepare(features,medians)[k] for k in FEATURES]]
            reference = float(forest.predict_proba(x)[0,list(forest.classes_).index(1)])
            require(abs(reference-result['probability_handover'])<1e-12,'Imputation parity failed')
        golden.append({'id':name,'kind':'software_fixture','features':features,**result})
    preprocessing = {'schema_version':1,'model_id':model['model_id'],
                     'feature_order':[{'index':i,'name':k,'unit':UNITS[i]} for i,k in enumerate(FEATURES)],
                     'scaling':'none', 'medians':dict(zip(FEATURES,medians)),
                     'missing_trend':'When trend_available=0, ignore the supplied slope and use training median at index 3. JSON null/C++ NaN is accepted there only.',
                     'invalid_inputs':'Reject missing/nonfinite required values, trend flags outside {0,1}, RSRP delta mismatch >1e-5, speed<=0, or mobility age outside [0,0.5].',
                     'tree_input_dtype':'IEEE-754 float32', 'comparison':'<= goes to left child; otherwise right',
                     'aggregation':'Mean of probability_handover at reached leaves across 128 trees',
                     'decision':'HANDOVER (1) iff probability_handover >= 0.6; otherwise STAY (0). Invalid predictions have no action.',
                     'cadence_s':.2,'feature_max_age_s':.2,
                     'simulator_responsibilities':['Use only pre-action measurements and the agreed slope/candidate history.',
                         'Select/validate the candidate cell; the binary forest does not output a cell ID.',
                         'Gate active handovers, RRC state, measurement freshness, target validity and agreed cooldown.',
                         'On invalid inputs do not trigger an RF handover; apply the explicitly documented fallback.',
                         'Log RF score, raw prediction, actual gated action, target and model ID.']}
    report = {'model_id':model['model_id'],'model_status':model['model_status'],
              'training_rows':len(rows),'unique_feature_vectors':len(seen),
              'class_counts':dict(Counter(str(r['label']) for r in rows)),
              'prediction_counts_on_training_inputs':dict(Counter(str(int(v>=THRESHOLD)) for v in actual)),
              'training_resubstitution_metrics_only':scores(rows,actual,THRESHOLD),
              'validation_metrics':None, 'test_metrics':None, 'independent_validation_available':False,
              'json_sklearn_max_absolute_error':float(error),
              'cpp_compile_and_parity':'not_run: no local C++ compiler was found; run the included standalone checker on Joe\u2019s system',
              'hyperparameter_search_performed':False,'threshold_tuned':False,
              'training_weighting':'Use supplied per-feature-vector weights, multiplied by balanced_subsample class weights within each tree.',
              'input_ranges':{k:{'min':min(x[i] for x in xs),'max':max(x[i] for x in xs)} for i,k in enumerate(FEATURES)},
              'limitations':dataset_report['limitations']+[
                  'This prototype is fit on all eligible primary rows; no held-out accuracy is available.',
                  'A single STAY observation and four distinct inputs cannot establish a useful policy.',
                  'Training class weighting changes scores; 0.6 is the agreed initial threshold, not a calibrated confidence.',
                  'This export does not implement or validate an ns-3 policy and does not establish RF improvement over A3.']}
    out = fresh_output(output,[folder])
    dump(out/'model.json',model)
    dump(out/'preprocessing.json',preprocessing)
    dump(out/'golden_predictions.json',golden)
    dump(out/'training_report.json',report)
    dump(out/'protocol.json',p)
    (out/'rf_prototype.hpp').write_text(cpp_header(model),encoding='utf-8')
    (out/'rf_parity_check.cpp').write_text(parity_cpp(golden),encoding='utf-8')
    guide = '''# RF prototype handoff for Joe

This is an UNVALIDATED INTEGRATION PROTOTYPE trained on 16 real paired outcomes
(15 HANDOVER, 1 STAY), four unique feature vectors and one related scenario family.
Its objective is observed reception-gap preference, with throughput breaking close
ties. Unknown service failures were not made zero or used as labels. It cannot
support claims of better connectivity or RF improvement over A3.

Use model.json with a JSON evaluator, or include rf_prototype.hpp in your separate
RF controller. The generated header contains the forest and preprocessing; it
needs C++17+, no Python process and no third-party inference library.
It is an export artifact; no existing ns-3 source was changed.

Feature order (all double inputs):
0 serving_rsrp_dbm (dBm)
1 candidate_rsrp_dbm (dBm)
2 rsrp_delta_db (candidate minus serving, dB)
3 delta_slope_db_per_s (same-cell history, dB/s)
4 trend_available (0 or 1)
5 speed_mps (m/s; divide km/h by 3.6)
6 mobility_age_s (s)

Call aiori_rf_prototype::Predict(std::array<double,7>{...}). The return fields are
valid, probability_handover and action (0=STAY, 1=HANDOVER, -1=invalid). With trend
unavailable, set index 4 to 0 and index 3 to NaN; the trained median is applied.
Other missing inputs are rejected. Threshold is fixed at 0.6, using >=.
The RF score is not calibrated confidence. preprocessing.json defines the rules.

Before integrating, run the standalone parity checker in this export directory:

    g++ -std=c++17 -O2 rf_parity_check.cpp -o rf_parity_check
    ./rf_parity_check

It should print PASS and exit 0. No local compiler was available here, so this
C++ compilation is not claimed as completed. Python JSON predictions have been
checked against sklearn. golden_predictions.json includes all four observed
inputs plus missing-trend and invalid-input software checks.

Keep your simulator's RRC/active-HO/target/freshness gates. The forest only returns
a binary action; select the candidate before inference. Run at the agreed 200 ms
cadence and document the follow-up/cooldown/fallback policy separately. Do not
substitute the model threshold for those gates. Log the model ID, features, score,
requested action, gate result, final action and selected cell.

First compare your C++ predictions with every golden record. Then run fresh,
matched live A3/RF simulations at both speeds and record the existing metrics.
Those are integration/benchmark experiments, not evidence already established by
this training file. Training-only metrics are in training_report.json; validation
and test metrics are deliberately null. No simulator code is included or edited.
'''
    (out/'JOE_INTEGRATION.md').write_text(guide,encoding='utf-8')
    files = [path for path in sorted(out.iterdir()) if path.is_file()]
    (out/'SHA256SUMS.txt').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in files),encoding='utf-8')
    with zipfile.ZipFile(out/'rf_prototype_v1.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.iterdir()):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path,path.name)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset')
    parser.add_argument('--output',required=True)
    parser.add_argument('--allow-synthetic',action='store_true')
    args = parser.parse_args(argv)
    try:
        report = train_prototype(args.dataset,args.output,args.allow_synthetic)
    except (ContractError,OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 2
    print(json.dumps({k:report[k] for k in ['model_id','training_rows','class_counts','prediction_counts_on_training_inputs','json_sklearn_max_absolute_error','independent_validation_available']},indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
