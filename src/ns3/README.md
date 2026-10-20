
# MOBI-HO Lab — ns-3 LTE Baseline

## Environment

- Ubuntu 24.04 LTS on WSL2
- ns-3.46.1
- C++ LTE simulation
- A3-RSRP automatic handover algorithm

## Current Implementation

The baseline simulation contains:

- Three LTE eNodeBs
- One moving UE
- Configurable UE mobility speed
- Automatic A3-RSRP handover decisions
- X2-based handover execution
- Handover event and failure trace callbacks

## Reproduction Instructions

Use a separate official ns-3.46.1 installation.

Copy `mobi-ho-a3.cc` into the ns-3 `scratch/`
directory.

From the ns-3 root directory:

```bash
./ns3 configure --enable-examples --enable-tests
./ns3 build -j 4
./ns3 run "scratch/mobi-ho-a3 --speedKmh=30"
./ns3 run "scratch/mobi-ho-a3 --speedKmh=120"
```

## Verified Initial Observations

Both speed configurations produced automatic handovers:

- Cell 1 to Cell 2
- Cell 2 to Cell 3

These observations come from initial single-run tests.

## Current Limitations

The baseline does not yet include:

- Structured RSRP and handover CSV exports
- Complete four-metric benchmarking
- Multi-seed experimental analysis
- Random Forest integration

These capabilities are under development.



