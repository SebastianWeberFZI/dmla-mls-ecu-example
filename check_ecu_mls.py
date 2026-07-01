import json
import sys
import csv
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "ecu_mls_model.json"


def load_model():
    with MODEL_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def artifacts_for_scenario(model, scenario):
    catalog = model["artifact_catalog"]
    artifacts = {}
    for name in scenario["artifacts"]:
        if name not in catalog:
            raise KeyError(f"Scenario references unknown artifact {name}")
        artifacts[name] = catalog[name]
    return artifacts


def by_type(artifacts):
    result = {}
    for name, artifact in artifacts.items():
        result.setdefault(artifact["type"], []).append((name, artifact))
    return result


def first_of_type(index, artifact_type):
    values = index.get(artifact_type, [])
    return values[0] if values else None


def resolve_artifact_path(artifact, property_name="path"):
    value = artifact.get(property_name)
    if not value:
        return None
    return (ROOT / value).resolve()


def count_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate_input_completeness(simulator_name, simulator, artifact_index):
    errors = []
    for required_type in simulator["requires"]:
        if required_type not in artifact_index:
            errors.append(
                f"{simulator_name}: missing required artifact type {required_type}"
            )
    return errors


def validate_constraint(constraint, artifact_index):
    kind = constraint["kind"]

    if kind == "property_equals":
        entry = first_of_type(artifact_index, constraint["artifact_type"])
        if entry is None:
            return [f"constraint needs {constraint['artifact_type']}"]
        name, artifact = entry
        actual = artifact.get(constraint["property"])
        expected = constraint["value"]
        if actual != expected:
            return [
                f"{name}.{constraint['property']} is {actual!r}, expected {expected!r}"
            ]
        return []

    if kind == "contains_all":
        entry = first_of_type(artifact_index, constraint["artifact_type"])
        if entry is None:
            return [f"constraint needs {constraint['artifact_type']}"]
        name, artifact = entry
        actual_values = set(artifact.get(constraint["property"], []))
        missing = [value for value in constraint["values"] if value not in actual_values]
        if missing:
            return [
                f"{name}.{constraint['property']} misses {', '.join(missing)}"
            ]
        return []

    if kind == "same_property":
        left = first_of_type(artifact_index, constraint["left_type"])
        right = first_of_type(artifact_index, constraint["right_type"])
        missing = []
        if left is None:
            missing.append(constraint["left_type"])
        if right is None:
            missing.append(constraint["right_type"])
        if missing:
            return [f"constraint needs {', '.join(missing)}"]
        left_name, left_artifact = left
        right_name, right_artifact = right
        left_value = left_artifact.get(constraint["left_property"])
        right_value = right_artifact.get(constraint["right_property"])
        if left_value != right_value:
            return [
                f"{left_name}.{constraint['left_property']}={left_value!r} "
                f"does not match {right_name}.{constraint['right_property']}={right_value!r}"
            ]
        return []

    if kind == "covers_functions":
        architecture = first_of_type(artifact_index, constraint["architecture_type"])
        mapping = first_of_type(artifact_index, constraint["mapping_type"])
        missing = []
        if architecture is None:
            missing.append(constraint["architecture_type"])
        if mapping is None:
            missing.append(constraint["mapping_type"])
        if missing:
            return [f"constraint needs {', '.join(missing)}"]
        architecture_name, architecture_artifact = architecture
        mapping_name, mapping_artifact = mapping
        functions = set(architecture_artifact.get("functions", []))
        mapped = set(mapping_artifact.get("mapped_functions", []))
        uncovered = sorted(functions - mapped)
        if uncovered:
            return [
                f"{mapping_name} does not cover functions from {architecture_name}: "
                f"{', '.join(uncovered)}"
            ]
        return []

    return [f"unknown constraint kind {kind}"]


def validate_simulator_constraints(simulator_name, simulator, artifact_index):
    errors = []
    for constraint in simulator.get("constraints", []):
        for error in validate_constraint(constraint, artifact_index):
            errors.append(f"{simulator_name}: {error}")
    return errors


def can_run(simulator_name, model, artifact_index):
    simulator = model["simulators"][simulator_name]
    errors = []
    errors.extend(validate_input_completeness(simulator_name, simulator, artifact_index))
    errors.extend(validate_simulator_constraints(simulator_name, simulator, artifact_index))
    return errors


def find_mapping(model, from_simulator, to_simulator):
    for mapping in model["state_mappings"]:
        if (
            mapping["from_simulator"] == from_simulator
            and mapping["to_simulator"] == to_simulator
        ):
            return mapping
    return None


def can_switch_to(from_simulator, to_simulator, model, artifact_index):
    mapping = find_mapping(model, from_simulator, to_simulator)
    if mapping is None:
        return [f"no state mapping from {from_simulator} to {to_simulator}"]

    errors = []
    for required_type in mapping["requires"]:
        if required_type not in artifact_index:
            errors.append(
                f"switch {from_simulator}->{to_simulator}: "
                f"missing mapping artifact type {required_type}"
            )
    return errors


def run_local_firmware_emulator(scenario_name, simulator_name, simulator, artifact_index):
    firmware = first_of_type(artifact_index, "FirmwareBinary")
    platform = first_of_type(artifact_index, "PlatformDescription")
    sensor_trace = first_of_type(artifact_index, "SensorTrace")
    missing = []
    if firmware is None:
        missing.append("FirmwareBinary")
    if platform is None:
        missing.append("PlatformDescription")
    if sensor_trace is None:
        missing.append("SensorTrace")
    if missing:
        return [f"{simulator_name}: tool adapter needs {', '.join(missing)}"], []

    _, firmware_artifact = firmware
    _, platform_artifact = platform
    _, sensor_trace_artifact = sensor_trace
    firmware_path = resolve_artifact_path(firmware_artifact)
    platform_path = resolve_artifact_path(platform_artifact)
    sensor_trace_path = resolve_artifact_path(sensor_trace_artifact)
    path_errors = []
    for label, path in (
        ("firmware", firmware_path),
        ("platform", platform_path),
        ("sensor trace", sensor_trace_path),
    ):
        if path is None:
            path_errors.append(f"{label} artifact has no path")
        elif not path.exists():
            path_errors.append(f"{label} artifact path does not exist: {path}")
    if path_errors:
        return [f"{simulator_name}: {error}" for error in path_errors], []

    adapter = simulator["tool_adapter"]
    script = (ROOT / adapter["script"]).resolve()
    output_path = (ROOT / adapter["output"].format(scenario=scenario_name)).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(script),
        "--firmware",
        str(firmware_path),
        "--platform",
        str(platform_path),
        "--sensor-trace",
        str(sensor_trace_path),
        "--out",
        str(output_path),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        return [f"{simulator_name}: tool adapter failed: {detail}"], []
    if not output_path.exists():
        return [f"{simulator_name}: tool adapter produced no trace at {output_path}"], []

    errors = validate_execution_trace(
        simulator_name,
        simulator,
        artifact_index,
        sensor_trace_path,
        output_path,
    )
    evidence = [f"{simulator_name}: executed {script.name} -> {output_path.relative_to(ROOT)}"]
    return errors, evidence


def validate_execution_trace(
    simulator_name,
    simulator,
    artifact_index,
    sensor_trace_path,
    output_path,
):
    with output_path.open("r", encoding="utf-8") as handle:
        trace = json.load(handle)

    errors = []
    for check in simulator.get("execution_checks", []):
        kind = check["kind"]

        if kind == "trace_kind":
            actual = trace.get("kind")
            expected = check["value"]
            if actual != expected:
                errors.append(
                    f"{simulator_name}: trace kind is {actual!r}, expected {expected!r}"
                )
            continue

        if kind == "samples_match_sensor_trace":
            expected = count_csv_rows(sensor_trace_path)
            actual = trace.get("sample_count")
            if actual != expected:
                errors.append(
                    f"{simulator_name}: trace sample_count is {actual}, expected {expected}"
                )
            continue

        if kind == "events_cover_firmware_symbols":
            firmware = first_of_type(artifact_index, "FirmwareBinary")
            if firmware is None:
                errors.append(f"{simulator_name}: execution check needs FirmwareBinary")
                continue
            _, firmware_artifact = firmware
            expected_symbols = set(firmware_artifact.get("symbols", []))
            actual_symbols = {
                event.get("function") for event in trace.get("events", []) if event
            }
            missing = sorted(expected_symbols - actual_symbols)
            if missing:
                errors.append(
                    f"{simulator_name}: trace misses firmware events {', '.join(missing)}"
                )
            continue

        if kind == "max_reaction_time_at_most_deadline":
            firmware = first_of_type(artifact_index, "FirmwareBinary")
            if firmware is None:
                errors.append(f"{simulator_name}: execution check needs FirmwareBinary")
                continue
            _, firmware_artifact = firmware
            deadline = firmware_artifact.get("deadline_ms")
            actual = trace.get("max_reaction_time_ms")
            if deadline is None:
                errors.append(f"{simulator_name}: FirmwareBinary has no deadline_ms")
            elif actual is None:
                errors.append(f"{simulator_name}: trace has no max_reaction_time_ms")
            elif float(actual) > float(deadline):
                errors.append(
                    f"{simulator_name}: max reaction time {actual} ms exceeds "
                    f"deadline {deadline} ms"
                )
            continue

        errors.append(f"{simulator_name}: unknown execution check kind {kind}")

    return errors


def run_tool_adapter(scenario_name, simulator_name, simulator, artifact_index):
    adapter = simulator.get("tool_adapter")
    if not adapter:
        return [], []
    if adapter["kind"] == "local_firmware_emulator":
        return run_local_firmware_emulator(
            scenario_name, simulator_name, simulator, artifact_index
        )
    return [f"{simulator_name}: unknown tool adapter kind {adapter['kind']}"], []


def validate_scenario(name, model):
    scenario = model["scenarios"][name]
    artifacts = artifacts_for_scenario(model, scenario)
    artifact_index = by_type(artifacts)
    errors = []
    evidence = []

    for simulator_name in scenario["sequence"]:
        if simulator_name not in model["simulators"]:
            errors.append(f"unknown simulator {simulator_name}")
            continue
        errors.extend(can_run(simulator_name, model, artifact_index))

    for source, target in zip(scenario["sequence"], scenario["sequence"][1:]):
        errors.extend(can_switch_to(source, target, model, artifact_index))

    if errors:
        return errors, evidence

    for simulator_name in scenario["sequence"]:
        simulator = model["simulators"][simulator_name]
        adapter_errors, adapter_evidence = run_tool_adapter(
            name, simulator_name, simulator, artifact_index
        )
        errors.extend(adapter_errors)
        evidence.extend(adapter_evidence)

    return errors, evidence



def main(argv):
    model = load_model()
    names = argv[1:] or list(model["scenarios"].keys())
    unexpected = []

    for name in names:
        errors, evidence = validate_scenario(name, model)
        expected = model["scenarios"][name]["expect"]
        passed = not errors
        expected_pass = expected == "pass"
        verdict = "PASS" if passed else "FAIL"
        expectation = "as expected" if passed == expected_pass else "UNEXPECTED"
        print(f"{name}: {verdict} ({expectation})")
        for item in evidence:
            print(f"  - {item}")
        if errors:
            for error in errors:
                print(f"  - {error}")
        if passed != expected_pass:
            unexpected.append(name)

    if unexpected:
        print("Unexpected scenario results: " + ", ".join(unexpected))
        return 1
    print("All scenario expectations satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
