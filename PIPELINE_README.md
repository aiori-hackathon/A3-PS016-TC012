# Debayan's offline data and evaluation pipeline

Python 3.10+; standard library only. No third-party installation is needed to run
from this project root. No ns-3 source has been added, edited or executed.

## Quick start (PowerShell or Linux shell)

```powershell
python scripts/make_demo.py
python -m aiori_pipeline validate examples/synthetic/a3
python -m aiori_pipeline process examples/synthetic/a3 --output output/demo/a3
python -m aiori_pipeline process examples/synthetic/rf --output output/demo/rf
python -m aiori_pipeline compare output/demo/a3/metrics.json output/demo/rf/metrics.json --output output/demo/comparison.csv
python -m unittest discover -s tests -v
```

All demo input is FABRICATED, marked synthetic=true. Identical A3/RF fixtures
exercise the pipeline; their zero differences do not measure policy performance.
The synthetic radio values are feature-processing fixtures, not a physically
consistent simulation. Regenerate fixtures with scripts/make_demo.py.

## Real data

Ask Joe for the six files and sidecars in docs/JOE_CSV_HANDOFF.md. Store one
run per data/raw/<run_id>/ folder (ignored by Git). Then:

```powershell
python -m aiori_pipeline validate data/raw/a3_linear_30_s1_r11
python -m aiori_pipeline process data/raw/a3_linear_30_s1_r11 --output output/a3_linear_30_s1_r11 --ping-pong-window-s 1 --max-mobility-age-s 0.5
```

Commands exit with code 2 on invalid input. Raw files are read-only. Output
directories are separate; rerunning a command replaces that directory's named
output files. Keep output paths outside the raw run folders.

## Outputs

| File | Contents |
|---|---|
| features.csv | Serving and strongest available neighbour RSRP, difference, previous same-pair difference slope, speed and mobility age; run/split provenance |
| rejected_features.csv | Incomplete radio snapshots and missing/stale past mobility |
| metrics.json | Run metadata, per-run metrics, observation counts and censoring |
| flow_metrics.csv | Received packet count and throughput per UE/flow/direction |
| interruptions.csv | Per attempt/flow packet gap, excess gap, observed/censored status and separate RRC duration |
| comparison.csv | Paired RF-minus-A3 differences by scenario/speed, means and bootstrap intervals |

Features use only measurements at or before their timestamps. No future backfill
is performed. Radio snapshots are exact-time groups; mobility is a backward
as-of join bounded by the configured age. RSRQ and position remain available in
raw files but are not used in version-1 features. First trend values are blank
with trend_available=0, never silently imputed. Trend uses the previous valid
snapshot for the same UE/source/candidate; its time interval may vary.

Features are unlabeled. Outcome labels and RF training are intentionally pending
the agreed offline action/outcome criterion and actual simulator data. Copying
A3 actions or assigning fabricated outcome labels is not implemented. Reserve
whole independent runs/scenarios; never randomly split adjacent feature rows.

The separate optional ML workflow is documented in docs/ML_PIPELINE.md. It prepares
labels from matched stay/handover outcomes, trains one RF, and exports portable
JSON inference. It includes synthetic software fixtures; it does not create real
labels or train on the four supplied A3 validation runs.

## Metric definitions and limits

- Window: application receptions in [observation_start_s, observation_end_s).
- Handover attempts: START in that window. SUCCESS/FAILURE is resolved only if
  terminal time <= observation_end_s. Later/missing outcomes are censored.
- Failure rate: failures / (successes + failures), blank if denominator is zero.
  Always inspect censored_attempts alongside this conditional rate.
- Ping-pong: consecutive successful handovers A->B then B->A for one UE within
  the declared window length (default 1 s), measured between success times.
  Count a return whose success occurs in the observation window, including prior
  context. Each return is counted once; A->B->A->B can count two returns.
- Throughput: received payload bits / declared window duration / 1e6. Aggregate
  throughput sums flows and directions; flow_metrics.csv preserves the breakdown.
  Different speed runs have different possible durations: normalize by the
  declared duration, and compare policies within each speed.
- Service-gap proxy: last reception strictly before START to first reception
  at/after START for each intended flow. excess_gap_s=max(0,gap-nominal interval).
  Both receptions must lie inside the window; otherwise the sample is censored.
  mean_excess_gap_s averages observed attempt/flow samples, including failures.
  It is a packet-gap proxy associated with handovers, not a causal measurement
  proving handover-induced outage. Multiple attempts may share one gap; do not
  sum these samples as total outage. Gaps that begin after START may be missed.
- rrc_duration_s is terminal minus START (successful or failed completion), kept
  separate from application service-gap duration.

## Paired evaluation

Pass explicit metrics.json paths to compare. Only test runs are accepted. Each
scenario/speed/pair_id must have exactly one A3 and one RF run, matching seed,
rng_run, config_id, radio model, simulator revision, observation window and metric
settings. Duplicate run IDs and repeated RNG seed/run pairs within a group fail.
The contract cannot independently prove independence or matching RNG streams;
audit Joe's sidecars. Never mix synthetic and simulation results.

For each metric, use only pairs with two defined values and report total/valid
pair counts. Missing samples are not zeros. Compare throughput by flow separately
if traffic composition differs. Start with ten independent held-out pairs per
speed; this is a planning target, not a statistical guarantee.

Intervals use 2,000 paired bootstrap resamples and fixed RNG seed 42, with
empirical 2.5/97.5 percentile bounds. Fewer than two valid pairs yields blank
intervals. Small-sample intervals are descriptive; all-zero failure results do
not establish that failure risk is zero. A negative RF-minus-A3 difference favours
RF for failures/ping-pong/gaps; positive favours RF for throughput. Report tradeoffs
and censoring, not a single automatic winner.

## Suggested ownership

Joe maintains simulator tracing and exports. Debayan owns aiori_pipeline/,
scripts/, tests/ and this documentation. Use separate commits/PRs for these files;
do not change src/ns3/ while developing this pipeline. The workspace initially
had no checked-out tracked files; existing repository source was left untouched.
