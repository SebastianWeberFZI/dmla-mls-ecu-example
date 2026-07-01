# DMLA / MLS ECU Example

Reference implementation for the ECU software architecture example (Section IV)
of the position paper:

> Sebastian Weber, Thomas Weber, Jörg Henß, Robert Heinrich.
> **"Going beyond structure — Can Dynamic Multi-Level Algebra Support
> Multi-Level Simulation?"**

This prototype implements the paper's example as a small DMLA-inspired
compatibility model for multi-level simulation (MLS) of an automotive ECU.

It does not implement DMLA itself. Instead, it mirrors the example concepts
from the paper and executes one concrete tool step through an adapter:

- model artifacts refine `ModelArtifact`
- simulators refine `Simulator`
- compatibility is represented by explicit requirements and constraints
- simulator switches require explicit state mappings
- validation operations reject incomplete or semantically incompatible setups
- the firmware-emulation step runs an external process and validates the
  generated trace as a new artifact

The goal is not to demonstrate faster simulation, but explicit and
automatable compatibility reasoning across a chain of architecture,
transaction-level, and firmware-level simulators, exactly as described in
the paper's Figure 1.

## Run

From this directory:

```bash
python3 check_ecu_mls.py
```

On Windows:

```powershell
.\run_checks.cmd
```

The script reads `ecu_mls_model.json`, checks all scenarios, and exits with code
0 only if every scenario result matches its expected verdict.

If PowerShell script execution is enabled, `.\run_checks.ps1` can be used as well.

Generated tool traces are written below `tool_runs/` (git-ignored).

## Implemented Operations

- `ValidateInputCompleteness`: all required artifact types must be present.
- `ValidateSimulatorConstraints`: simulator-specific constraints must hold.
- `CanSwitchTo`: a switch requires a state mapping and mapping artifacts.
- `ValidateScenario`: checks a full simulator sequence.
- `RunToolAdapter`: starts `tools/firmware_emulator.py` as a separate process.
- `ValidateExecutionTrace`: checks that the generated firmware trace matches
  the sensor trace, covers the firmware symbols, and satisfies the deadline.

## Tool Adapter

`FirmwareEmulator` is configured with a `local_firmware_emulator` adapter. The
adapter consumes:

- `artifacts/firmware/*.json`
- `artifacts/platforms/renode_cortex_r52_platform.json`
- `artifacts/traces/camera_sensor_trace.csv`

This is still a lightweight stand-in rather than Renode itself. The important
step is that the DMLA checker crosses the boundary into an executable tool
process and treats its output as an artifact. A later Renode adapter can keep
the same checker contract and replace only the adapter command.

## Scenarios

| Scenario | Description | Expected |
|---|---|---|
| `complete_chain` | Valid architecture → TLM → firmware-emulation chain. | pass |
| `missing_symbol_map` | Invalid switch from TLM to firmware emulation. | fail |
| `wrong_firmware_isa` | Invalid firmware/platform combination (RISC-V binary on an ARM platform). | fail |
| `missing_sensor_trace` | Invalid firmware-emulation input set. | fail |
| `firmware_deadline_violation` | Statically compatible inputs whose generated firmware trace violates the reaction-time deadline. | fail |

All five scenarios have been verified to produce their expected result.

## Correspondence to the paper

| Paper (Fig. 1 / Sec. IV) | This repository |
|---|---|
| Architecture Simulator, TLM Simulator, Firmware Emulator | `simulators` in `ecu_mls_model.json` |
| Input artefacts (Usage scenario, Component architecture, Deployment model, …) | `artifact_catalog` in `ecu_mls_model.json` |
| Validated contracts (`CanRun`, ISA/peripherals/time units compatible, …) | `constraints` per simulator |
| `CanSwitchTo` mappings (needs bus map / needs symbols) | `state_mappings` in `ecu_mls_model.json` |

## License

MIT — see [LICENSE](LICENSE).
