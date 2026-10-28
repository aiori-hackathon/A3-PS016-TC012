"""Checks for the deliberately limited packet-performance label objective."""
import copy
import json
import unittest

from aiori_pipeline.ml import DECISIONS, FEATURES
from aiori_pipeline.packet_labels import FAMILY, load_protocol, make_rows, packet_preference, summarize
from aiori_pipeline.pipeline import ContractError


class PacketLabelTests(unittest.TestCase):
    def setUp(self):
        self.p = load_protocol('configs/packet_label_protocol.json')
        self.stay = dict(window_censored=0, unfinished_handover_at_window_end=False,
                         total_excess_gap_s=.1, throughput_mbps=3., service_failures='')
        self.ho = dict(self.stay, total_excess_gap_s=.2, throughput_mbps=3.1)

    def test_gap_priority_beats_throughput(self):
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(0,'total_excess_gap_s'))

    def test_handover_gap_win(self):
        self.ho['total_excess_gap_s'] = .01
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(1,'total_excess_gap_s'))

    def test_throughput_only_breaks_gap_tolerance_tie(self):
        self.ho['total_excess_gap_s'] = .104
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(1,'throughput_mbps'))

    def test_exact_margin_is_not_an_actionable_difference(self):
        self.ho.update(total_excess_gap_s=.105,throughput_mbps=3.01)
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(-1,'tie'))

    def test_missing_service_failures_are_not_filled(self):
        before = copy.deepcopy((self.stay,self.ho))
        packet_preference(self.stay,self.ho,self.p)
        self.assertEqual((self.stay,self.ho),before)
        self.assertEqual(self.stay['service_failures'],'')

    def test_known_service_counts_do_not_silently_change_this_objective(self):
        # A different objective must never be advertised as connectivity-aware.
        self.stay['service_failures'] = 2
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(0,'total_excess_gap_s'))

    def test_censored_window_is_not_labelled_stay(self):
        self.stay['window_censored'] = 1
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(-1,'incomplete_observation'))

    def test_unfinished_handover_is_excluded(self):
        self.ho['unfinished_handover_at_window_end'] = True
        self.assertEqual(packet_preference(self.stay,self.ho,self.p),(-1,'incomplete_observation'))

    def fixture(self, verified=True):
        d = {k:'' for k in DECISIONS}
        d.update(predecision_hash='0'*64, decision_id='SYNTHETIC_DECISION', synthetic='true')
        d.update(dict(zip(FEATURES,[-80,-79,1,2,1,8.333333,.1])))
        a = {'data_checks_passed':True,'errors':[],
             'provenance':{'verified_source_sha256':'1'*64} if verified else {},
             'pairs':[{'predecision_hash':d['predecision_hash'],'pair_id':'SYNTHETIC_PAIR',
                       'config':{'horizon_s':1.,'action_hold_s':.2},
                       'outcomes':{'stay':self.stay,'handover':self.ho}}]}
        return [d],a

    def test_verified_primary_rows_have_no_random_split(self):
        ds,audit = self.fixture()
        rows = make_rows(ds,audit,'SYNTHETIC_BATCH',self.p)
        self.assertEqual(rows[0]['label'],0)
        self.assertEqual(rows[0]['training_eligible'],'true')
        self.assertEqual(rows[0]['group_id'],FAMILY)
        self.assertEqual(rows[0]['split'],'train')
        self.assertEqual(rows[0]['stay_service_failures'],'')
        self.assertEqual(rows[0]['handover_service_failures'],'')
        self.assertEqual(rows[0]['label_protocol_id'],'observed-packet-preference-v1')

    def test_source_unavailable_is_supplemental(self):
        ds,audit = self.fixture(False)
        rows = make_rows(ds,audit,'SYNTHETIC_BATCH',self.p)
        self.assertEqual(rows[0]['label'],0)
        self.assertEqual(rows[0]['training_eligible'],'false')

    def test_invalid_audit_cannot_generate_labels(self):
        ds,audit = self.fixture()
        audit['data_checks_passed'] = False
        with self.assertRaisesRegex(ContractError,'audit failed'):
            make_rows(ds,audit,'SYNTHETIC_BATCH',self.p)

    def test_incorrect_horizon_rejected(self):
        ds,audit = self.fixture()
        audit['pairs'][0]['config']['horizon_s'] = 2
        with self.assertRaisesRegex(ContractError,'window/hold'):
            make_rows(ds,audit,'SYNTHETIC_BATCH',self.p)

    def test_conflicting_features_remain_visible(self):
        ds,audit = self.fixture()
        a = make_rows(ds,audit,'SYNTHETIC_BATCH',self.p)[0]
        b = dict(a,label=1,source_pair_id='SYNTHETIC_SECOND')
        report = summarize([a,b])
        self.assertEqual(report['unique_feature_vectors'],1)
        self.assertEqual(report['class_counts'],{'0':1,'1':1})
        self.assertEqual(len(report['conflicting_feature_groups']),1)
        json.dumps(report,allow_nan=False)


if __name__ == '__main__':
    unittest.main()
