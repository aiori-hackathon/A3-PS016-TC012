# Offline labels and Random Forest training

This extends Debayan's Python workstream only. It does not change or run ns-3,
generate real alternative-action outcomes, or establish a network improvement.
The four supplied A3 runs remain validation/integration data. Their observed
handover success does not provide a label for the unobserved alternative action.

## Environment and a working synthetic example

Python 3.10+. The baseline processing CLI and label preparation need only the
standard library. RF fitting and classification evaluation need scikit-learn.

PowerShell, from the project root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[ml]"
.venv/Scripts/python.exe scripts/make_ml_demo.py
.venv/Scripts/python.exe -m aiori_pipeline.ml label --decisions examples/ml_synthetic/decisions.csv --outcomes examples/ml_synthetic/action_outcomes.csv --protocol configs/ml_protocol.json --output output/ml-demo/labels
.venv/Scripts/python.exe -m aiori_pipeline.ml train output/ml-demo/labels --allow-synthetic --output output/ml-demo/model
.venv/Scripts/python.exe -m aiori_pipeline.ml evaluate output/ml-demo/labels --model output/ml-demo/model/model.json --allow-synthetic --output output/ml-demo/test
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Linux: substitute .venv/bin/python for .venv/Scripts/python.exe.
requirements-ml-lock.txt records the verified Python 3.14 / Windows environment;
use it to reproduce that environment. For other Python versions, install the
optional ml dependencies from pyproject.toml and rerun the tests.
Outputs refuse to overwrite a populated directory; choose a new output path for
another run. The synthetic generator writes only its two named fixture files.
Do not run it against a real input folder.

The example contains 72 FABRICATED decisions, 144 action outcomes, 12 groups and
three disjoint splits. It is a deterministic software check. Synthetic training
requires --allow-synthetic, and all models/reports retain the synthetic flag.
No numerical score from this example is experimental evidence.

## Decision definition (draft experiment protocol)

configs/ml_protocol.json is an editable, explicitly draft convention:

- Candidate: strongest available neighbour selected using the same rule offline
  and online. The existing feature builder breaks equal-RSRP ties by cell ID.
- At decision time t, handover means request the named candidate. Stay means
  suppress handover during the same 200 ms action interval.
- Both branches use the same documented follow-up controller after that interval.
- Evaluate outcomes in [t,t+1 s). Use the declared 1 s ping-pong definition.
- Feature timestamps must be <=t and at most 200 ms old. All values must come
  from the shared pre-action history, including measurements at t before action.

These durations and priorities are proposals, not organizer requirements or an
approved optimum. Settle the convention with Joe, update the protocol ID whenever
semantics change, and set status to frozen before real-data RF fitting. The
label command can audit draft real data, but training rejects a draft protocol.
This status records experiment design; it is not a tool permission request.

Prefer matched replay with identical prefix/configuration/random streams before
t, then branch the action. A matching declared hash is a consistency check, not
proof that simulator state or random-stream behaviour really matched. Keep raw
traces and audit those claims. A new decision requires two new action rollouts;
whole runs with arbitrary unrelated decision histories are not valid pairs.

## Inputs from the paired-action experiment

Keep the six existing CSVs, run configuration and logs for every rollout. Add
these two offline tables. They are deliberately separate from run.csv, whose
policy field currently accepts only a3/rf. Do not mislabel a forced action as RF.

### decisions.csv -- one row per pre-action decision

```csv
decision_id,group_id,split,scenario_id,config_id,seed,rng_run,imsi,serving_cell_id,candidate_cell_id,decision_time_s,feature_time_s,predecision_hash,synthetic,serving_rsrp_dbm,candidate_rsrp_dbm,rsrp_delta_db,delta_slope_db_per_s,trend_available,speed_mps,mobility_age_s
```

Reuse feature values from features.csv at the latest causally available snapshot;
copy its time_s into feature_time_s. Add the experiment metadata above.

- decision_id: globally unique for one UE/time/candidate comparison.
- group_id: underlying scenario/trajectory family, shared across related seeds,
  speeds, adjacent decisions and repeated histories. All rows in a group must
  belong to one split: train, validation or test. Do not use run ID as the group
  when separate runs repeat the same scenario. scenario_id is a descriptive name.
- config_id, seed, rng_run: resolved common environment and actual RNG controls.
- predecision_hash: lowercase SHA256 of the archived common pre-action evidence
  plus config, RNG settings, UE, source, candidate and decision time. Document the
  canonical serialization and hash the identical prefix in both action branches.
  It must not include any post-decision value or chosen action.
- synthetic: false for simulator data, true for fabricated fixtures.
- Features retain dBm, dB, seconds, metres/second units. A missing initial trend
  is a blank delta_slope_db_per_s with trend_available=0. Do not invent zero.

Use the exact same feature cadence, candidate selection and trend-history logic
in online inference. Missing initial trends are imputed from training data only.
Avoid stale trend history; the upstream builder currently uses the previous
valid same-source/candidate snapshot, whose time interval can vary.

### action_outcomes.csv -- exactly two rows per decision

```csv
decision_id,action,run_id,protocol_id,predecision_hash,window_start_s,window_end_s,status,service_failures,ping_pong_events,total_excess_gap_s,throughput_mbps
```

- action is stay or handover. run_id uniquely identifies that action rollout.
- protocol_id and predecision_hash must match the chosen protocol and decision.
- window_start_s=t and window_end_s=t+horizon_s in both branches.
- status is complete or censored. Only complete pairs receive actionable labels.
- service_failures counts the same documented connectivity-loss/RLF episodes in
  both branches. It is not simply the handover-failure count: staying can lose
  connectivity without attempting a handover. Joe must supply supporting events
  and the common episode definition. Avoid counting one episode twice.
- ping_pong_events counts returns using the declared window and prior context.
- total_excess_gap_s is a symmetric window-wide service-gap measure across the
  same flows, not the baseline pipeline's handover-associated mean. Proposed
  definition: for each flow, union the intervals [previous_rx+nominal_interval,
  next_rx] when positive, intersect them with [t,t+horizon), and sum durations
  over flows. Include the last pre-window reception and first post-window
  reception. If boundary context is missing, mark censored rather than inventing
  a gap. Multiple flows share an environment; their summed gap is a label cost,
  not elapsed wall-clock outage. Use identical traffic in both action branches.
- throughput_mbps is received payload bits / horizon / 1e6 over the same flows.

These outcome summaries must be derived from archived simulator evidence. The
label command validates the supplied summaries; it does not derive service-loss
events or verify alternative trajectories from aggregate numbers. The original
six-CSV baseline contract alone is insufficient for service_failures labels.

## Label rule and exclusions

Compare outcomes in this declared lexicographic order:

1. Fewer service failures wins.
2. If equal, fewer ping-pong events wins.
3. If equal, lower total gap wins only when the difference exceeds 5 ms.
4. Otherwise higher throughput wins only when the difference exceeds 0.01 Mbps.
5. Otherwise declare a tie.

Margins are configurable in the protocol. label=0 means stay, label=1 means
handover; label=-1 means tie/censored and is excluded from RF training. Raw
outcomes remain intact. This objective is a transparent design choice; it does
not assume every handover or every A3 action is beneficial.

Missing/duplicate actions, mismatched prefixes/windows/protocols, future or stale
features, inconsistent RSRP deltas and cross-split groups fail explicitly.
Exact seven-feature fingerprints (rounded to six decimals) also cannot cross
splits. This catches our repeated input problem, but does not prove independence
of near-duplicates. Audit scenario families as well. No split is randomly assigned
by this pipeline: freeze a defensible group-level split manifest before training.

## Training and inference outputs

label writes labelled.csv, protocol.json and a manifest with source/dataset hashes,
class counts and excluded reasons. Source CSVs are read-only. Training verifies
hashes, uses only train rows to fit imputation and RF, and reports validation
classification separately. Each split needs both classes and at least two groups;
these are software minimums, not evidence that sample size is adequate.

RF settings: 128 trees, max depth 8, minimum leaf size 2, balanced_subsample class
weights, fixed RNG 42 and one worker. Fit rows have inverse-group-size weights,
giving each scenario group equal total input weight. The handover probability
threshold defaults to 0.6 and is explicitly configurable. Tune only on validation;
do not describe RF vote fractions as calibrated probabilities without validation.

Outputs:

- model.json: plain JSON tree structure, feature order, training-only medians,
  threshold, protocol, versions and development fingerprints. No pickle loading.
- training_report.json: train/validation class support, confusion matrices,
  balanced accuracy, precision/recall/F1, Brier score and mean group accuracy.
  Reserved test rows are not scored during training.
- golden_predictions.json: validation vectors and reference probabilities for
  checking Joe's future inference adapter. Every exported prediction is verified
  against scikit-learn before saving. Tree inputs use float32, matching sklearn.
- evaluate writes test_report.json separately and rejects previously seen
  development groups, states and exact feature vectors. Freeze the model and
  threshold before invoking it; do not iterate model choices on this test report.

Standard-library inference is available as:

```python
import json
from aiori_pipeline.ml import probability
model = json.load(open("output/ml-demo/model/model.json"))
# row contains the seven FEATURES keys; a missing initial trend may be blank.
p_handover = probability(model, row)
action = "handover" if p_handover >= model["threshold"] else "stay"
```

This is an offline inference interface, not a live ns-3 integration. Safety gates
for RRC state, target validity, cooldown and active handovers remain simulator
work. Use new held-out A3/RF live runs to assess all four network metrics.
Classifier accuracy alone cannot establish policy improvement.

## Next real-data checklist

1. Settle/freeze the protocol and common service-failure definition with Joe.
2. Obtain a small paired-action pilot, raw evidence and both summary tables.
3. Verify diversity, both actionable label classes and exclusion rates.
4. Assign entire scenario families to disjoint splits; reserve fresh final tests.
5. Fit one RF, check validation behaviour and freeze its exported model.
6. Verify adapter predictions against golden vectors, then run matched held-out
   A3/RF simulations. Keep the original four A3 validation runs out of final tests.

References: [scikit-learn RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
and [data-leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
The implemented label objective is project-specific.
