# STM32 Motor Inverter Example

A larger CircuitWeaver source example for a 3-phase MOSFET inverter controlled by an STM32G431.

## Circuit Scope

This is a schematic-generation stress example, not a production motor-drive reference design. It models:

- STM32G431 controller sheet with SWD, HSE crystal, decoupling, load capacitors, and unused GPIO no-connects.
- 3-phase inverter sheet with IR2101 gate drivers, six N-MOSFETs, bootstrap parts, gate resistors, shunt sensing, VBUS divider, motor connector, and supply/PWR_FLAG inputs.
- Explicit global nets for supplies and cross-sheet control/sense signals so the generated KiCad project is ERC-clean with the current CircuitWeaver writer.

## Files

- `circuit.json` - cleaned source-level Circuit JSON.
- `generated/` - KiCad schematics produced by CircuitWeaver.
- `generated/erc.rpt` - KiCad ERC report for the generated schematic.

## Usage

```bash
circuitweaver validate examples/motor_inverter_stm32/circuit.json
circuitweaver compile examples/motor_inverter_stm32/circuit.json -o examples/motor_inverter_stm32/generated -n motor_inverter_stm32
kicad-cli sch erc --output examples/motor_inverter_stm32/generated/erc.rpt examples/motor_inverter_stm32/generated/motor_inverter_stm32.kicad_sch
```

Current ERC result: 0 errors, 0 warnings.

## Cleanup Notes

The original tmp JSON was structurally valid, but not example-quality. The cleaned version fixes JSON/source issues:

- Added missing `pin_number` values derived from `Component-pin` source port IDs.
- Changed `source_component.name` values to reference designators and moved descriptions/values into `display_value`.
- Added power metadata, deterministic project global-net config, PWR_FLAG symbols, supply connector, HSE load capacitors, and footprints.
- Removed the reset RC network because the selected KiCad STM32G431CBUx symbol exposes pin 7 as `PG10`, not `NRST`.
- Marked unused MCU pins with `do_not_connect`.

Tool issues found while generating this example:

- CircuitWeaver did not materialize `SourcePort.do_not_connect` into KiCad no-connect markers; this pass adds that.
- Embedded KiCad symbols used generated `Sym_*` IDs, causing empty-library ERC warnings; this pass preserves original `Library:Symbol` IDs.
- Embedded nested unit symbols were incorrectly renamed with the library prefix, for example `Connector_Generic:Conn_01x02_1_1`; KiCad requires nested units to keep the plain symbol prefix.
- Inherited KiCad symbols need flattened pins/graphics for schematic connectivity, but inherited properties must not be duplicated in the embedded symbol copy.
- Component pin positions and routed edge endpoints must use the snapped schematic symbol origin, otherwise KiCad sees wires adjacent to pins instead of connected.
- Routed detours around component bounds must be snapped to the schematic grid to avoid off-grid wire endpoints.
- The built-in part search catalog advertised `Power:*` symbols, but the installed KiCad library is `power.kicad_sym`; this pass changes those catalog entries to `power:*`.
- Hierarchical sheet pins still produce KiCad ERC hierarchy mismatches for this project. The example avoids that current writer limitation by declaring cross-sheet control/sense nets as explicit globals.
