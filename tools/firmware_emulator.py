import argparse
import csv
import json
from pathlib import Path


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sensor_trace(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [
            {
                "time_ms": float(row["time_ms"]),
                "lane_offset_m": float(row["lane_offset_m"]),
                "confidence": float(row["confidence"]),
            }
            for row in csv.DictReader(handle)
        ]


def append_event(events, sample_index, function, start_ms, duration_ms):
    end_ms = start_ms + duration_ms
    events.append(
        {
            "sample_index": sample_index,
            "function": function,
            "start_ms": round(start_ms, 3),
            "end_ms": round(end_ms, 3),
            "duration_ms": round(duration_ms, 3),
        }
    )
    return end_ms


def simulate(firmware, platform, sensor_trace):
    if firmware["isa"] != platform["isa"]:
        raise ValueError(
            f"firmware ISA {firmware['isa']} does not match platform ISA {platform['isa']}"
        )

    execution_ms = firmware["execution_ms"]
    events = []
    reaction_times_ms = []
    required_functions = [
        "camera_ingest",
        "lane_detection",
        "steering_command",
    ]

    for index, sample in enumerate(sensor_trace):
        cursor = sample["time_ms"]
        for function in required_functions:
            cursor = append_event(
                events,
                index,
                function,
                cursor,
                float(execution_ms[function]),
            )
        reaction_times_ms.append(round(cursor - sample["time_ms"], 3))

    max_reaction_time_ms = max(reaction_times_ms) if reaction_times_ms else 0.0
    return {
        "kind": "FirmwareTrace",
        "tool": "local_firmware_emulator",
        "firmware": firmware["name"],
        "platform": platform["name"],
        "firmware_isa": firmware["isa"],
        "platform_isa": platform["isa"],
        "time_unit": "ms",
        "sample_count": len(sensor_trace),
        "deadline_ms": firmware["deadline_ms"],
        "max_reaction_time_ms": round(max_reaction_time_ms, 3),
        "reaction_times_ms": reaction_times_ms,
        "events": events,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--sensor-trace", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    firmware = load_json(args.firmware)
    platform = load_json(args.platform)
    sensor_trace = load_sensor_trace(args.sensor_trace)
    result = simulate(firmware, platform, sensor_trace)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
