"""Build exploratory packet-performance labels from freshly audited pilot archives.

This intentionally does not change the existing service-failure-first ML workflow.
It never trains a model or claims held-out performance.
"""
import argparse
import csv
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .ml import DECISIONS, FEATURES, dump, feature_fingerprint, fresh_output, number, sha
from .pilot import digest, import_pilot
from .pipeline import ContractError, require, write_csv

EXTRA = ['source_batch', 'source_pair_id', 'verified_source_sha256', 'training_eligible',
         'label', 'label_reason', 'label_protocol_id', 'stay_total_excess_gap_s',
         'handover_total_excess_gap_s', 'stay_throughput_mbps', 'handover_throughput_mbps',
         'stay_service_failures', 'handover_service_failures', 'feature_fingerprint', 'sample_weight']
FIELDS = DECISIONS + EXTRA
FAMILY = 'conservative-three-cell-linear-pilot-family'


def load_protocol(path):
    p = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    require(p.get('schema_version') == 1 and p.get('protocol_id') == 'observed-packet-preference-v1', 'Unknown packet label protocol')
    require(p.get('objective') == 'observed_packet_performance' and
            p.get('priority') == ['total_excess_gap_s', 'throughput_mbps'], 'Unsupported packet objective')
    require(p.get('service_failure_treatment') == 'excluded_from_this_objective; unknown_values_preserved',
            'Service failures must remain outside this explicitly limited objective')
    for key in ['horizon_s','action_hold_s','gap_margin_s','throughput_margin_mbps']:
        p[key] = number(p.get(key), key, 0)
    require(0 < p['action_hold_s'] <= p['horizon_s'], 'Invalid packet observation horizon')
    return p


def packet_preference(stay, handover, p):
    if any(o['window_censored'] or o.get('unfinished_handover_at_window_end', False) for o in (stay, handover)):
        return -1, 'incomplete_observation'
    difference = number(handover['total_excess_gap_s'], 'handover gap', 0)-number(stay['total_excess_gap_s'], 'stay gap', 0)
    if abs(difference) > p['gap_margin_s']+1e-12:
        return int(difference < 0), 'total_excess_gap_s'
    difference = number(handover['throughput_mbps'], 'handover throughput', 0)-number(stay['throughput_mbps'], 'stay throughput', 0)
    if abs(difference) > p['throughput_margin_mbps']+1e-12:
        return int(difference > 0), 'throughput_mbps'
    return -1, 'tie'


def make_rows(decisions, audit, batch, p):
    require(audit['data_checks_passed'] and not audit['errors'], 'Pilot audit failed; no labels may be generated')
    pairs = {r['predecision_hash']:r for r in audit['pairs']}
    require(len(pairs) == len(decisions), 'Audit/decision count mismatch')
    verified = audit.get('provenance', {}).get('verified_source_sha256', '')
    rows = []
    for d in decisions:
        pair = pairs[d['predecision_hash']]
        require(pair['config']['horizon_s'] == p['horizon_s'] and pair['config']['action_hold_s'] == p['action_hold_s'], 'Packet label window/hold differs from the recorded experiment')
        stay, handover = pair['outcomes']['stay'], pair['outcomes']['handover']
        target, reason = packet_preference(stay, handover, p)
        row = dict(d)
        # All pilots share one conservative family. Nothing is held out by row.
        row.update(group_id=FAMILY, split='train', scenario_id='as-exported-three-cell-linear-pilot',
                   config_id='exported-partial-'+digest(pair['config']), source_batch=batch,
                   source_pair_id=pair['pair_id'], verified_source_sha256=verified,
                   training_eligible=str(bool(verified) and target != -1).lower(),
                   label=target, label_reason=reason, label_protocol_id=p['protocol_id'],
                   stay_total_excess_gap_s=stay['total_excess_gap_s'],
                   handover_total_excess_gap_s=handover['total_excess_gap_s'],
                   stay_throughput_mbps=stay['throughput_mbps'], handover_throughput_mbps=handover['throughput_mbps'],
                   stay_service_failures=stay['service_failures'], handover_service_failures=handover['service_failures'],
                   feature_fingerprint=feature_fingerprint(d), sample_weight=0.)
        rows.append(row)
    return rows


def summarize(rows):
    by_features = defaultdict(list)
    for r in rows:
        by_features[r['feature_fingerprint']].append(r)
    return {'rows':len(rows), 'class_counts':dict(Counter(str(r['label']) for r in rows)),
            'unique_feature_vectors':len(by_features), 'scenario_families':len({r['group_id'] for r in rows}),
            'conflicting_feature_groups':[
                {'feature_fingerprint':fp, 'source_pair_ids':[r['source_pair_id'] for r in members],
                 'class_counts':dict(Counter(str(r['label']) for r in members))}
                for fp,members in by_features.items() if len({r['label'] for r in members}-{ -1 }) > 1]}


def build(inputs, output, protocol_path):
    require(bool(inputs) and len({Path(v).resolve() for v in inputs}) == len(inputs), 'Input archives must be distinct')
    p = load_protocol(protocol_path)
    out = fresh_output(output, [*inputs, protocol_path])
    rows, sources = [], []
    for index, path in enumerate(inputs):
        batch = f'batch-{index+1}-{Path(path).stem}'
        intake_dir = out/'audits'/batch
        audit = import_pilot(path, intake_dir)
        require(audit['data_checks_passed'], f'{batch}: intake failed; see {intake_dir / "audit.json"}')
        with (intake_dir/'decisions.csv').open(encoding='utf-8-sig', newline='') as f:
            decisions = list(csv.DictReader(f))
        rows.extend(make_rows(decisions, audit, batch, p))
        sources.append({'batch':batch, 'archive':str(Path(path).resolve()), 'archive_sha256':sha(path),
                        'audit_sha256':sha(intake_dir/'audit.json'),
                        'verified_source_sha256':audit.get('provenance', {}).get('verified_source_sha256'),
                        'source_provenance':'verified archived source' if audit.get('provenance', {}).get('verified_source_sha256') else 'archived source unavailable; supplemental only'})
    require(len({r['decision_id'] for r in rows}) == len(rows), 'Duplicate paired decision evidence across archives')
    require(len({r['synthetic'] for r in rows}) == 1, 'Cannot mix real and synthetic rows')
    training = [r for r in rows if r['training_eligible'] == 'true']
    require(bool(training), 'No uncensored pairs with verified archived source; no training dataset written')
    counts = Counter(r['feature_fingerprint'] for r in training)
    for r in training:
        r['sample_weight'] = 1/counts[r['feature_fingerprint']]
    supplemental = [r for r in rows if r['training_eligible'] != 'true']
    write_csv(out/'labelled_all.csv', rows, FIELDS)
    write_csv(out/'training.csv', training, FIELDS)
    write_csv(out/'supplemental.csv', supplemental, FIELDS)
    write_csv(out/'training_X.csv', [{k:r[k] for k in FEATURES} for r in training], FEATURES)
    write_csv(out/'training_y.csv', [{k:r[k] for k in ['decision_id','label','sample_weight']} for r in training], ['decision_id','label','sample_weight'])
    dump(out/'protocol.json', p)
    report = {'schema_version':1, 'label_scope':'observed_packet_performance_only',
              'synthetic':rows[0]['synthetic']=='true', 'protocol_id':p['protocol_id'],
              'all_pairs':summarize(rows), 'primary_training':summarize(training),
              'supplemental':summarize(supplemental), 'splits':{'train':len(training),'validation':0,'test':0},
              'all_service_failure_counts_preserved':True, 'unknown_service_failure_values':sum(r[k]=='' for r in rows for k in ['stay_service_failures','handover_service_failures']),
              'model_trained':False, 'independent_validation_available':False,
              'validated_training_workflow_ready':False,
              'sample_weight_definition':'Each unique primary seven-feature vector has total weight 1; no class oversampling or fabricated rows.',
              'sources':sources,
              'limitations':p['limitations']+[
                  'Primary training rows require source SHA256 verification; other audited labels are supplemental.',
                  'config_id hashes the exported partial configuration, not a complete resolved simulator configuration.',
                  'This dataset cannot establish RF generalization or improvement over A3.',
                  'The existing service-failure-first validated trainer is unchanged and is not compatible with this narrower protocol.',
                  'One scenario family and a single STAY example cannot support a defensible two-class train/validation split.']}
    report['files_sha256'] = {name:sha(out/name) for name in ['labelled_all.csv','training.csv','supplemental.csv','training_X.csv','training_y.csv','protocol.json']}
    dump(out/'dataset_report.json', report)
    readme = (
        '# Exploratory packet-performance training dataset\n\n'
        'Labels describe the measured one-second paired reception-gap/throughput preference. '
        'They do not describe connectivity failure or an optimal handover policy. '
        'The objective was selected after observing the pilot results.\n\n'
        'training.csv contains audited primary rows with verified archived simulator source. '
        'labelled_all.csv also includes supplemental outcomes whose source was not archived. '
        'Unknown service failures remain blank. Never replace them with zero.\n\n'
        'training_X.csv has exactly the seven model inputs. training_y.csv has aligned decision IDs, '
        'targets (0=STAY, 1=HANDOVER) and weights, in the same row order. '
        'No random split is provided. All related pilot rows belong to one conservative family; '
        'validation and test sets are unavailable. Do not report held-out accuracy.\n\n'
        'Rows with identical inputs can have opposing observed labels. No class balancing or '
        'fabrication was used. The report records counts, source hashes, limitations and audit links. '
        'This package does not train or validate an RF model. The existing validated trainer '
        'retains its stricter protocol and group requirements.\n')
    (out/'README.md').write_text(readme, encoding='utf-8')
    with zipfile.ZipFile(out/'training_dataset.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.name != 'training_dataset.zip':
                archive.write(path, path.relative_to(out).as_posix())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='Audited ns-3 pilot ZIP archives')
    parser.add_argument('--protocol', default='configs/packet_label_protocol.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        report = build(args.inputs, args.output, args.protocol)
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({k:report[k] for k in ['label_scope','primary_training','supplemental','splits','unknown_service_failure_values','model_trained']}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
