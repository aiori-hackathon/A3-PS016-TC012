# Importing Joe's paired-action pilots

This is Debayan's offline Python work. It reads simulator output without changing
or executing Joe's C++ code. It does not generate simulations, infer unknown
service failures, choose dataset splits, freeze a protocol, label data or fit RF.
Python 3.10+ and the standard library are sufficient.

## Run an intake

From the repository root, using PowerShell:

```powershell
.venv/Scripts/python.exe -m aiori_pipeline.pilot "C:/Users/Debayan/Downloads/low_margin_pilot_v2.zip" --expected-pairs 16 --protocol configs/ml_protocol.json --output output/pilot-intake/low-margin-v2
```

The original pilot uses the same command with paired_pilot_v1.zip and
--expected-pairs 8. Choose a new output path for every intake: populated
directories are never overwritten. Linux can use .venv/bin/python.
An extracted directory containing decisions.csv and action_outcomes.csv is also
accepted, including an enclosing folder with one dataset root. ZIPs are read
without extraction. Never place output inside an input directory.

Exit codes:

- 0: file checks pass and the structural inputs for the label stage are present.
  This does not mean a model can be trained or that the experiment is valid.
- 3: file checks pass, but label inputs are incomplete. This is the expected
  result for both exploratory pilots currently supplied by Joe.
- 2: invalid/inconsistent inputs, unsafe archive paths, or unusable output path.

## Files produced

- audit.json: errors, label blockers, coverage, duplicates, gap preferences,
  per-pair raw calculations, provenance and checksums.
- decisions.csv: our existing ML column names, with source values preserved,
  rng_seed mapped to seed and a deterministic decision_id/predecision_hash.
- action_outcomes.csv: our ML column names, preserving blank service_failures.
  Non-censored rows remain status=pending until all label prerequisites exist.
  Pending is deliberately rejected by the existing label command.
- split_plan_template.json: one assignment entry per original pair_id. Missing
  group/split/scenario/configuration assignments are blank, not guessed.
- protocol_snapshot.json: a copy of the supplied protocol, when provided.

The normalized CSVs and template are written only when all data checks pass.
Invalid inputs produce audit.json without a partially accepted dataset. Source
files are never overwritten. Raw archives and generated outputs stay in ignored
locations; no private simulator data is added to the repository.

## Automated checks

The importer accepts the layouts in paired_pilot_v1.zip and
low_margin_pilot_v2.zip. It requires:

- decisions.csv: one pair_id per decision, seven features, UE/source/candidate,
  speed, boundary, RNG controls and decision time.
- action_outcomes.csv: exactly one stay and one handover outcome per pair.
- Each <pair_id>_stay and <pair_id>_handover folder: radio.csv, mobility.csv,
  handovers.csv, packets.csv, traffic.csv, pilot_decision_features.csv,
  run_config.json and simulation.log. A run.csv is not required: these are forced
  action rollouts, not A3/RF policy comparisons.

Checks include:

- Missing/orphan folders, actions and rows; malformed CSVs, duplicate headers,
  non-finite values, invalid flow/UE identities, repeated packet IDs, overlapping
  handovers and unmatched terminal events.
- Both configurations agree except for action. Each configuration and feature
  record agrees with decisions.csv. Exported pre-decision histories agree across
  branches after canonical ordering; traffic definitions match in full.
- Exactly one timed action marker, no unfinished handover at decision time, no
  STAY handover during the hold interval, and one selected-cell HANDOVER start
  within the action interval. Marker/start evidence does not prove all internal
  controller state or random streams are equivalent.
- Candidate is the strongest fresh neighbour, using cell ID to break ties;
  serving/candidate RSRP, difference, same-cell measurement slope, speed and
  mobility age reconcile with causal raw measurements. Asynchronous slope
  history is rejected until explicit timestamps support its definition.
- Source radio samples must be at/before the decision and no older than the
  supplied protocol's max_feature_age_s (200 ms without a protocol). feature_time_s
  is conservatively the older serving/candidate sample time. Mobility age remains
  separate. Same-time radio samples block label readiness pending event-order
  evidence. No future backfill is performed.
- A logger's unavailable-trend zero placeholder is converted to a blank only
  when trend_available=0. Available slope zero is preserved as a real value.
- Raw packet/byte counts, throughput, summed excess reception gaps, sequence
  diagnostics, HO successes/failures, boundary censoring and ping-pong counts
  reconcile with the summaries. Ping-pong includes earlier context per our
  existing protocol; summaries that omit a boundary-spanning return will fail.
- A handover still unfinished at the end of the observation window separately
  censors the normalized outcome, even if packet receptions span the window.
- Declared archive checksums, archived source hash and scenario/band coverage
  are verified when a reproducibility manifest is present. A reported Git HEAD
  is a declaration, not proof that the archived source is that commit.

The source hash is checked without compiling or running the supplied source.
The current pilot schema supports one UE per rollout. A stationary-UE dataset
or reordered packet sequence diagnostics need explicit contract changes.

## What remains unknown

Service failures are imported as supplied. They cannot be reconstructed reliably
from HO failures or received-packet gaps. A supplied numeric count is checked for
validity, not independently verified against a standardized RLF event stream.
The common service-failure definition and supporting simulator instrumentation
still need agreement and review.

Summed reception gaps can exceed one second across several flows. They are a
label cost, not elapsed radio outage. The sequence diagnostic counts whole
sequence gaps between receptions whose interval intersects the window, including
gaps crossing its edges. It is not end-to-end packet loss or a transmitted-packet
loss rate. Neither diagnostic is silently renamed as an official outage/loss
metric.

Matching exported histories proves consistency of the supplied records. It does
not prove identical complete simulator/RNG state, shared follow-up behaviour or
fairness of the full experiment. Those require Joe's simulator/code audit.

### Read-only review of the second pilot controller

The archived source with SHA-256
5f3c6cb07feb19489b7f785463ef62a31692e9f04a4107512d58dfb97f5fae87
confirms the declared 200 ms action hold, normal 3 dB margin, 400 ms persistence
timer, 300 ms normal-measurement age limit and one-second cooldown measured from
the last handover request. The pilot HANDOVER bypasses the normal margin and
persistence requirement while still requiring a stronger eligible neighbour.
Automatic A3 is disabled in this separate implementation.

One detail needs explicit agreement before freezing: candidate timer state is
retained during the STAY hold and early returns for stale/missing measurements,
cooldown or an active handover. The timer therefore measures elapsed time from
its earlier qualifying observation; the code does not prove continuously fresh
qualification over that whole interval. Candidate change/insufficient margin and
a handover request reset it. An unfinished handover blocks new requests through
the active-handover state. Agree on retention/reset and failure recovery semantics
with Joe rather than silently describing a different shared controller.

This review does not change the simulator or freeze the protocol. No consistent
service-failure count can be inferred from these pilot exports.

## Assigning whole groups later

Copy the output split_plan_template.json to a separate reviewed sidecar. Fill in
group_id, split (train/validation/test), scenario_id and config_id per original
pair_id, then rerun intake into a new output directory with --metadata <file>.
The metadata has schema_version=1, a boolean synthetic flag and an assignments
object; synthetic is false by default for these simulator archives. Test fixtures
must declare synthetic=true. A config_id must identify the resolved experiment
configuration, not just the small per-rollout JSON.

All seeds, speeds, neighbouring decision times and repeated trajectories from
the same scenario family must remain together. The importer rejects supplied
splits that cross a declared group, exact seven-feature vector or the same
exported run lineage. These catches are minimum safeguards: configuration
changes, near-duplicates and related batches still require manual family review.
Maintain one consistent split plan across all imported batches; do not split each
archive independently. Missing assignments remain blank.

## Handoff to the existing label stage

label_inputs_ready requires passing data checks, full assignments, a frozen
supplied protocol with service_failure_definition, matching protocol_id in both
rollout configurations, known failure counts and uncensored observation windows.
It is a structural gate, not verification of the supplied scientific definitions.
The importer never adds a protocol ID to Joe's configurations or freezes a file.

Once these prerequisites are resolved, import again and use the existing label
command documented in ML_PIPELINE.md. It still applies the agreed outcome
priority, excludes ties/censored pairs and checks split leakage. RF training
separately requires both actionable classes and at least two groups in each
development split, with independent held-out scenarios. training_ready is always
false in intake reports because intake does not assess a labelled training set.

diagnostic_gap_preferences deliberately ignores unknown service failures and
other priority metrics. It must not be copied into label columns. Opposing gap
preferences for identical inputs can reflect stochastic outcomes or omitted
state; investigate them with independent repeats rather than adding RNG seed as
a predictor or forcing class balance.

Run the software tests with:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tests fabricate small, explicitly synthetic fixtures; experimental ZIPs are not
test dependencies and are never committed.
