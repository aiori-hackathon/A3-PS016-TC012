# RF integration artifacts

[rf-prototype-v1/JOE_INTEGRATION.md](rf-prototype-v1/JOE_INTEGRATION.md) is the
handoff for the first real-data RF integration prototype. The folder preserves
the exact exported JSON model, standalone C++ evaluator, preprocessing contract,
golden inputs/outputs, protocol, training report and checksums.

This model is explicitly unvalidated. It was fitted on 16 paired observations
(15 HANDOVER labels and one STAY label), four unique inputs and one related
scenario family. Labels concern measured reception-gap/throughput preference;
unknown service failures remain outside this objective. No independent
validation/test score or improvement over A3 is established.

The generated C++ files are model-export artifacts, separate from Joe's ns-3
implementation. JSON inference matches scikit-learn on the exported reference
inputs. C++ compilation was unavailable locally: run the included standalone
parity checker before integrating it into the simulator.

The source simulator archives, raw traces, training CSVs and generated ZIPs remain
outside version control. Training and export commands are in
[docs/ML_PIPELINE.md](../docs/ML_PIPELINE.md).
