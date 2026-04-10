#!/usr/bin/env python3
"""Run full compile and ERC check."""

import json
import subprocess
from typing import List
from pydantic import TypeAdapter
from circuitweaver.compiler.layout.engine import AutoLayoutEngine
from circuitweaver.compiler.kicad_writer import KiCadWriter
from circuitweaver.types.circuit_json import CircuitElement, SourceComponent, SchematicComponent, SchematicBox, SchematicTrace, SchematicNetLabel
from pathlib import Path

# Load and parse
with open('tmp/debug_circuit.json') as f:
    raw = json.load(f)

adapter = TypeAdapter(List[CircuitElement])
elements = adapter.validate_python(raw)

# Layout
engine = AutoLayoutEngine()
result = engine.layout(elements)

print("=== Elements by sheet ===")
sheet_counts = {}
for e in result:
    sid = getattr(e, 'sheet_id', 'no_sheet_id')
    etype = getattr(e, 'type', type(e).__name__)
    key = (sid, etype)
    sheet_counts[key] = sheet_counts.get(key, 0) + 1

for (sid, etype), count in sorted(sheet_counts.items()):
    print(f"  {sid}: {etype} x{count}")

print("\n=== Root sheet elements ===")
root_elements = [e for e in result if not hasattr(e, 'sheet_id') or getattr(e, 'sheet_id', None) == 'root']
for e in root_elements:
    etype = getattr(e, 'type', type(e).__name__)
    eid = None
    if hasattr(e, 'schematic_component_id'): eid = e.schematic_component_id
    elif hasattr(e, 'schematic_box_id'): eid = e.schematic_box_id
    elif hasattr(e, 'schematic_trace_id'): eid = e.schematic_trace_id
    elif hasattr(e, 'schematic_net_label_id'): eid = e.schematic_net_label_id
    elif hasattr(e, 'source_component_id'): eid = e.source_component_id
    print(f"  {etype}: {eid}")

# Write to output
output_dir = Path("tmp/output2")
output_dir.mkdir(parents=True, exist_ok=True)

source_components = {e.source_component_id: e for e in result if isinstance(e, SourceComponent)}
writer = KiCadWriter()

for sheet_id in ['root', 'mcu_sub']:
    content = writer.write_schematic(result, sheet_id, source_components)
    filename = f"debug_project.kicad_sch" if sheet_id == 'root' else f"{sheet_id}.kicad_sch"
    (output_dir / filename).write_text(content)
    print(f"\nWrote {filename} ({len(content)} bytes)")

# Write project file
pro_content = writer.write_project("debug_project", ['root', 'mcu_sub'])
(output_dir / "debug_project.kicad_pro").write_text(pro_content)

print(f"\nWritten to {output_dir}")

# Run ERC
print("\n=== Running ERC ===")
erc_result = subprocess.run(
    ["kicad-cli", "sch", "erc", str(output_dir / "debug_project.kicad_sch"), "--exit-code-violations"],
    capture_output=True, text=True
)
print(erc_result.stdout)
if erc_result.stderr:
    print(erc_result.stderr)
print(f"Exit code: {erc_result.returncode}")
