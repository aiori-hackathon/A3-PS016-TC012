"""Read-only paired-pilot intake. Staging is separate from labelling/training."""
import argparse
import csv
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path, PurePosixPath

from .ml import DECISIONS, FEATURES, OUTCOMES, feature_fingerprint, fresh_output, integer, number, protocol, sha
from .pipeline import FLOATS, INTS, SCHEMAS, ContractError, flow_key, require, write_csv

DECISION_INPUT = ['pair_id', 'speed_kmh', 'rng_seed', 'rng_run', 'boundary',
                  'decision_time_s', 'imsi', 'serving_cell_id', 'candidate_cell_id', *FEATURES]
OUTCOME_INPUT = ['pair_id', 'action', 'speed_kmh', 'rng_seed', 'rng_run', 'boundary',
                 'decision_time_s', 'window_start_s', 'window_end_s', 'received_packets',
                 'received_payload_bytes', 'throughput_mbps', 'total_excess_gap_s',
                 'missing_sequence_count', 'handover_successes', 'handover_failures',
                 'ping_pong_events', 'service_failures', 'window_censored']
FEATURE_INPUT = ['decision_time_s', 'imsi', 'serving_cell_id', 'candidate_cell_id', *FEATURES, 'pilot_action']
RAW = ['radio.csv', 'mobility.csv', 'handovers.csv', 'packets.csv', 'traffic.csv']
ASSIGNMENTS = ['group_id', 'split', 'scenario_id', 'config_id']
CONFIG_FIELDS = ['speed_kmh', 'rng_seed', 'rng_run', 'boundary', 'decision_time_s']
LIMIT = 512 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def canonical(rows):
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, separators=(',', ':')))


class Source:
    """Read a ZIP in memory or a directory. Never extract or execute supplied files."""
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.archive = None
        self.hashes = {}
        try:
            if self.path.is_dir():
                paths = list(self.path.rglob('*'))
                require(not any(p.is_symlink() for p in paths), 'Input contains a symbolic link')
                require(all(p.resolve().is_relative_to(self.path) for p in paths), 'Input path escapes dataset directory')
                self.files = {p.relative_to(self.path).as_posix(): p for p in paths if p.is_file()}
                sizes = [p.stat().st_size for p in self.files.values()]
            else:
                self.archive = zipfile.ZipFile(self.path)
                entries = self.archive.infolist()
                names = [i.filename for i in entries]
                require(len(names) == len(set(names)), 'ZIP contains duplicate entries')
                for entry in entries:
                    name = PurePosixPath(entry.filename)
                    require(not name.is_absolute() and '..' not in name.parts and
                            '\\' not in entry.filename and ':' not in entry.filename,
                            'Unsafe ZIP member path')
                    require(not stat.S_ISLNK(entry.external_attr >> 16), 'ZIP contains a symbolic link')
                    require(not entry.flag_bits & 1, 'Encrypted ZIP members are unsupported')
                self.files = {i.filename: i for i in entries if not i.is_dir()}
                sizes = [i.file_size for i in self.files.values()]
            require(len(self.files) <= 10000 and sum(sizes) <= LIMIT, 'Input exceeds intake size limit')
            roots = [str(PurePosixPath(n).parent) for n in self.files if PurePosixPath(n).name == 'decisions.csv']
            require(len(roots) == 1, 'Expected exactly one decisions.csv dataset root')
            self.prefix = '' if roots[0] == '.' else roots[0] + '/'
            self.names = {n[len(self.prefix):] for n in self.files if n.startswith(self.prefix)}
            require('action_outcomes.csv' in self.names, 'Missing action_outcomes.csv')
        except Exception:
            self.close()
            raise

    def close(self):
        if self.archive:
            self.archive.close()

    def read(self, name):
        require(name in self.names, f'Missing file: {name}')
        key = self.prefix + name
        value = self.archive.read(key) if self.archive else self.files[key].read_bytes()
        checksum = hashlib.sha256(value).hexdigest()
        require(self.hashes.setdefault(name, checksum) == checksum, f'Input changed during intake: {name}')
        return value

    def json(self, name):
        value = json.loads(self.read(name).decode('utf-8-sig'))
        require(isinstance(value, dict), f'{name}: expected JSON object')
        return value

    def table(self, name, fields, optional=(), allow_empty=False):
        reader = csv.DictReader(io.StringIO(self.read(name).decode('utf-8-sig'), newline=''))
        headers = reader.fieldnames or []
        require(len(headers) == len(set(headers)) and set(fields) <= set(headers), f'{name}: missing/duplicate headers')
        rows = []
        for line, row in enumerate(reader, 2):
            require(None not in row and all(v is not None for v in row.values()), f'{name}:{line}: malformed row')
            row = {k: v.strip() for k, v in row.items()}
            require(all(row[k] != '' for k in fields if k not in optional), f'{name}:{line}: empty required field')
            rows.append(row)
        require(rows or allow_empty, f'{name}: no rows')
        return rows

    def raw(self, folder, name):
        rows = self.table(f'{folder}/{name}', SCHEMAS[name].split(','), ['failure_reason'], allow_empty=True)
        for row in rows:
            for key in SCHEMAS[name].split(','):
                if key in INTS:
                    row[key] = integer(row[key], key)
                elif key in FLOATS:
                    row[key] = number(row[key], key)
            if 'time_s' in row:
                require(row['time_s'] >= 0, f'{name}: negative timestamp')
        return sorted(rows, key=lambda r: r.get('time_s', 0))


def same_number(a, b, field, tolerance=1e-5):
    require(abs(number(a, field) - number(b, field)) <= tolerance, f'{field}: exported values disagree ({a}, {b})')


def check_raw(tables):
    flows = {}
    for r in tables['traffic.csv']:
        key = flow_key(r)
        require(key not in flows and r['direction'] in {'DL', 'UL'} and r['packet_interval_s'] > 0,
                'Invalid/duplicate traffic flow')
        flows[key] = r['packet_interval_s']
    require(bool(flows), 'traffic.csv: no intended flows')
    ues = {k[0] for k in flows}
    for name in RAW[:-1]:
        require(all(r['imsi'] in ues for r in tables[name]), f'{name}: unknown IMSI')
    for name, keys in [('packets.csv', ['imsi', 'flow_id', 'direction', 'sequence']),
                       ('radio.csv', ['time_s', 'imsi', 'measured_cell_id']),
                       ('mobility.csv', ['time_s', 'imsi'])]:
        ids = [tuple(r[k] for k in keys) for r in tables[name]]
        require(len(ids) == len(set(ids)), f'{name}: duplicate records')
    require(all(flow_key(r) in flows and r['payload_bytes'] > 0 for r in tables['packets.csv']), 'Invalid packet flow/payload')
    require(all(r['speed_mps'] >= 0 for r in tables['mobility.csv']), 'Negative mobility speed')
    for r in tables['radio.csv']:
        require(r['is_serving_cell'] in {'0', '1'} and
                (r['is_serving_cell'] == '1') == (r['serving_cell_id'] == r['measured_cell_id']),
                'Radio serving-cell identity mismatch')
    active, seen = {}, set()
    for r in tables['handovers.csv']:
        key = r['imsi'], r['attempt_id']
        require(r['source_cell_id'] != r['target_cell_id'], 'Invalid handover cells')
        if r['event'] == 'START':
            require(key not in seen and r['imsi'] not in active, 'Duplicate/overlapping handover')
            active[r['imsi']] = r
            seen.add(key)
        else:
            start = active.get(r['imsi'])
            require(r['event'] in {'SUCCESS', 'FAILURE'} and start is not None and
                    all(start[k] == r[k] for k in ['attempt_id', 'source_cell_id', 'target_cell_id']),
                    'Unmatched/invalid handover terminal event')
            require(r['event'] != 'FAILURE' or r['failure_reason'], 'Missing handover failure reason')
            del active[r['imsi']]
    return flows


def check_features(d, tables, max_age):
    t, ue = number(d['decision_time_s'], 'decision_time_s', 0), integer(d['imsi'], 'imsi')
    source, target = integer(d['serving_cell_id'], 'serving_cell_id'), integer(d['candidate_cell_id'], 'candidate_cell_id')
    require(source != target, 'Candidate equals serving cell')
    require(integer(d['boundary'], 'boundary') == source, 'Boundary/serving cell mismatch')
    latest, histories = {}, {}
    for cell in {r['measured_cell_id'] for r in tables['radio.csv'] if r['imsi'] == ue}:
        history = [r for r in tables['radio.csv'] if r['imsi'] == ue and r['measured_cell_id'] == cell and r['time_s'] <= t]
        if history:
            latest[cell], histories[cell] = history[-1], history
    require(source in latest and target in latest, 'Missing causal radio measurements')
    require(all(0 <= t-latest[c]['time_s'] <= max_age+1e-9 for c in (source, target)), 'Stale radio features')
    require(latest[source]['serving_cell_id'] == source and latest[target]['serving_cell_id'] == source,
            'Feature source differs from latest exported serving cell')
    neighbours = [r for c, r in latest.items() if c != source and t-r['time_s'] <= max_age+1e-9]
    require(max(neighbours, key=lambda r: (r['rsrp_dbm'], -r['measured_cell_id']))['measured_cell_id'] == target,
            'Candidate is not the strongest fresh neighbour')
    same_number(d['serving_rsrp_dbm'], latest[source]['rsrp_dbm'], 'serving_rsrp_dbm')
    same_number(d['candidate_rsrp_dbm'], latest[target]['rsrp_dbm'], 'candidate_rsrp_dbm')
    same_number(d['rsrp_delta_db'], number(d['candidate_rsrp_dbm'], 'candidate RSRP')-number(d['serving_rsrp_dbm'], 'serving RSRP'), 'rsrp_delta_db')
    trend = integer(d['trend_available'], 'trend_available')
    require(trend in {0, 1}, 'Invalid trend_available')
    if trend:
        require(len(histories[source]) >= 2 and len(histories[target]) >= 2, 'Trend has no previous measurement')
        a, b = histories[source][-2:], histories[target][-2:]
        require(a[0]['time_s'] == b[0]['time_s'] and a[1]['time_s'] == b[1]['time_s'],
                'Asynchronous radio history: slope needs explicit measurement timestamps')
        dt = a[1]['time_s'] - a[0]['time_s']
        expected = ((b[1]['rsrp_dbm']-a[1]['rsrp_dbm'])-(b[0]['rsrp_dbm']-a[0]['rsrp_dbm']))/dt
        # Raw RSRP and times are rounded to six decimal places in the supplied CSVs.
        tolerance = 1e-6 + 4e-6/dt + abs(expected)*2e-6/dt
        same_number(d['delta_slope_db_per_s'], expected, 'delta_slope_db_per_s', tolerance)
    else:
        require(d['delta_slope_db_per_s'] == '' or number(d['delta_slope_db_per_s'], 'unavailable slope') == 0,
                'Unavailable trend must be blank or the logger zero placeholder')
    mobility = [r for r in tables['mobility.csv'] if r['imsi'] == ue and r['time_s'] <= t]
    require(bool(mobility), 'Missing causal mobility measurement')
    age = t - mobility[-1]['time_s']
    require(age <= 0.5+1e-9, 'Stale mobility feature')
    same_number(d['mobility_age_s'], age, 'mobility_age_s')
    same_number(d['speed_mps'], mobility[-1]['speed_mps'], 'speed_mps')
    require(number(d['speed_mps'], 'speed_mps') > 0, 'Stationary speed needs a revised ML contract')
    same_number(number(d['speed_mps'], 'speed_mps')*3.6, d['speed_kmh'], 'speed_kmh')
    return min(latest[c]['time_s'] for c in (source, target))


def measure(tables, flows, start, end, ping_window):
    selected = [r for r in tables['packets.csv'] if start <= r['time_s'] < end]
    result = {'received_packets': len(selected), 'received_payload_bytes': sum(r['payload_bytes'] for r in selected),
              'total_excess_gap_s': 0., 'missing_sequence_count': 0, 'window_censored': 0}
    result['throughput_mbps'] = result['received_payload_bytes'] * 8 / (end-start) / 1e6
    for key, interval in flows.items():
        packets = [r for r in tables['packets.csv'] if flow_key(r) == key]
        result['window_censored'] |= int(not any(r['time_s'] < start for r in packets) or not any(r['time_s'] >= end for r in packets))
        for a, b in zip(packets, packets[1:]):
            require(b['sequence'] > a['sequence'], 'Reordered packets: sequence diagnostic needs a different definition')
            result['total_excess_gap_s'] += max(0., min(b['time_s'], end)-max(a['time_s']+interval, start))
            if b['time_s'] > start and a['time_s'] < end:
                result['missing_sequence_count'] += b['sequence']-a['sequence']-1
    successes = [r for r in tables['handovers.csv'] if r['event'] == 'SUCCESS']
    result['handover_successes'] = sum(start <= r['time_s'] < end for r in successes)
    result['handover_failures'] = sum(r['event'] == 'FAILURE' and start <= r['time_s'] < end for r in tables['handovers.csv'])
    previous, ping = {}, 0
    for r in successes:
        a = previous.get(r['imsi'])
        if a and start <= r['time_s'] < end and r['source_cell_id'] == a['target_cell_id'] and r['target_cell_id'] == a['source_cell_id'] and r['time_s']-a['time_s'] <= ping_window:
            ping += 1
        previous[r['imsi']] = r
    result['ping_pong_events'] = ping
    return result


def check_action(log, events, action, d, hold):
    t = number(d['decision_time_s'], 'decision time')
    markers = re.findall(r'PILOT DECISION: (STAY|HANDOVER)\s+time=([0-9.eE+-]+)', log)
    require(len(markers) == 1 and markers[0][0] == action.upper(), 'Missing/duplicate simulation action marker')
    same_number(markers[0][1], t, 'action marker time', 1e-6)
    active = {}
    for event in events:
        if event['time_s'] >= t:
            break
        if event['event'] == 'START':
            active[event['imsi']] = event
        else:
            active.pop(event['imsi'], None)
    require(integer(d['imsi'], 'imsi') not in active, 'Pilot decision occurred during an unfinished handover')
    starts = [e for e in events if e['event'] == 'START' and t <= e['time_s'] < t+hold-1e-6]
    if action == 'stay':
        require(not starts, 'STAY triggered a handover during the hold interval')
    else:
        require(len(starts) == 1 and starts[0]['source_cell_id'] == integer(d['serving_cell_id'], 'source') and
                starts[0]['target_cell_id'] == integer(d['candidate_cell_id'], 'candidate'),
                'HANDOVER did not start the selected cell transition in the action interval')


def audit_pair(src, d, outcomes, p, source_sha256=None):
    pair = d['pair_id']
    require(re.fullmatch(r'[A-Za-z0-9_-]+', pair), 'Unsafe pair_id')
    start = number(d['decision_time_s'], 'decision_time_s', 0)
    branches, checks = {}, {}
    for action in ('stay', 'handover'):
        folder = f'{pair}_{action}'
        cfg = src.json(folder+'/run_config.json')
        require(cfg.get('action') == action, 'Configuration action mismatch')
        for k in CONFIG_FIELDS:
            same_number(cfg.get(k), d[k], k)
        for k in ('rng_seed', 'rng_run', 'boundary'):
            integer(cfg[k], k)
            integer(d[k], k)
        horizon = number(cfg.get('horizon_s'), 'horizon_s', 0)
        hold = number(cfg.get('action_hold_s'), 'action_hold_s', 0)
        require(0 < hold <= horizon, 'Invalid action hold/horizon')
        if p:
            same_number(horizon, p['horizon_s'], 'horizon_s')
            same_number(hold, p['action_hold_s'], 'action_hold_s')
            if cfg.get('protocol_id'):
                require(cfg['protocol_id'] == p['protocol_id'], 'Rollout protocol_id mismatch')
        features = src.table(folder+'/pilot_decision_features.csv', FEATURE_INPUT, ['delta_slope_db_per_s'])
        require(len(features) == 1 and features[0]['pilot_action'] == action, 'Invalid feature row/action')
        for k in FEATURE_INPUT[:-1]:
            if k == 'delta_slope_db_per_s' and not integer(d['trend_available'], 'trend_available'):
                continue
            same_number(features[0][k], d[k], k)
        log = src.read(folder+'/simulation.log').decode('utf-8-sig')
        require(f'PILOT DECISION: {action.upper()}' in log, 'Missing simulation action marker')
        tables = {name: src.raw(folder, name) for name in RAW}
        flows = check_raw(tables)
        check_action(log, tables['handovers.csv'], action, d, hold)
        require({key[0] for key in flows} == {integer(d['imsi'], 'imsi')}, 'Pilot currently requires one UE per rollout')
        feature_time = check_features(d, tables, p['max_feature_age_s'] if p else .2)
        o = outcomes[action]
        for k in CONFIG_FIELDS:
            same_number(o[k], d[k], k)
        same_number(o['window_start_s'], start, 'window_start_s')
        same_number(o['window_end_s'], start+horizon, 'window_end_s')
        metrics = measure(tables, flows, start, start+horizon, p['ping_pong_window_s'] if p else 1.)
        for k, v in metrics.items():
            if k in {'throughput_mbps', 'total_excess_gap_s'}:
                same_number(o[k], v, k, 2e-6)
            else:
                require(integer(o[k], k) == v, f'{k}: summary differs from raw CSVs')
        if o['service_failures'] != '':
            integer(o['service_failures'], 'service_failures')
        branches[action] = (cfg, features[0], tables, feature_time)
        checks[action] = dict(metrics, service_failures=o['service_failures'], feature_time_s=feature_time)
        unfinished = set()
        for event in tables['handovers.csv']:
            if event['time_s'] >= start+horizon:
                break
            key = event['imsi'], event['attempt_id']
            if event['event'] == 'START':
                unfinished.add(key)
            else:
                unfinished.discard(key)
        checks[action]['unfinished_handover_at_window_end'] = bool(unfinished)
    a, b = branches['stay'], branches['handover']
    common = {k:v for k,v in a[0].items() if k != 'action'}
    require(common == {k:v for k,v in b[0].items() if k != 'action'}, 'STAY/HANDOVER configurations differ')
    # Compare every exported feature, including extra future logger fields.
    require({k:v for k,v in a[1].items() if k != 'pilot_action'} == {k:v for k,v in b[1].items() if k != 'pilot_action'}, 'STAY/HANDOVER feature records differ')
    require(canonical(a[2]['traffic.csv']) == canonical(b[2]['traffic.csv']), 'STAY/HANDOVER traffic differs')
    evidence = {'serialization': 'pilot-evidence-v1', 'config': common,
                'features': {k:v for k,v in a[1].items() if k != 'pilot_action'}, 'traffic': canonical(a[2]['traffic.csv'])}
    evidence['source_sha256'] = source_sha256
    counts = {}
    for name in RAW[:-1]:
        prefix = canonical([r for r in a[2][name] if r['time_s'] < start])
        require(prefix == canonical([r for r in b[2][name] if r['time_s'] < start]), f'Pre-decision {name} differs')
        evidence[name], counts[name] = prefix, len(prefix)
    difference = checks['stay']['total_excess_gap_s']-checks['handover']['total_excess_gap_s']
    margin = p['gap_margin_s'] if p else .005
    preference = 'handover' if difference > margin+1e-12 else 'stay' if difference < -margin-1e-12 else 'tie'
    return {'pair_id':pair, 'predecision_hash':digest(evidence), 'predecision_counts':counts,
            'feature_time_s':min(a[3], b[3]), 'config':common, 'outcomes':checks,
            'diagnostic_gap_preference':preference, 'gap_reduction_s':difference,
            'same_time_radio_requires_ordering_evidence':a[3] == start}


def provenance(src):
    result = {'checksum_entries_verified': 0}
    if 'SHA256SUMS.txt' in src.names:
        seen = set()
        for line in src.read('SHA256SUMS.txt').decode('utf-8-sig').splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r'([a-f0-9]{64})\s+\*?(.+)', line)
            require(match is not None, 'Malformed SHA256SUMS entry')
            expected, name = match.groups()
            require(name not in seen, 'Duplicate SHA256SUMS entry')
            seen.add(name)
            require(hashlib.sha256(src.read(name)).hexdigest() == expected, f'Checksum mismatch: {name}')
        require(seen == src.names-{'SHA256SUMS.txt'}, 'SHA256SUMS does not cover the complete dataset')
        result['checksum_entries_verified'] = len(seen)
    if 'reproducibility_manifest.json' in src.names:
        manifest = src.json('reproducibility_manifest.json')
        result['declared_manifest'] = manifest
        if manifest.get('source_sha256'):
            matches = [n for n in sorted(src.names) if n.endswith('.cc') and hashlib.sha256(src.read(n)).hexdigest() == manifest['source_sha256']]
            require(len(matches) == 1, 'Manifest source_sha256 does not identify one archived C++ source')
            result['verified_source_file'] = matches[0]
            result['verified_source_sha256'] = manifest['source_sha256']
    return result


def split_checks(rows, pair_checks):
    seen = {k:{} for k in ['group_id', 'feature_fingerprint', 'lineage']}
    for row, pair in zip(rows, pair_checks):
        split = row['split']
        if not split:
            continue
        require(split in {'train', 'validation', 'test'}, 'Invalid assigned split')
        lineage = digest({k:v for k,v in pair['config'].items() if k not in {'decision_time_s', 'boundary', 'action'}})
        for key, value in [('group_id',row['group_id']), ('feature_fingerprint',feature_fingerprint(row)), ('lineage',lineage)]:
            if value:
                require(seen[key].setdefault(value, split) == split, f'Leakage: {key} crosses splits')


def import_pilot(input_path, output, expected_pairs=None, metadata_path=None, protocol_path=None):
    inputs = [input_path] + [v for v in (metadata_path, protocol_path) if v]
    out = fresh_output(output, inputs)
    report = {'schema_version':1, 'data_checks_passed':False, 'label_inputs_ready':False,
              'training_ready':False, 'errors':[], 'label_blockers':[], 'training_blockers':[], 'pairs':[]}
    src = None
    normalized, normalized_outcomes = [], []
    try:
        p = protocol(protocol_path) if protocol_path else None
        metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8-sig')) if metadata_path else {'schema_version':1, 'assignments':{}}
        require(isinstance(metadata, dict) and metadata.get('schema_version') == 1 and isinstance(metadata.get('assignments'), dict), 'Invalid metadata assignment manifest')
        synthetic = metadata.get('synthetic', False)
        require(type(synthetic) is bool, 'synthetic must be a JSON boolean')
        report['synthetic'] = synthetic
        src = Source(input_path)
        report['provenance'] = provenance(src)
        report['input'] = {'path':str(src.path), 'zip_sha256':sha(src.path) if src.archive else None}
        ds = src.table('decisions.csv', DECISION_INPUT, ['delta_slope_db_per_s'])
        os = src.table('action_outcomes.csv', OUTCOME_INPUT, ['service_failures'])
        ids = [d['pair_id'] for d in ds]
        require(len(ids) == len(set(ids)), 'Duplicate pair_id in decisions.csv')
        require(not set(metadata['assignments'])-set(ids), 'Metadata contains unknown pair IDs')
        if expected_pairs is not None:
            require(integer(expected_pairs, 'expected_pairs') == len(ds), f'Expected {expected_pairs} pairs, found {len(ds)}')
        groups = defaultdict(dict)
        for o in os:
            require(o['pair_id'] in ids and o['action'] in {'stay', 'handover'}, 'Orphan/invalid action outcome')
            require(o['action'] not in groups[o['pair_id']], 'Duplicate action outcome')
            groups[o['pair_id']][o['action']] = o
        folders = {n.split('/')[0] for n in src.names if '/' in n}
        require(folders == {f'{pair}_{action}' for pair in ids for action in ('stay', 'handover')}, 'Missing/orphan rollout folder')
        manifest = report['provenance'].get('declared_manifest', {})
        for k, actual in [('paired_decisions', len(ds)), ('rollouts', len(os))]:
            if k in manifest:
                require(integer(manifest[k], k) == actual, f'Manifest {k} mismatch')
        coverage = defaultdict(Counter)
        for d in ds:
            delta = number(d['rsrp_delta_db'], 'rsrp_delta_db')
            band = '0-1' if 0 <= delta < 1 else '1-3' if 1 <= delta <= 3 else 'other'
            key = tuple(number(d[k], k) for k in ('speed_kmh','rng_seed','rng_run','boundary'))
            coverage[key][band] += 1
        report['scenario_coverage'] = [dict(zip(['speed_kmh','rng_seed','rng_run','boundary'], key), bands=dict(bands)) for key,bands in sorted(coverage.items())]
        if all(k in manifest for k in ('speed_kmh','rng_seed','rng_runs','boundaries')):
            requested = set(product(manifest['speed_kmh'], [manifest['rng_seed']], manifest['rng_runs'], manifest['boundaries']))
            require(set(coverage) == requested, 'Manifest scenario matrix is incomplete or inconsistent')
            bands = manifest.get('requested_rsrp_advantage_bands_db', [])
            require(set(bands) <= {'0-1','1-3'}, 'Unsupported declared RSRP advantage band')
            require(all(set(bands) <= set(observed) for observed in coverage.values()), 'A requested RSRP band is missing from a scenario')
        for d in ds:
            try:
                require(set(groups[d['pair_id']]) == {'stay', 'handover'}, 'Missing paired action outcome')
                pair = audit_pair(src, d, groups[d['pair_id']], p, report['provenance'].get('verified_source_sha256'))
                assignment = metadata['assignments'].get(d['pair_id'], {})
                require(isinstance(assignment, dict) and set(assignment) <= set(ASSIGNMENTS), 'Invalid assignment fields')
                require(all(isinstance(v, str) for v in assignment.values()), 'Assignments must be text')
                assignment = {k:v.strip() for k,v in assignment.items()}
                row = {k:'' for k in DECISIONS}
                row.update({k:d[k] for k in FEATURES})
                if integer(row['trend_available'], 'trend_available') == 0:
                    row['delta_slope_db_per_s'] = ''
                row.update(assignment)
                row.update(decision_id='pilot-'+pair['predecision_hash'], seed=d['rng_seed'], rng_run=d['rng_run'],
                           imsi=d['imsi'], serving_cell_id=d['serving_cell_id'], candidate_cell_id=d['candidate_cell_id'],
                           decision_time_s=d['decision_time_s'], feature_time_s=pair['feature_time_s'],
                           predecision_hash=pair['predecision_hash'], synthetic=str(synthetic).lower())
                normalized.append(row)
                report['pairs'].append(pair)
                for action in ('stay', 'handover'):
                    original = groups[d['pair_id']][action]
                    normalized_outcomes.append({
                        'decision_id':row['decision_id'], 'action':action, 'run_id':row['decision_id']+'_'+action,
                        'protocol_id':pair['config'].get('protocol_id', ''), 'predecision_hash':pair['predecision_hash'],
                        'window_start_s':original['window_start_s'], 'window_end_s':original['window_end_s'],
                        'status':'censored' if pair['outcomes'][action]['window_censored'] or pair['outcomes'][action]['unfinished_handover_at_window_end'] else 'pending',
                        **{k:original[k] for k in ['service_failures', 'ping_pong_events', 'total_excess_gap_s', 'throughput_mbps']}})
            except (ContractError, KeyError, ValueError) as exc:
                report['errors'].append({'pair_id':d['pair_id'], 'message':str(exc)})
        require(len({r['decision_id'] for r in normalized}) == len(normalized), 'Duplicate pre-decision evidence across decision IDs')
        if not report['errors']:
            split_checks(normalized, report['pairs'])
            report['data_checks_passed'] = True
        blockers = report['label_blockers']
        if not p or p['status'] != 'frozen':
            blockers.append('Experimental protocol is missing or still draft.')
        if not p or not p.get('service_failure_definition'):
            blockers.append('An agreed service-failure definition is missing from the protocol.')
        if any(not r[k] for r in normalized for k in ASSIGNMENTS):
            blockers.append('Scenario/configuration/group IDs and whole-group split assignments are incomplete.')
        if any(not r['protocol_id'] for r in normalized_outcomes):
            blockers.append('Rollout configurations do not identify the agreed protocol_id.')
        if any(r['service_failures'] == '' for r in normalized_outcomes):
            blockers.append('Service-failure counts are unknown; blank values were preserved.')
        if any(r['status'] == 'censored' for r in normalized_outcomes):
            blockers.append('Some windows lack reception boundary context or end during an unfinished handover.')
        if any(pair['same_time_radio_requires_ordering_evidence'] for pair in report['pairs']):
            blockers.append('Radio samples at decision time need proof they were recorded before the action.')
        report['label_inputs_ready'] = report['data_checks_passed'] and not blockers
        if report['label_inputs_ready']:
            for r in normalized_outcomes:
                r['status'] = 'complete'
        fingerprints = defaultdict(list)
        for r, pair in zip(normalized, report['pairs']):
            fingerprints[feature_fingerprint(r)].append(pair['pair_id'])
        report['counts'] = {'decisions':len(ds), 'rollouts':len(os), 'validated_pairs':len(normalized),
                            'unique_feature_vectors':len(fingerprints), 'unknown_service_failure_rows':sum(r['service_failures']=='' for r in os)}
        report['duplicate_feature_groups'] = [v for v in fingerprints.values() if len(v)>1]
        report['diagnostic_gap_preferences'] = dict(Counter(pair['diagnostic_gap_preference'] for pair in report['pairs']))
        by_pair = {pair['pair_id']:pair for pair in report['pairs']}
        report['conflicting_gap_preference_groups'] = [v for v in fingerprints.values() if len({by_pair[i]['diagnostic_gap_preference'] for i in v}-{'tie'})>1]
        report['training_blockers'] = ['Intake does not assign labels or train. Run the existing label-stage checks after resolving label blockers.',
                                       'Training needs both actionable classes and at least two independent groups in each development split; intake does not establish scenario independence.']
        if len(report['diagnostic_gap_preferences']) < 2:
            report['training_blockers'].append('Current gap diagnostics show no two-action diversity.')
        if report['conflicting_gap_preference_groups']:
            report['training_blockers'].append('Identical model inputs have opposing gap preferences; more independent repeats/scenarios are needed.')
        report['provenance_warnings'] = []
        if not report['provenance'].get('verified_source_sha256'):
            report['provenance_warnings'].append('No archived source checksum could be verified.')
        if not manifest.get('followup_protocol') or manifest.get('followup_protocol') == 'pending final code-level audit':
            report['provenance_warnings'].append('Shared follow-up controller semantics still need review; matching CSVs alone cannot establish them.')
        if report['data_checks_passed']:
            write_csv(out/'decisions.csv', normalized, DECISIONS)
            write_csv(out/'action_outcomes.csv', normalized_outcomes, OUTCOMES)
            template = {'schema_version':1, 'synthetic':synthetic,
                        'assignments':{d['pair_id']:{k:metadata['assignments'].get(d['pair_id'], {}).get(k, '') for k in ASSIGNMENTS} for d in ds}}
            (out/'split_plan_template.json').write_text(json.dumps(template, indent=2)+'\n', encoding='utf-8')
        if p:
            (out/'protocol_snapshot.json').write_text(json.dumps(p, indent=2)+'\n', encoding='utf-8')
        report['file_sha256'] = dict(sorted(src.hashes.items()))
        report['sidecar_sha256'] = {str(Path(path)):sha(path) for path in (metadata_path, protocol_path) if path}
        report['output_sha256'] = {name:sha(out/name) for name in ['decisions.csv','action_outcomes.csv','split_plan_template.json','protocol_snapshot.json'] if (out/name).is_file()}
    except (ContractError, KeyError, ValueError, OSError, zipfile.BadZipFile) as exc:
        report['data_checks_passed'] = False
        report['label_inputs_ready'] = False
        report['errors'].append({'message':str(exc)})
    finally:
        if src:
            src.close()
    report['notes'] = [
        'Matching exported histories and their hash do not prove equality of internal simulator or RNG state.',
        'Feature time is the oldest of the latest serving/candidate radio samples; mobility age remains separate.',
        'Gap preferences are exploratory diagnostics, not training labels. Unknown service failures are never zero.',
        'Reception gaps are summed across flows, not elapsed radio outage. Sequence gaps intersecting the window are not confirmed end-to-end packet loss.',
        'Missing assignments stay blank; no random split or automatic protocol freeze is performed.']
    (out/'audit.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Pilot ZIP or extracted dataset directory')
    parser.add_argument('--output', required=True, help='New output directory outside the input')
    parser.add_argument('--expected-pairs', type=int)
    parser.add_argument('--metadata', help='Reviewed assignment manifest; missing fields remain blank')
    parser.add_argument('--protocol', help='Protocol to check; never changed or frozen by intake')
    args = parser.parse_args(argv)
    try:
        report = import_pilot(args.input, args.output, args.expected_pairs, args.metadata, args.protocol)
    except (ContractError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({k:report.get(k) for k in ['data_checks_passed','label_inputs_ready','training_ready','counts','diagnostic_gap_preferences','errors','label_blockers']}, indent=2))
    return 2 if not report['data_checks_passed'] else 0 if report['label_inputs_ready'] else 3


if __name__ == '__main__':
    sys.exit(main())
