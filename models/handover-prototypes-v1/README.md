# XGBoost and Logistic Regression handover prototypes

Both classifiers use the same verified pilot dataset as `rf-prototype-packet-v1-d2a723f8b90e`. Sixteen matched decisions yielded four unique feature vectors in one related scenario family, with 15 HANDOVER labels and one STAY label. The single STAY shares its feature vector with HANDOVER examples. Each distinct vector contributes a total fit weight of one. Labels reflect measured packet reception gaps and throughput over one second. Service failures remain unknown. Both models predicted HANDOVER for every training row at the fixed 0.60 threshold. Their training-set accuracy was 93.75% and balanced accuracy was 50%. Independent validation remains pending.

## Run the demo

Open **Model evaluation** in the dashboard. Choose a recorded pilot input, or edit its measurements, and select **Compare predictions**. The browser evaluates both models from the exported bundle. An action of HANDOVER means the score meets the fixed demo threshold of 0.60. These scores are uncalibrated class scores.

## Simulator handoff

`handover_prototypes.hpp` requires C++17 and the standard library. `aiori_prototypes::Predict(std::array<double,7>{...})` returns XGBoost first and Logistic Regression second. Each result has `valid`, `score` and `action`. Actions are `0` for STAY, `1` for HANDOVER and `-1` for invalid inputs. Pass the ordered inputs below:

1. `serving_rsrp_dbm` in dBm
2. `candidate_rsrp_dbm` in dBm
3. `rsrp_delta_db` in dB, calculated as candidate minus serving
4. `delta_slope_db_per_s` in dB/s, or NaN when trend is unavailable
5. `trend_available` as 0 or 1
6. `speed_mps` as positive m/s
7. `mobility_age_s` in seconds, within the v1 interface range of 0 to 0.5

Unavailable slope uses the training median. Preserve the simulator's existing freshness, candidate, RRC, in-flight handover and cooldown gates before any request. Read `parity.json` for comparison against Python predictions and run the standalone checker before integration.

```bash
g++ -std=c++17 -O2 prototype_parity.cpp -o prototype_parity
./prototype_parity
```

`xgboost.json` is the native XGBoost model and can be loaded by XGBoost. `handover-prototypes.json` in the download contains both portable predictors, feature order, input examples, dataset SHA-256, hyperparameters and training metrics. The dashboard copy lives at `frontend/public/handover-prototypes.json`.

To reproduce, use the pilot intake described in `docs/ML_PIPELINE.md`. This build used `xgboost-cpu==3.4.1` and `scikit-learn==1.9.1`.

```bash
python -m aiori_pipeline.train_demo_models output/packet-training-v1 --output output/handover-prototypes-v1
```
