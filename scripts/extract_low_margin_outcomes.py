
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path.home() / "MOBI-HO-Lab/results/low_margin_pilot_v2"
HORIZON = 1.0


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def calculate_outcome(decision, action):
    pair_id = decision["pair_id"]
    folder = ROOT / f"{pair_id}_{action}"

    start = float(decision["decision_time_s"])
    end = start + HORIZON

    packets = read_csv(folder / "packets.csv")
    traffic = read_csv(folder / "traffic.csv")
    handovers = read_csv(folder / "handovers.csv")

    # Group received packets by the actual traffic flow.
    by_flow = defaultdict(list)

    for packet in packets:
        key = (
            packet["imsi"],
            packet["flow_id"],
            packet["direction"],
        )
        by_flow[key].append(packet)

    window_packets = [
        packet for packet in packets
        if start <= float(packet["time_s"]) < end
    ]

    received_bytes = sum(
        int(packet["payload_bytes"])
        for packet in window_packets
    )

    throughput_mbps = (
        received_bytes * 8 / (HORIZON * 1_000_000)
    )

    total_excess_gap = 0.0
    missing_sequences = 0
    censored = False

    for flow in traffic:
        key = (
            flow["imsi"],
            flow["flow_id"],
            flow["direction"],
        )

        arrivals = sorted(
            by_flow.get(key, []),
            key=lambda p: float(p["time_s"]),
        )

        interval = float(flow["packet_interval_s"])

        if interval <= 0:
            raise ValueError(
                f"Invalid packet interval: {folder}, {key}"
            )

        # Check that reception records span both boundaries.
        times = [float(p["time_s"]) for p in arrivals]

        if not any(t < start for t in times):
            censored = True

        if not any(t >= end for t in times):
            censored = True

        for previous, current in zip(
            arrivals, arrivals[1:]
        ):
            t1 = float(previous["time_s"])
            t2 = float(current["time_s"])

            # Excess gap beyond the nominal packet interval.
            gap_start = t1 + interval

            overlap = max(
                0.0,
                min(t2, end) - max(gap_start, start),
            )

            total_excess_gap += overlap

            # Sequence diagnostic for gaps intersecting
            # the observation window.
            if t2 > start and t1 < end:
                seq_gap = (
                    int(current["sequence"])
                    - int(previous["sequence"])
                    - 1
                )

                missing_sequences += max(seq_gap, 0)

    window_handovers = [
        ho for ho in handovers
        if start <= float(ho["time_s"]) < end
    ]

    successes = [
        ho for ho in window_handovers
        if ho["event"] == "SUCCESS"
    ]

    failures = [
        ho for ho in window_handovers
        if ho["event"] == "FAILURE"
    ]

    # Count successful A -> B -> A reversals
    # wholly observed inside this window.
    ping_pong = 0

    for first, second in zip(
        successes, successes[1:]
    ):
        if (
            first["source_cell_id"]
            == second["target_cell_id"]
            and first["target_cell_id"]
            == second["source_cell_id"]
        ):
            ping_pong += 1

    # Do not confuse handover failures with
    # connectivity/service failures.
    service_failures = ""

    return {
        "pair_id": pair_id,
        "action": action,
        "speed_kmh": decision["speed_kmh"],
        "rng_seed": decision["rng_seed"],
        "rng_run": decision["rng_run"],
        "boundary": decision["boundary"],
        "decision_time_s": decision["decision_time_s"],
        "window_start_s": f"{start:.6f}",
        "window_end_s": f"{end:.6f}",
        "received_packets": len(window_packets),
        "received_payload_bytes": received_bytes,
        "throughput_mbps": f"{throughput_mbps:.6f}",
        "total_excess_gap_s": f"{total_excess_gap:.6f}",
        "missing_sequence_count": missing_sequences,
        "handover_successes": len(successes),
        "handover_failures": len(failures),
        "ping_pong_events": ping_pong,
        "service_failures": service_failures,
        "window_censored": int(censored),
    }


def main():
    decisions = read_csv(ROOT / "decisions.csv")

    if len(decisions) != 16:
        raise ValueError(
            f"Expected 16 decisions, got {len(decisions)}"
        )

    outcomes = []

    for decision in decisions:
        for action in ("stay", "handover"):
            result = calculate_outcome(
                decision, action
            )

            outcomes.append(result)

            print(
                result["pair_id"],
                action.upper(),
                "throughput=",
                result["throughput_mbps"],
                "gap=",
                result["total_excess_gap_s"],
                "censored=",
                result["window_censored"],
            )

    if len(outcomes) != 32:
        raise ValueError(
            f"Expected 32 outcomes, got {len(outcomes)}"
        )

    output = ROOT / "action_outcomes.csv"

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(outcomes[0].keys()),
        )
        writer.writeheader()
        writer.writerows(outcomes)

    print("\nSUCCESS: action_outcomes.csv created")
    print("Total outcome records:", len(outcomes))
    print("Output:", output)


if __name__ == "__main__":
    main()

