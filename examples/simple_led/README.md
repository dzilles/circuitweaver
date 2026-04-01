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

- `circuit.json` - The Circuit JSON source file
- `README.md` - This file

## Usage

```bash
# Validate the circuit
circuitweaver validate circuit.json

# Compile to KiCad schematic
circuitweaver compile circuit.json -o output/

# Run ERC (requires KiCad)
circuitweaver erc output/main.kicad_sch
```

## ASCII Art Schematic

```
┌──────────────────[LED Indicator]──────────────────┐
│  5V input, 10mA LED current                       │
│  R = (Vcc - Vf) / If                              │
├───────────────────────────────────────────────────┤
│                                                   │
│                      ┌───────────┐                │
│   VCC ───────────────┤ R1  330Ω ├─────┐          │
│                      └───────────┘     │          │
│                                        │          │
│                                    ┌───┴───┐      │
│                                    │ LED1  │      │
│                                    │  Red  ├──GND │
│                                    └───────┘      │
│                                                   │
└───────────────────────────────────────────────────┘
```

## Circuit JSON Structure

The circuit demonstrates:

1. **Source Components**: `source_component` for R1 and LED1
2. **Source Nets**: `source_net` for VCC and GND
3. **Schematic Box**: Visual grouping with title and description
4. **Schematic Components**: Placement at grid coordinates
5. **Schematic Ports**: Pin connection points
6. **Schematic Traces**: Orthogonal wiring between ports
7. **Net Labels**: Power rail connections
