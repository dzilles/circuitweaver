# Phase 1 Implementation Plan: Logic-Only Architecture

## Overview

**CLEAN SLATE** - Delete all schematic_* types and related code. The auto-layout tool (Phase 2) will add them back when needed.

Workflow after Phase 1:
1. **LLM generates logic** (`source_*` types only) → `logic.json`
2. **Auto-layout** (Phase 2) will generate KiCad files directly from logic

Phase 1 implements validation and tools for logic-only JSON.

---

## 1. Type Definitions (`types/circuit_json.py`)

### 1.1 Add `SourceGroup` Type

```python
class SourceGroup(BaseModel):
    type: Literal["source_group"]
    source_group_id: str
    name: Optional[str] = None
    subcircuit_id: Optional[str] = None
    parent_subcircuit_id: Optional[str] = None
    parent_source_group_id: Optional[str] = None
    is_subcircuit: Optional[bool] = None
```

### 1.2 Update `SourceTrace` to Match tscircuit Spec

**Current:**
```python
class SourceTrace(BaseModel):
    type: Literal["source_trace"]
    source_trace_id: str
    connected_source_port_ids: Optional[List[str]] = None
    connected_source_net_ids: Optional[List[str]] = None
```

**New:**
```python
class SourceTrace(BaseModel):
    type: Literal["source_trace"]
    source_trace_id: str
    connected_source_port_ids: List[str]  # REQUIRED (can be empty)
    connected_source_net_ids: List[str] = Field(default_factory=list)
    subcircuit_id: Optional[str] = None
    max_length: Optional[float] = None
    display_name: Optional[str] = None
```

### 1.3 Update `SourceNet` to Match tscircuit Spec

**Current:**
```python
class SourceNet(BaseModel):
    type: Literal["source_net"]
    source_net_id: str
    name: str
    member_source_port_ids: Optional[List[str]] = None
```

**New:**
```python
class SourceNet(BaseModel):
    type: Literal["source_net"]
    source_net_id: str
    name: str
    is_power: Optional[bool] = None
    is_ground: Optional[bool] = None
    is_digital_signal: Optional[bool] = None
    is_analog_signal: Optional[bool] = None
    trace_width: Optional[float] = None
    subcircuit_id: Optional[str] = None
    # Note: member_source_group_ids will be computed by auto-layout
```

### 1.4 Update `SourceComponent` for `ftype` Support

**Add to existing:**
```python
class SourceComponent(BaseModel):
    type: Literal["source_component"]
    source_component_id: str
    name: str
    ftype: Optional[str] = None  # NEW: "simple_resistor", "simple_capacitor", etc.

    # Existing fields
    value: Optional[str] = None
    footprint: Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    supplier_part_numbers: Optional[Dict[str, List[str]]] = None

    # NEW: Component-specific value fields
    resistance: Optional[float] = None      # For simple_resistor (Ohms)
    capacitance: Optional[float] = None     # For simple_capacitor (Farads)
    inductance: Optional[float] = None      # For simple_inductor (Henries)
    frequency: Optional[float] = None       # For simple_crystal (Hz)

    display_value: Optional[str] = None     # Human-readable value
    subcircuit_id: Optional[str] = None
    source_group_id: Optional[str] = None
```

### 1.5 Update `SourcePort` with Pin Attributes

**Add optional fields:**
```python
class SourcePort(BaseModel):
    type: Literal["source_port"]
    source_port_id: str
    source_component_id: str
    name: str
    pin_number: Optional[int] = None
    port_hints: Optional[List[str]] = None

    # NEW: Pin attributes
    is_power: Optional[bool] = None
    is_ground: Optional[bool] = None
    must_be_connected: Optional[bool] = None
    do_not_connect: Optional[bool] = None
    subcircuit_id: Optional[str] = None
```

### 1.6 Update `CircuitElement` Union

```python
# Source types (LLM generates these)
SourceElement = Union[
    SourceComponent,
    SourcePort,
    SourceNet,
    SourceTrace,
    SourceGroup,
]

# Schematic types (auto-layout generates these)
SchematicElement = Union[
    SchematicSheet,
    SchematicComponent,
    SchematicPort,
    SchematicTrace,
    SchematicBox,
    SchematicNetLabel,
    SchematicText,
    SchematicLine,
    SchematicError,
    SchematicNoConnect,
]

# Full circuit (after auto-layout)
CircuitElement = Union[SourceElement, SchematicElement]
```

---

## 2. Validator Changes (`validator/`)

### 2.1 New Validation Modes

Add to `validator/engine.py`:

```python
class ValidationMode(Enum):
    LOGIC_ONLY = "logic"      # Validate source_* elements only
    FULL = "full"             # Validate complete circuit.json
```

### 2.2 Rules Classification

| Rule | Logic Mode | Full Mode | Changes Needed |
|------|------------|-----------|----------------|
| `UniqueIdsRule` | ✓ | ✓ | None |
| `SourceFirstRule` | ✓ | ✓ | Update: only check source ordering |
| `IntegerCoordsRule` | - | ✓ | Skip in logic mode |
| `OrthogonalTracesRule` | - | ✓ | Skip in logic mode |
| `BoundsCheckRule` | - | ✓ | Skip in logic mode |
| `PinPositionsRule` | - | ✓ | Skip in logic mode |
| `UnconnectedPinsRule` | - | ✓ | Skip in logic mode |
| `UnplacedComponentsRule` | - | ✓ | Skip in logic mode |
| `HierarchyLinksRule` | ✓ | ✓ | Update for source_group |

### 2.3 New Logic-Only Rules

**Add `validator/rules/source_refs.py`:**

```python
class SourceReferencesRule(ValidationRule):
    """Validates that all source_* references are valid."""

    name = "source_references"

    def validate(self, elements: List[CircuitElement]) -> List[ValidationMessage]:
        # Check: source_port.source_component_id → valid source_component
        # Check: source_trace.connected_source_port_ids → valid source_ports
        # Check: source_trace.connected_source_net_ids → valid source_nets
        # Check: *.subcircuit_id → valid source_group.subcircuit_id
```

**Add `validator/rules/trace_connections.py`:**

```python
class TraceConnectionsRule(ValidationRule):
    """Validates source_trace connections are logically valid."""

    name = "trace_connections"

    def validate(self, elements: List[CircuitElement]) -> List[ValidationMessage]:
        # Check: Each trace connects at least 2 things (ports and/or nets)
        # Check: No duplicate port references in same trace
        # Warn: Port connected to multiple traces (might be intentional)
```

### 2.4 Update `validator/engine.py`

```python
def validate(
    elements: List[CircuitElement],
    mode: ValidationMode = ValidationMode.FULL
) -> ValidationResult:

    if mode == ValidationMode.LOGIC_ONLY:
        rules = [
            UniqueIdsRule(),
            SourceReferencesRule(),
            TraceConnectionsRule(),
            HierarchyLinksRule(),  # Updated for source_group
        ]
    else:
        rules = [
            # All existing rules
        ]

    # Run validation...
```

---

## 3. MCP Server Changes (`server/`)

### 3.1 Update `tool_registry.py`

**Add new tool:**

```python
@server.tool()
async def validate_logic_json(file_path: str) -> str:
    """Validate a logic-only JSON file (source_* elements only).

    Use this to validate your logic_draft.json before running auto-layout.
    This checks:
    - All IDs are unique
    - All references are valid (port→component, trace→port, etc.)
    - Trace connections are logically valid
    - Hierarchy structure is valid

    Does NOT check visual layout (coordinates, positions, etc.)
    """
    # Load file
    # Parse elements (only accept source_* types)
    # Run validation with mode=LOGIC_ONLY
    # Return result
```

**Add placeholder tool:**

```python
@server.tool()
async def run_auto_layout(input_file: str, output_file: str) -> str:
    """Generate schematic layout from logic JSON.

    NOTE: Auto-layout is not yet implemented. This tool will:
    - Read logic_draft.json (source_* elements)
    - Calculate component positions
    - Route wires between connected ports
    - Output circuit.json (source_* + schematic_* elements)

    For now, returns an error indicating manual layout is required.
    """
    return "Auto-layout not yet implemented. Please create schematic elements manually or wait for Phase 2."
```

**Update tool descriptions** to reflect new workflow.

### 3.2 Update Server Prompts

Update the system prompt in `mcp_server.py` to reference the new `circuit-json-spec.md`.

---

## 4. CLI Changes (`cli.py`)

### 4.1 Add `validate-logic` Command

```python
@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
def validate_logic(file_path: str):
    """Validate a logic-only JSON file (source_* elements only)."""
    # Similar to validate command but with mode=LOGIC_ONLY
```

### 4.2 Update Help Text

Update command descriptions to reflect new workflow.

---

## 5. Files to Modify

| File | Changes |
|------|---------|
| `types/circuit_json.py` | Add SourceGroup, update SourceTrace/Net/Component/Port, add type unions |
| `types/__init__.py` | Export new types |
| `validator/engine.py` | Add ValidationMode, update validate() signature |
| `validator/rules/__init__.py` | Register new rules |
| `validator/rules/source_refs.py` | NEW: Validate source references |
| `validator/rules/trace_connections.py` | NEW: Validate trace logic |
| `validator/rules/hierarchy_links.py` | Update for source_group |
| `validator/rules/source_first.py` | Update for logic-only mode |
| `server/tool_registry.py` | Add validate_logic_json, run_auto_layout placeholder |
| `server/mcp_server.py` | Update prompts |
| `cli.py` | Add validate-logic command |

---

## 6. Testing Plan

### 6.1 Unit Tests to Add

- `test_source_group_type.py` - SourceGroup validation
- `test_source_trace_new_format.py` - New trace format
- `test_logic_validation.py` - Logic-only validation mode
- `test_source_references.py` - Reference validation rule

### 6.2 Integration Tests

- Validate example logic_draft.json files
- Ensure old circuit.json files still work (backwards compatibility)

---

## 7. Migration Notes

### 7.1 Backwards Compatibility

- Keep all existing schematic_* types
- Old circuit.json files should still validate and compile
- New logic_draft.json files validated with `validate_logic_json`

### 7.2 Documentation Updates

- `docs/circuit-json-spec.md` - Already updated
- `README.md` - Update workflow description
- `examples/` - Add logic_draft.json examples

---

## 8. Implementation Order

1. **Types** - Update circuit_json.py (foundation for everything)
2. **New Rules** - Add source_refs.py, trace_connections.py
3. **Validator Engine** - Add ValidationMode support
4. **Update Existing Rules** - hierarchy_links.py, source_first.py
5. **MCP Tools** - Add validate_logic_json, run_auto_layout placeholder
6. **CLI** - Add validate-logic command
7. **Tests** - Add unit and integration tests
8. **Examples** - Add logic_draft.json examples

---

## 9. Out of Scope (Phase 2)

- Auto-layout algorithm implementation
- Schematic routing
- Component placement optimization
- Wire bundling/bus routing
