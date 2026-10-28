"""Synthetic tests for the explicit unvalidated integration export."""
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from aiori_pipeline.ml import DECISIONS, FEATURES, feature_fingerprint, sha
from aiori_pipeline.packet_labels import FIELDS
from aiori_pipeline.pipeline import ContractError, write_csv
from aiori_pipeline.prototype import predict, prepare, train_prototype, training_data


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root/'synthetic-data'
        self.data.mkdir()
        rows = []
        for group in range(4):
            for repeat in range(4):
                i = group*4+repeat
                d = {k:'' for k in FIELDS}
                d.update(decision_id=f'SYNTHETIC-{i}',group_id='SYNTHETIC-FAMILY',split='train',
                         scenario_id='SYNTHETIC',config_id='SYNTHETIC',seed=1,rng_run=repeat+11,imsi=1,
                         serving_cell_id=1,candidate_cell_id=2,decision_time_s=1.,feature_time_s=.9,
                         predecision_hash=f'{i:064x}',synthetic='true',serving_rsrp_dbm=-80,
                         candidate_rsrp_dbm=-79+group,rsrp_delta_db=1+group,delta_slope_db_per_s=2+group,
                         trend_available=1,speed_mps=30/3.6,mobility_age_s=.1,
                         source_batch='SYNTHETIC',source_pair_id=f'SYNTHETIC-{i}',
                         verified_source_sha256='1'*64,training_eligible='true',label=int(i!=0),
                         label_reason='total_excess_gap_s',label_protocol_id='observed-packet-preference-v1',
                         stay_total_excess_gap_s=.1,handover_total_excess_gap_s=.2,
                         stay_throughput_mbps=3.,handover_throughput_mbps=3.,sample_weight=.25)
                d['feature_fingerprint'] = feature_fingerprint(d)
                rows.append(d)
        write_csv(self.data/'training.csv',rows,FIELDS)
        (self.data/'protocol.json').write_text(Path('configs/packet_label_protocol.json').read_text())
        self.report = dict(schema_version=1,label_scope='observed_packet_performance_only',synthetic=True,
                           protocol_id='observed-packet-preference-v1',
                           primary_training={'rows':16,'class_counts':{'0':1,'1':15}},
                           limitations=['SYNTHETIC SOFTWARE CHECK ONLY'],files_sha256={})
        self.save_report()

    def save_report(self):
        self.report['files_sha256'] = {n:sha(self.data/n) for n in ['training.csv','protocol.json']}
        (self.data/'dataset_report.json').write_text(json.dumps(self.report))

    def rewrite(self,mutate):
        with (self.data/'training.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        mutate(rows)
        write_csv(self.data/'training.csv',rows,FIELDS)
        self.save_report()

    def test_fit_export_and_all_golden_vectors(self):
        out = self.root/'model'
        report = train_prototype(self.data,out,allow_synthetic=True)
        self.assertFalse(report['independent_validation_available'])
        self.assertIsNone(report['validation_metrics'])
        self.assertIsNone(report['test_metrics'])
        self.assertLess(report['json_sklearn_max_absolute_error'],1e-12)
        model = json.loads((out/'model.json').read_text())
        self.assertTrue(model['synthetic'])
        self.assertEqual(model['features'],FEATURES)
        self.assertEqual(model['threshold'],.6)
        self.assertEqual(len(model['trees']),128)
        self.assertEqual(model['model_status'],'integration_prototype_unvalidated')
        golden = json.loads((out/'golden_predictions.json').read_text())
        self.assertEqual(len(golden),6)
        for g in golden:
            p = predict(model,g['features'])
            self.assertEqual(p['valid'],g['valid'])
            self.assertEqual(p['prediction'],g['prediction'])
            if p['valid']:
                self.assertAlmostEqual(p['probability_handover'],g['probability_handover'],places=12)
        self.assertIn('static_cast<float>',(out/'rf_prototype.hpp').read_text())
        self.assertIn('kThreshold = 0.6',(out/'rf_prototype.hpp').read_text())
        self.assertIn('invalid-serving-fixture',(out/'rf_parity_check.cpp').read_text())
        with zipfile.ZipFile(out/'rf_prototype_v1.zip') as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('model.json'),(out/'model.json').read_bytes())
        for line in (out/'SHA256SUMS.txt').read_text().splitlines():
            checksum,name = line.split('  ',1)
            self.assertEqual(checksum,sha(out/name))

    def test_synthetic_requires_explicit_flag(self):
        with self.assertRaisesRegex(ContractError,'allow-synthetic'):
            training_data(self.data)

    def test_changed_dataset_rejected(self):
        path = self.data/'training.csv'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ContractError,'checksum changed'):
            training_data(self.data,True)

    def test_supplemental_row_cannot_be_fitted(self):
        self.rewrite(lambda rows:rows[0].update(training_eligible='false'))
        with self.assertRaisesRegex(ContractError,'eligible training'):
            training_data(self.data,True)

    def test_single_class_is_rejected(self):
        self.rewrite(lambda rows:[r.update(label='1') for r in rows])
        with self.assertRaisesRegex(ContractError,'both observed classes'):
            training_data(self.data,True)

    def test_weights_cannot_be_changed_silently(self):
        self.rewrite(lambda rows:rows[0].update(sample_weight='1'))
        with self.assertRaisesRegex(ContractError,'total weight one'):
            training_data(self.data,True)

    def test_no_validation_rows_are_allowed(self):
        self.rewrite(lambda rows:[r.update(split='validation') for r in rows])
        with self.assertRaisesRegex(ContractError,'eligible training'):
            training_data(self.data,True)

    def test_unavailable_trend_ignores_logger_zero(self):
        r = dict(zip(FEATURES,[-80,-79,1,0,0,8.,.1]))
        self.assertEqual(prepare(r,[0,0,0,4.,0,0,0])['delta_slope_db_per_s'],4.)
        r['delta_slope_db_per_s'] = None
        self.assertEqual(prepare(r,[0,0,0,4.,0,0,0])['delta_slope_db_per_s'],4.)

    def constant_model(self):
        return {'schema_version':1,'features':FEATURES,'medians':[0]*7,'threshold':.6,
                'trees':[dict(left=[-1],right=[-1],feature=[-2],threshold=[-2],probability_handover=[.6])]}

    def test_exact_threshold_requests_handover(self):
        r = dict(zip(FEATURES,[-80,-79,1,2,1,8.,.1]))
        self.assertEqual(predict(self.constant_model(),r)['prediction'],1)

    def test_invalid_inputs_do_not_become_stay_decisions(self):
        r = dict(zip(FEATURES,[-80,-79,1,2,1,8.,.1]))
        for key,value in [('serving_rsrp_dbm',None),('trend_available',.5),('speed_mps',0),
                          ('mobility_age_s',1),('rsrp_delta_db',4),('speed_mps',1e40),('delta_slope_db_per_s',None)]:
            bad = dict(r)
            bad[key] = value
            result = predict(self.constant_model(),bad)
            self.assertFalse(result['valid'],(key,value))
            self.assertIsNone(result['prediction'])


if __name__ == '__main__':
    unittest.main()
