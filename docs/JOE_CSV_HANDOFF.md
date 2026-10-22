# CSV handoff from Joe to Debayan

Status: proposed version-1 contract implemented by the offline Python pipeline.
This document requests exports; it does not modify or execute ns-3 code.

## Delivery unit

Deliver one folder per simulation run, containing all six CSVs below. Use UTF-8,
comma delimiters, decimal points and headers exactly as shown. Additional columns
are allowed. All times are simulation seconds. Missing measurements are omitted,
never encoded as zero or NaN. Cell IDs are actual LTE IDs, not node indices.

Use a stable IMSI across handovers. RNTI alone is insufficient. Export only the
primary component carrier for this version. Rows may arrive unsorted; the reader
sorts them. Do not repeat measurements or packet receptions.

For an initial handoff, send A3 runs at 30 and 120 km/h using at least two distinct
seed/run combinations at each speed. These are pipeline smoke checks, not enough
evidence for the final evaluation. Keep train, validation and test runs separate.

## 1. run.csv -- exactly one row

```csv
run_id,policy,split,scenario_id,config_id,pair_id,seed,rng_run,speed_kmh,ns3_version,radio_model,git_commit,observation_start_s,observation_end_s,synthetic
```

| Field | Meaning |
|---|---|
| run_id | Globally unique run name, e.g. a3_linear_30_s1_r11 |
| policy | a3 or rf |
| split | train, validation or test; assign by whole independent runs/scenarios |
| scenario_id | Scenario family, e.g. linear or boundary_stress |
| config_id | Shared configuration ID/hash covering topology, pathloss/fading, traffic, streams and all common settings; exclude policy and seed/run |
| pair_id | Same identifier for matched A3/RF runs; unique within scenario and speed |
| seed, rng_run | Actual ns-3 RNG seed and run, nonnegative integers |
| speed_kmh | Configured positive UE speed |
| ns3_version | Exact installed version, e.g. 3.46.1 |
| radio_model | Explicit implemented radio model, e.g. ns-3 LTE/EPC |
| git_commit | Simulator source revision; use the same revision for both policies |
| observation_start_s, observation_end_s | Shared traffic measurement window [start,end), excluding startup/drain if desired |
| synthetic | false for real ns-3 output; true only for fabricated fixtures |

Also archive the full simulator command, resolved radio/channel configuration,
traffic configuration and RNG stream assignment in a text/JSON sidecar. config_id
is a declaration, not independent proof that network conditions match.

## 2. traffic.csv -- one row per intended flow

```csv
imsi,flow_id,direction,packet_interval_s
```

- imsi: stable nonnegative integer UE identity.
- flow_id: stable application-flow string, consistent across matched runs.
- direction: DL or UL, relative to the UE.
- packet_interval_s: positive nominal application packet interval in seconds.

Version 1 assumes constant-period UDP traffic active throughout the observation
window. Include intended flows even if they receive no packets. Multiple bearers
must have separate flow IDs. Variable-rate traffic needs a revised interruption
definition before being processed with this contract.

## 3. radio.csv -- one row per measured cell per UE timestamp

```csv
time_s,imsi,serving_cell_id,measured_cell_id,rsrp_dbm,rsrq_db,is_serving_cell
```

- RSRP is dBm; RSRQ is dB, not watts, linear ratios or encoded report ranges.
- is_serving_cell is 1 or 0 and must agree with both cell ID fields.
- A snapshot must contain one serving row and at least one neighbour row at the
  same timestamp, all with the same serving_cell_id.
- Include all available neighbours. Do not synthesize missing measurements.
- Use decision-accessible measurements; document whether they are PHY samples
  or filtered RRC reports. Training and eventual online inference must match.

Partial snapshots are retained in raw data but excluded from features, with
reasons recorded in rejected_features.csv. No interpolation from the future.

## 4. mobility.csv -- periodic UE state

```csv
time_s,imsi,x_m,y_m,z_m,speed_mps
```

Positions are metres; speed is metres/second. Export from time zero and at least
every 200 ms. Features use the latest measurement at or before the radio time,
with a default maximum age of 500 ms. Stale/missing history is rejected.

## 5. handovers.csv -- one START and at most one terminal row per attempt

```csv
time_s,imsi,attempt_id,source_cell_id,target_cell_id,event,failure_reason
```

- attempt_id: unique within a UE/run; created at the start and reused at terminal.
- event: START, SUCCESS or FAILURE.
- source_cell_id and target_cell_id stay unchanged across that attempt's rows.
  A success callback's current cell is the target: retain the original source.
- failure_reason: nonempty for FAILURE, otherwise may be blank. Preserve the
  actual failure category rather than collapsing every trace to a generic event.
- Export one canonical event stream. Do not count UE and eNB callbacks twice.
- An unresolved START is permitted and reported as censored, never a success.
- Preserve events before the observation window for ping-pong context.
- CONNECTION_ESTABLISHED is not a handover; leave it out of this file.

Example:

```csv
time_s,imsi,attempt_id,source_cell_id,target_cell_id,event,failure_reason
10.000000,1,h0001,1,2,START,
10.050000,1,h0001,1,2,SUCCESS,
```

## 6. packets.csv -- application payload reception, not transmission

```csv
time_s,imsi,flow_id,direction,sequence,payload_bytes
```

- time_s: application receiver timestamp, seconds.
- sequence: unique nonnegative packet number within that UE/flow/direction.
- payload_bytes: positive received application payload size, excluding headers.
- DL reception is measured at UE; UL reception at remote host.
- Log per flow, without combining UL/DL or counting retransmissions as new data.
- Keep context before/after handovers; measurement uses the declared window.

An empty file with headers means no received packets, provided tracing was
enabled and verified. Missing packet tracing must not be disguised as zero delivery.

## Changes needed relative to current repository exports

| Current export | Required handoff |
|---|---|
| radio_measurements.csv | Add IMSI and serving cell ID, verify physical units and snapshot completeness; export radio.csv |
| mobility.csv | Existing position and speed fields largely match; retain stable IMSI and time-zero sample |
| handover_events.csv | Add attempt ID and persistent source/target mapping, preserve failure category, normalize event names |
| No application reception CSV | Add packets.csv using receiver-side timestamps and unique sequence numbers |
| No run/flow manifest | Supply run.csv and traffic.csv |

Do not infer stable identity from RNTI without a timestamped mapping. These are
export requirements for Joe to implement in his own workstream.

## Validate before delivery

From the project root:

```powershell
python -m aiori_pipeline validate data/raw/a3_linear_30_s1_r11
```

Deliver raw runs and sidecars, not just aggregate metrics. Debayan will process
them and report rejected snapshots, missing outcomes and censored packet gaps.
