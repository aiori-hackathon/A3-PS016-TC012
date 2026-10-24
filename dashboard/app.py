
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path.home() / "MOBI-HO-Lab"
RESULTS = ROOT / "results"
OUTPUT = ROOT / "A3-PS016-TC012" / "output"

st.set_page_config(
    page_title="MOBI-HO Lab",
    page_icon="📡",
    layout="wide",
)

st.title("📡 MOBI-HO Lab")
st.caption(
    "Simulation-Based Cellular Handover "
    "Benchmarking for High-Mobility Users"
)

# Include only experiments with real processed metrics.
runs = sorted(
    p.parent.name
    for p in OUTPUT.glob("a3_linear_*/metrics.json")
)

if not runs:
    st.error("No processed ns-3 experiment results found.")
    st.stop()

selected = st.sidebar.selectbox(
    "Select simulation run",
    runs
)

metric_path = OUTPUT / selected / "metrics.json"
data_dir = RESULTS / selected

with metric_path.open() as f:
    metrics = json.load(f)

st.sidebar.markdown("### Experiment details")
st.sidebar.write("Policy:", metrics["policy"])
st.sidebar.write("Speed:", metrics["speed_kmh"], "km/h")
st.sidebar.write("RNG seed:", metrics["seed"])
st.sidebar.write("RNG run:", metrics["rng_run"])

st.subheader("Performance overview")

cols = st.columns(4)

cols[0].metric(
    "Throughput",
    f"{metrics['throughput_mbps']:.3f} Mbps"
)

attempts = metrics["handover_attempts"]
successes = metrics["handover_successes"]

success_rate = (
    100 * successes / attempts
    if attempts else None
)

cols[1].metric(
    "Handover success",
    f"{success_rate:.1f}%"
    if success_rate is not None else "N/A"
)

cols[2].metric(
    "Ping-pong events",
    metrics["ping_pong_events"]
)

gap = metrics.get("mean_excess_gap_s")

cols[3].metric(
    "Mean excess packet gap",
    f"{gap * 1000:.2f} ms"
    if gap is not None else "N/A"
)

st.info(
    "Packet-gap measurements are reception-gap proxies, "
    "not direct measurements of radio outage duration."
)

st.divider()

# UE mobility graph
mobility_path = data_dir / "mobility.csv"

if mobility_path.exists():
    mobility = pd.read_csv(mobility_path)

    st.subheader("UE movement")

    fig = px.line(
        mobility,
        x="time_s",
        y="x_m",
        color="imsi",
        title="UE position over simulation time",
        labels={
            "time_s": "Simulation time (s)",
            "x_m": "UE X position (m)",
        },
    )

    st.plotly_chart(fig, use_container_width=True)

# Handover events
handover_path = data_dir / "handovers.csv"

if handover_path.exists():
    handovers = pd.read_csv(handover_path)

    st.subheader("Handover timeline")

    if not handovers.empty:
        fig = px.scatter(
            handovers,
            x="time_s",
            y="target_cell_id",
            color="event",
            symbol="event",
            hover_data=[
                "source_cell_id",
                "attempt_id",
                "imsi",
            ],
            title="Handover events",
            labels={
                "time_s": "Simulation time (s)",
                "target_cell_id": "Target cell ID",
            },
        )

        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(handovers, use_container_width=True)
    else:
        st.write("No handover events recorded.")

st.divider()
st.subheader("A3 baseline comparison")

records = []

for run in runs:
    with (OUTPUT / run / "metrics.json").open() as f:
        m = json.load(f)

    records.append({
        "Run": run,
        "Speed (km/h)": m["speed_kmh"],
        "Throughput (Mbps)": m["throughput_mbps"],
        "Failures": m["handover_failures"],
        "Ping-pong": m["ping_pong_events"],
        "Excess gap (ms)": (
            m["mean_excess_gap_s"] * 1000
            if m.get("mean_excess_gap_s") is not None
            else None
        ),
    })

comparison = pd.DataFrame(records)

st.dataframe(comparison, use_container_width=True)

left, right = st.columns(2)

with left:
    fig = px.bar(
        comparison,
        x="Run",
        y="Throughput (Mbps)",
        color="Speed (km/h)",
        title="Throughput comparison",
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    fig = px.bar(
        comparison,
        x="Run",
        y="Excess gap (ms)",
        color="Speed (km/h)",
        title="Packet-gap comparison",
    )
    st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Data source: real ns-3 simulation exports processed "
    "through the AIORI evaluation pipeline. "
    "RF model results are not included yet."
)
