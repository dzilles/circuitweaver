# Simple LED Circuit

A basic LED indicator circuit demonstrating CircuitWeaver's Circuit JSON format.

## Circuit Description

This circuit drives a red LED from a 5V supply with a current-limiting resistor.

```
VCC (5V) ──── R1 (330Ω) ──── LED1 (Red) ──── GND
```

## Calculations

- LED forward voltage (Vf): 2V
- Desired LED current (If): 10mA
- Supply voltage (Vcc): 5V
- Resistor value: R = (Vcc - Vf) / If = (5V - 2V) / 10mA = 300Ω

Using 330Ω (nearest standard value) gives ~9mA LED current.

## Files

- `circuit.json` - The Circuit JSON source file (logic only)
- `README.md` - This file

## Usage

```bash
# Validate the circuit
circuitweaver validate circuit.json
```

## Circuit JSON Structure

This example demonstrates the **logic-only** format with `source_*` elements:

1. **source_component**: Define parts (R1, LED1) with values and footprints
2. **source_port**: Define pins on each component
3. **source_net**: Define named signals (VCC, GND)
4. **source_trace**: Connect ports together and to nets

The auto-layout tool (Phase 2) will generate the visual schematic from this logic.
