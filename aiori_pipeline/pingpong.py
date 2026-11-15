
from collections import defaultdict


def detect_ping_pong(handovers, window_s=1.0):
    """Detect successful A->B->A reversals separately for each UE."""
    if window_s <= 0:
        raise ValueError("window_s must be positive")

    histories = defaultdict(list)

    for row in handovers:
        if row["event"] != "SUCCESS":
            continue

        histories[str(row["imsi"])].append({
            "time_s": float(row["time_s"]),
            "source": int(row["source_cell_id"]),
            "target": int(row["target_cell_id"]),
        })

    events = []

    for imsi, history in histories.items():
        history.sort(key=lambda item: item["time_s"])

        for first, second in zip(history, history[1:]):
            elapsed = second["time_s"] - first["time_s"]

            if (
                first["source"] == second["target"]
                and first["target"] == second["source"]
                and 0 <= elapsed <= window_s
            ):
                events.append({
                    "imsi": imsi,
                    "first_cell": first["source"],
                    "intermediate_cell": first["target"],
                    "return_cell": second["target"],
                    "first_handover_time_s": first["time_s"],
                    "return_handover_time_s": second["time_s"],
                    "elapsed_s": elapsed,
                })

    return sorted(events, key=lambda event: (event["return_handover_time_s"], event["imsi"]))
