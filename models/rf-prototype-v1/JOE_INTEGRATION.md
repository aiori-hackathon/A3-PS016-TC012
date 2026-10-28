# RF prototype handoff for Joe

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
