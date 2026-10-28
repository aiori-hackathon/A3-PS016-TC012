"""Synthetic software fixtures only; no fabricated experimental evidence."""
import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from aiori_pipeline.ml import label
from aiori_pipeline.pilot import DECISION_INPUT, FEATURE_INPUT, OUTCOME_INPUT, import_pilot, main
from aiori_pipeline.pipeline import SCHEMAS, ContractError, write_csv


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root/'raw'
        self.raw.mkdir()
        self.pair = 'SYNTHETIC_speed30_run11_b1_t0p5'
        self.make_pair(self.pair, 11)
        self.protocol = self.root/'protocol.json'
        self.protocol.write_text(Path('configs/ml_protocol.json').read_text())
        self.metadata = self.root/'metadata.json'
        self.metadata.write_text(json.dumps({'schema_version':1, 'synthetic':True, 'assignments':{}}))

    def make_pair(self, pair, rng_run):
        d = dict(zip(DECISION_INPUT, [pair,30,1,rng_run,1,.5,1,1,2,-80,-78.2,1.8,2,1,30/3.6,.1]))
        existing = self.read('decisions.csv') if (self.raw/'decisions.csv').exists() else []
        write_csv(self.raw/'decisions.csv', existing+[d], DECISION_INPUT)
        outcomes = self.read('action_outcomes.csv') if (self.raw/'action_outcomes.csv').exists() else []
        for action in ('stay', 'handover'):
            folder = self.raw/f'{pair}_{action}'
            folder.mkdir()
            cfg = dict(speed_kmh=30, rng_seed=1, rng_run=rng_run, boundary=1,
                       decision_time_s=.5, action=action, horizon_s=1., action_hold_s=.2)
            (folder/'run_config.json').write_text(json.dumps(cfg))
            (folder/'simulation.log').write_text('SYNTHETIC FIXTURE\nPILOT DECISION: '+action.upper()+' time=0.5')
            f = {k:d[k] for k in FEATURE_INPUT if k != 'pilot_action'}
            f['pilot_action'] = action
            write_csv(folder/'pilot_decision_features.csv', [f], FEATURE_INPUT)
            radio, mobility, packets = [], [], []
            for i in range(11):
                t = i/5
                mobility.append(dict(zip(SCHEMAS['mobility.csv'].split(','),[t,1,t*30/3.6,0,0,30/3.6])))
                for cell, rsrp in [(1,-80),(2,-79+2*t),(3,-100)]:
                    radio.append(dict(zip(SCHEMAS['radio.csv'].split(','),[t,1,1,cell,rsrp,-10,int(cell==1)])))
            for i in range(21):
                packets.append(dict(zip(SCHEMAS['packets.csv'].split(','),[i/10,1,'dl','DL',i,1000])))
            traffic = [dict(imsi=1, flow_id='dl', direction='DL', packet_interval_s=.1)]
            events = []
            if action == 'handover':
                events = [dict(zip(SCHEMAS['handovers.csv'].split(','),[t,1,'fixture',1,2,event,''])) for t,event in [(.505,'START'),(.508,'SUCCESS')]]
            for name, rows in [('radio.csv',radio),('mobility.csv',mobility),('packets.csv',packets),('traffic.csv',traffic),('handovers.csv',events)]:
                write_csv(folder/name, rows, SCHEMAS[name].split(','))
            o = dict(pair_id=pair, action=action, speed_kmh=30, rng_seed=1, rng_run=rng_run, boundary=1,
                     decision_time_s=.5, window_start_s=.5, window_end_s=1.5, received_packets=10,
                     received_payload_bytes=10000, throughput_mbps=.08, total_excess_gap_s=0,
                     missing_sequence_count=0, handover_successes=int(action=='handover'), handover_failures=0,
                     ping_pong_events=0, service_failures='', window_censored=0)
            outcomes.append(o)
        write_csv(self.raw/'action_outcomes.csv', outcomes, OUTCOME_INPUT)

    def read(self, name):
        with (self.raw/name).open(newline='') as f:
            return list(csv.DictReader(f))

    def change(self, name, mutate):
        rows = self.read(name)
        fields = list(rows[0])
        mutate(rows)
        write_csv(self.raw/name, rows, fields)

    def config_change(self, mutate):
        for action in ('stay','handover'):
            path = self.raw/f'{self.pair}_{action}'/'run_config.json'
            cfg = json.loads(path.read_text())
            mutate(cfg, action)
            path.write_text(json.dumps(cfg))

    def run_import(self, name='out', **kwargs):
        return import_pilot(self.raw, self.root/name, metadata_path=self.metadata,
                            protocol_path=self.protocol, **kwargs)

    def assert_invalid(self, report, text):
        self.assertFalse(report['data_checks_passed'])
        self.assertIn(text, json.dumps(report['errors']))
        self.assertFalse((self.root/'out'/'decisions.csv').exists())

    def test_import_preserves_unknowns_and_does_not_freeze(self):
        before = {p.relative_to(self.raw).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.raw.rglob('*') if p.is_file()}
        report = self.run_import(expected_pairs=1)
        self.assertTrue(report['data_checks_passed'])
        self.assertFalse(report['label_inputs_ready'])
        self.assertFalse(report['training_ready'])
        with (self.root/'out'/'action_outcomes.csv').open(newline='') as f:
            outcomes = list(csv.DictReader(f))
        self.assertTrue(all(o['service_failures']=='' and o['status']=='pending' for o in outcomes))
        with (self.root/'out'/'decisions.csv').open(newline='') as f:
            d = next(csv.DictReader(f))
        self.assertEqual(d['group_id'], '')
        self.assertEqual(d['split'], '')
        self.assertEqual(d['synthetic'], 'true')
        self.assertAlmostEqual(float(d['feature_time_s']), .4)
        self.assertEqual(json.loads(self.protocol.read_text())['status'], 'draft')
        after = {p.relative_to(self.raw).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.raw.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def zip_source(self, nested=True):
        path = self.root/'pilot.zip'
        with zipfile.ZipFile(path,'w') as z:
            for p in self.raw.rglob('*'):
                if p.is_file():
                    z.write(p, ('pilot/' if nested else '')+p.relative_to(self.raw).as_posix())
        return path

    def test_zip_and_directory_have_identical_evidence_hashes(self):
        a = self.run_import()
        b = import_pilot(self.zip_source(), self.root/'zip-out', metadata_path=self.metadata, protocol_path=self.protocol)
        self.assertTrue(b['data_checks_passed'])
        self.assertEqual(a['pairs'][0]['predecision_hash'], b['pairs'][0]['predecision_hash'])

    def test_flat_zip(self):
        report = import_pilot(self.zip_source(False), self.root/'out')
        self.assertTrue(report['data_checks_passed'])

    def test_missing_file(self):
        (self.raw/f'{self.pair}_stay'/'radio.csv').unlink()
        self.assert_invalid(self.run_import(), 'Missing file')

    def test_missing_action(self):
        self.change('action_outcomes.csv', lambda rows:rows.pop())
        self.assert_invalid(self.run_import(), 'Missing paired action')

    def test_duplicate_action(self):
        self.change('action_outcomes.csv', lambda rows:rows.append(dict(rows[0])))
        self.assert_invalid(self.run_import(), 'Duplicate action')

    def test_orphan_action(self):
        self.change('action_outcomes.csv', lambda rows:rows[0].update(pair_id='unknown'))
        self.assert_invalid(self.run_import(), 'Orphan')

    def test_duplicate_decision(self):
        self.change('decisions.csv', lambda rows:rows.append(dict(rows[0])))
        self.assert_invalid(self.run_import(), 'Duplicate pair_id')

    def test_expected_batch_size(self):
        self.assert_invalid(self.run_import(expected_pairs=16), 'Expected 16')

    def test_predecision_packet_mismatch(self):
        self.change(f'{self.pair}_stay/packets.csv', lambda rows:rows[0].update(payload_bytes='1001'))
        self.assert_invalid(self.run_import(), 'Pre-decision packets.csv')

    def test_postdecision_radio_difference_does_not_affect_prefix(self):
        a = self.run_import()
        self.change(f'{self.pair}_stay/radio.csv', lambda rows:rows[-1].update(rsrp_dbm='-99'))
        b = self.run_import('later')
        self.assertTrue(b['data_checks_passed'])
        self.assertEqual(a['pairs'][0]['predecision_hash'], b['pairs'][0]['predecision_hash'])

    def test_config_mismatch(self):
        self.config_change(lambda cfg, action:cfg.update(extra_controller_setting=action))
        self.assert_invalid(self.run_import(), 'configurations differ')

    def test_handover_marker_alone_is_not_a_real_action(self):
        path = self.raw/f'{self.pair}_handover'/'handovers.csv'
        write_csv(path, [], SCHEMAS['handovers.csv'].split(','))
        self.assert_invalid(self.run_import(), 'did not start')

    def test_stay_cannot_handover_during_hold(self):
        source = self.raw/f'{self.pair}_handover'/'handovers.csv'
        target = self.raw/f'{self.pair}_stay'/'handovers.csv'
        target.write_bytes(source.read_bytes())
        self.assert_invalid(self.run_import(), 'STAY triggered')

    def test_unfinished_handover_is_censored(self):
        self.change(f'{self.pair}_handover/handovers.csv', lambda rows:rows[1].update(time_s='1.8'))
        self.change('action_outcomes.csv', lambda rows:rows[1].update(handover_successes='0'))
        report = self.run_import()
        self.assertTrue(report['data_checks_passed'])
        with (self.root/'out'/'action_outcomes.csv').open(newline='') as f:
            outcomes = list(csv.DictReader(f))
        self.assertEqual(outcomes[1]['status'], 'censored')
        self.assertTrue(report['pairs'][0]['outcomes']['handover']['unfinished_handover_at_window_end'])

    def test_missing_action_timestamp(self):
        (self.raw/f'{self.pair}_stay'/'simulation.log').write_text('PILOT DECISION: STAY')
        self.assert_invalid(self.run_import(), 'action marker')

    def test_summary_throughput_mismatch(self):
        self.change('action_outcomes.csv', lambda rows:rows[0].update(throughput_mbps='9'))
        self.assert_invalid(self.run_import(), 'throughput_mbps')

    def test_unknown_is_not_accepted_as_nan(self):
        self.change('action_outcomes.csv', lambda rows:rows[0].update(service_failures='NaN'))
        self.assert_invalid(self.run_import(), 'service_failures')

    def test_negative_service_failures(self):
        self.change('action_outcomes.csv', lambda rows:rows[0].update(service_failures='-1'))
        self.assert_invalid(self.run_import(), 'service_failures')

    def test_future_only_radio_cannot_supply_features(self):
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/radio.csv', lambda rows:rows.__setitem__(slice(None),[r for r in rows if float(r['time_s'])>.5]))
        self.assert_invalid(self.run_import(), 'Missing causal radio')

    def test_stale_radio(self):
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/radio.csv', lambda rows:rows.__setitem__(slice(None),[r for r in rows if float(r['time_s'])<.1 or float(r['time_s'])>.5]))
        self.assert_invalid(self.run_import(), 'Stale radio')

    def test_wrong_slope(self):
        self.change('decisions.csv', lambda rows:rows[0].update(delta_slope_db_per_s='20'))
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/pilot_decision_features.csv', lambda rows:rows[0].update(delta_slope_db_per_s='20'))
        self.assert_invalid(self.run_import(), 'delta_slope_db_per_s')

    def test_stronger_neighbour_not_silently_ignored(self):
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/radio.csv', lambda rows:[r.update(rsrp_dbm='-60') for r in rows if r['measured_cell_id']=='3'])
        self.assert_invalid(self.run_import(), 'strongest fresh neighbour')

    def test_zero_placeholder_becomes_missing_trend(self):
        self.change('decisions.csv', lambda rows:rows[0].update(trend_available='0', delta_slope_db_per_s='0'))
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/pilot_decision_features.csv', lambda rows:rows[0].update(trend_available='0', delta_slope_db_per_s='0'))
        report = self.run_import()
        self.assertTrue(report['data_checks_passed'])
        with (self.root/'out'/'decisions.csv').open(newline='') as f:
            self.assertEqual(next(csv.DictReader(f))['delta_slope_db_per_s'], '')

    def test_duplicate_feature_split_leakage(self):
        other = 'SYNTHETIC_speed30_run12_b1_t0p5'
        self.make_pair(other, 12)
        assignments = {self.pair:dict(group_id='a',split='train',scenario_id='s',config_id='c'),
                       other:dict(group_id='b',split='validation',scenario_id='s',config_id='c')}
        self.metadata.write_text(json.dumps({'schema_version':1,'synthetic':True,'assignments':assignments}))
        self.assert_invalid(self.run_import(), 'feature_fingerprint crosses splits')

    def test_duplicate_features_same_split_reported(self):
        self.make_pair('SYNTHETIC_speed30_run12_b1_t0p5',12)
        r = self.run_import()
        self.assertTrue(r['data_checks_passed'])
        self.assertEqual(r['counts']['unique_feature_vectors'],1)
        self.assertEqual(len(r['duplicate_feature_groups'][0]),2)

    def test_missing_reception_boundary_is_censored(self):
        for action in ('stay','handover'):
            self.change(f'{self.pair}_{action}/packets.csv', lambda rows:rows.__setitem__(slice(None),[r for r in rows if float(r['time_s'])<1.5]))
        self.change('action_outcomes.csv', lambda rows:[r.update(window_censored='1') for r in rows])
        r = self.run_import()
        self.assertTrue(r['data_checks_passed'])
        with (self.root/'out'/'action_outcomes.csv').open(newline='') as f:
            self.assertTrue(all(o['status']=='censored' for o in csv.DictReader(f)))

    def test_declared_zero_is_preserved_without_claiming_readiness(self):
        self.change('action_outcomes.csv', lambda rows:[r.update(service_failures='0') for r in rows])
        r = self.run_import()
        self.assertTrue(r['data_checks_passed'])
        self.assertFalse(r['label_inputs_ready'])
        self.assertEqual(r['counts']['unknown_service_failure_rows'],0)
        with (self.root/'out'/'action_outcomes.csv').open(newline='') as f:
            self.assertTrue(all(o['service_failures']=='0' for o in csv.DictReader(f)))

    def test_ready_synthetic_contract_can_enter_existing_label_stage(self):
        p = json.loads(self.protocol.read_text())
        p.update(status='frozen',service_failure_definition='SYNTHETIC_FIXTURE_ONLY')
        self.protocol.write_text(json.dumps(p))
        self.config_change(lambda cfg, action:cfg.update(protocol_id=p['protocol_id']))
        self.change('action_outcomes.csv', lambda rows:[r.update(service_failures='0') for r in rows])
        self.metadata.write_text(json.dumps({'schema_version':1,'synthetic':True,'assignments':{
            self.pair:dict(group_id='fixture', split='train', scenario_id='fixture', config_id='fixture')}}))
        r = self.run_import()
        self.assertTrue(r['label_inputs_ready'])
        self.assertFalse(r['training_ready'])
        rows = label(self.root/'out'/'decisions.csv', self.root/'out'/'action_outcomes.csv', self.protocol, self.root/'labels')
        self.assertEqual(rows[0]['label'], -1)  # A true tie is never a manufactured STAY label.

    def test_checksum_tampering(self):
        (self.raw/'SHA256SUMS.txt').write_text('0'*64+'  decisions.csv\n')
        self.assert_invalid(self.run_import(), 'Checksum mismatch')

    def test_no_overwrite(self):
        self.run_import()
        with self.assertRaisesRegex(ContractError, 'already populated'):
            self.run_import()

    def test_no_output_inside_raw(self):
        with self.assertRaisesRegex(ContractError, 'overlaps input'):
            import_pilot(self.raw, self.raw/'out')

    def test_unsafe_zip(self):
        path = self.zip_source()
        with zipfile.ZipFile(path,'a') as z:
            z.writestr('../outside.txt','no')
        self.assert_invalid(import_pilot(path,self.root/'out'), 'Unsafe ZIP')

    def test_duplicate_zip_member(self):
        path = self.zip_source()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path,'a') as z:
                z.writestr('pilot/decisions.csv','duplicate')
        self.assert_invalid(import_pilot(path,self.root/'out'), 'duplicate entries')

    def test_cli_pending_has_distinct_exit_code(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(self.raw),'--output',str(self.root/'out')])
        self.assertEqual(code,3)


if __name__ == '__main__':
    unittest.main()
