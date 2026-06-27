# KISS Connectivity Refactor Plan

This is a handoff plan for improving CircuitWeaver's KiCad schematic generation with a simple, testable, extensible connection model.

## Goal

Make CircuitWeaver logic-first and connection-correct:

1. User-authored Circuit JSON describes electrical intent with `source_*` elements.
2. Internal code derives one canonical connectivity model from source elements.
3. Layout consumes a typed render plan from that model.
4. Schematic and KiCad writers only serialize already-resolved geometry and connectivity.

Avoid a rewrite. The current baseline is green, so work should be incremental and protected by regression tests.

Baseline command:

```bash
.venv/bin/pytest -q
```

Baseline observed before this plan was executed on 2026-06-27:

```text
440 passed
```

Status after the first implementation slice on 2026-06-27:

```text
450 passed
```

Status after the hierarchy/cycle hardening slice on 2026-06-27:

```text
456 passed
```

Status after the nested-branch bridge slice on 2026-06-27:

```text
458 passed
```

Status after the nested hierarchy compile fixture on 2026-06-27:

```text
459 passed
```

Completed first-slice work:

- Added `src/circuitweaver/compiler/connectivity.py` with typed logical-net and sheet-connection planning.
- Kept `CompileEngine._process_connectivity()` as a compatibility wrapper over the new planner.
- Moved the main compiler layout path to typed `SheetConnection` plans; legacy dictionaries are normalized only at the layout boundary for older callers/tests.
- Fixed one-port power/ground nets so they render as global-label plans instead of disappearing.
- Fixed KiCad symbol resolution to use `ftype` inference when `symbol_id` is absent.
- Added in-memory validation through `validate_circuit_elements()`.
- Added regression tests for connectivity, KiCad symbol resolution, and in-memory validation.

Completed hierarchy/cycle hardening:

- Non-global nested child-to-parent nets now stop at the lowest common sheet instead of always propagating to `root`.
- Endpoint sheets at the common connection sheet use matching local labels instead of unnecessary hierarchical labels.
- Group parent cycles are reported by validation.
- Compiler sheet mapping and hierarchical parent walking now fall back deterministically instead of hanging on cyclic mappings.
- Direct source-to-layout group hierarchy building also falls back deterministically on cyclic parent mappings.

Completed nested-branch bridge hardening:

- Nets crossing between two nested branches now create generated bridge connections on intermediate sheets.
- Bridge connections reuse the typed `SheetConnection` plan and target generated hierarchical pin IDs registered as ELK ports.
- `SourceToLayoutTransform` can create a hierarchical label from a generated sheet pin without adding a separate renderer concept.
- A deterministic compile regression now verifies nested branch-to-branch nets in generated KiCad sheet files.
- Generated wire edges now carry source trace IDs as layout metadata, so layout-to-schematic no longer has to recover them by splitting edge IDs.

Completed typed-test cleanup:

- Layout and transform tests now use `SheetConnection` fixtures for normal connectivity behavior.
- Legacy connectivity dictionaries remain covered only by explicit compatibility tests and `_process_connectivity()` wrapper assertions.
- `SourceToLayoutTransform` still accepts legacy connectivity dictionaries for external callers, but emits a deprecation warning.

Completed dead-code cleanup:

- Removed the unused duplicate `compiler/elk_runner.py`; `AutoRouter` is the active ELK subprocess wrapper.

## Current Architecture Summary

Current compile flow:

1. `CompileEngine.layout()` splits source elements by type.
2. `_map_elements()` assigns components, groups, and ports to sheets.
3. `build_connection_plan()` computes typed per-sheet render plans and generated hierarchy elements.
4. `SourceToLayoutTransform` builds ELK nodes from `SheetConnection.render_kind`.
5. `AutoRouter` runs ELK through Node.js.
6. `LayoutToSchematicTransform` converts routed ELK nodes/edges into `schematic_*` elements.
7. `SchematicToSExprTransform` writes KiCad S-expressions.

Important files:

- `src/circuitweaver/compiler/engine.py`
- `src/circuitweaver/transform/source_to_layout.py`
- `src/circuitweaver/transform/layout_to_schematic.py`
- `src/circuitweaver/transform/schematic_to_s_expr.py`
- `src/circuitweaver/compiler/global_nets.py`
- `src/circuitweaver/validator/engine.py`

## Original Key Findings

These findings describe the pre-refactor state. The first implementation slice fixes findings 1, 2, and 4 while leaving deeper API and documentation cleanup for follow-up work.

### 1. Single-port named/global nets can disappear

The included LED example compiles, but generated KiCad output can omit VCC/GND labels entirely.

Reproduce:

```bash
.venv/bin/circuitweaver compile examples/simple_led/circuit.json -o /tmp/circuitweaver-plan-demo -n demo
rg -n "label|global_label|hierarchical_label|VCC|GND" /tmp/circuitweaver-plan-demo/demo.kicad_sch
```

Expected:

- `VCC` and `GND` should appear as labels, global labels, or power symbols.

Current observed issue:

- No matching label output is generated for those single-port named nets.

Likely cause:

- `CompileEngine._process_connectivity()` computes `is_global_net` and label names.
- `SourceToLayoutTransform._add_connectivity()` ignores `is_global_net` when deciding wire versus label.
- A one-port connection goes to `_add_wires()`, which emits no edge because there is no target port.

Relevant locations:

- `src/circuitweaver/compiler/engine.py`, `_process_connectivity`
- `src/circuitweaver/transform/source_to_layout.py`, `_add_connectivity`, `_add_wires`, `_add_labels`

### 2. Symbol inference is not consistently applied to KiCad output

`ftype` inference is used by layout through `get_effective_symbol_id()`, but KiCad S-expression generation often reads only `SourceComponent.symbol_id`.

Reproduce:

```bash
.venv/bin/circuitweaver compile examples/simple_led/circuit.json -o /tmp/circuitweaver-plan-demo -n demo
rg -n "QuestionBlock|lib_id|Device:R|Device:LED" /tmp/circuitweaver-plan-demo/demo.kicad_sch
```

Current observed issue:

- The compiler can warn about `Device:QuestionBlock`.
- Components can be emitted with an embedded placeholder name instead of the inferred `Device:R` or `Device:LED`.

Likely cause:

- `SchematicToSExprTransform._resolve_lib_id()` uses `comp.symbol_name`, then `source.symbol_id`, then `Device:QuestionBlock`.
- It does not use `get_effective_symbol_id(source)`.

Relevant location:

- `src/circuitweaver/transform/schematic_to_s_expr.py`, `_resolve_lib_id`

### 3. Connectivity policy is split across stages

Connection decisions are currently distributed:

- Sheet and hierarchy facts in `CompileEngine._map_elements()`.
- Net grouping and global/hierarchical facts in `CompileEngine._process_connectivity()`.
- Wire versus label decision in `SourceToLayoutTransform._add_connectivity()`.
- Label placement in `LayoutToSchematicTransform._process_edges()`.
- KiCad label kind in `SchematicToSExprTransform._transform_label()`.

This makes bugs hard to localize and extension hard to reason about.

### 4. Validation is partly file-centric

`CompileEngine.validate_project()` performs real validation only when `project.source_path` exists. In-memory projects can bypass the validation rules.

Relevant location:

- `src/circuitweaver/compiler/engine.py`, `validate_project`

### 5. Documentation and requirements are stale in places

The docs do not consistently describe the current architecture or target direction.

Observed issues:

- `PLAN.md` describes an older clean-slate logic-only direction.
- `docs/requirements/target-architecture.md` marks several target items as implemented.
- `docs/requirements/implementation-notes-and-gaps.md` still lists some related items as conflicts or gaps.
- `docs/circuit-json-spec.md` is mostly logic-first, but still includes some generated `schematic_*` concepts that can confuse LLM authors.

This matters because future agents may follow stale docs and preserve accidental behavior instead of the intended architecture.

## Design Target

Introduce a small, pure connectivity layer.

Suggested new module:

```text
src/circuitweaver/compiler/connectivity.py
```

Suggested responsibilities:

1. Build a canonical logical netlist from source elements.
2. Assign ports/nets to sheets using existing sheet mapping.
3. Decide how each net should be represented on each sheet.
4. Return typed data structures instead of loose dictionaries.

Keep the model intentionally small.

Suggested dataclasses:

```python
@dataclass(frozen=True)
class NetEndpoint:
    port_id: str
    component_id: str
    sheet_id: str
    group_id: str | None


@dataclass(frozen=True)
class LogicalNet:
    net_id: str
    display_name: str
    source_trace_ids: tuple[str, ...]
    source_net_id: str | None
    endpoints: tuple[NetEndpoint, ...]
    is_global: bool


@dataclass(frozen=True)
class SheetConnection:
    net_id: str
    trace_ids: tuple[str, ...]
    sheet_id: str
    endpoint_port_ids: tuple[str, ...]
    render_kind: Literal[
        "wire",
        "local_label",
        "global_label",
        "hierarchical_label",
    ]
    label_text: str
    hierarchical_pin_id: str | None = None
```

Optional:

```python
@dataclass(frozen=True)
class HierarchicalPinPlan:
    pin_id: str
    parent_sheet_id: str
    child_sheet_id: str
    sheet_box_id: str
    net_id: str
    text: str
```

The exact names can change. The invariant is more important than the shape:

- All source traces that refer to the same `source_net` must become one `LogicalNet`.
- A source trace without `connected_source_net_ids` may use `source_trace_id` as its logical net ID.
- A one-port named global net must produce a label plan, not disappear.
- Non-global inter-sheet nets must produce hierarchical pins and labels.
- Global inter-sheet nets must not create hierarchical pins.

## Phased Implementation Plan

### Phase 1: Add regression tests

Status: completed in the first implementation slice.

Add tests before changing behavior.

Suggested tests:

- `tests/unit/test_connectivity.py`
- `tests/unit/test_kicad_writer.py`
- `tests/test_layout_and_compilation_requirements.py` only if requirement traceability is needed.

Required coverage:

1. A single-port source trace connected to `SourceNet(is_power=True)` generates a per-sheet global-label render plan.
2. A single-port source trace connected to `SourceNet(is_ground=True)` generates a per-sheet global-label render plan.
3. Two separate source traces using the same `connected_source_net_ids=["N1"]` merge into one logical net.
4. A two-port direct trace without a source net remains wire-rendered when both endpoints are in the same sheet/group context.
5. A non-global net across two child sheets creates hierarchical pin plans and child hierarchical labels.
6. A global net across two child sheets creates global labels and no hierarchical pins.
7. Compiling `examples/simple_led/circuit.json` produces KiCad text containing `VCC` and `GND`.
8. `SchematicToSExprTransform._resolve_lib_id()` uses `ftype` inference when `symbol_id` is absent.

Acceptance:

```bash
.venv/bin/pytest -q
```

The first commit may include failing tests if using test-first workflow, but do not leave the branch failing after implementation.

### Phase 2: Extract canonical connectivity builder

Status: completed in the first implementation slice.

Create `compiler/connectivity.py`.

Initial function shape:

```python
def build_logical_nets(
    *,
    traces: list[SourceTrace],
    ports: list[SourcePort],
    nets: list[SourceNet],
    element_to_sheet: dict[str, str],
    element_to_group: dict[str, str],
    global_resolver: GlobalNetResolver,
) -> list[LogicalNet]:
    ...
```

Rules:

- Ignore invalid source references only if validation has already reported them. Prefer deterministic behavior and no crashes.
- Use the first `connected_source_net_ids` entry as the named-net owner, preserving current behavior.
- If no source net is present, use `source_trace_id` as the logical net ID and display name.
- Merge traces by logical net ID.
- Store endpoint order deterministically.

Acceptance:

- New `test_connectivity.py` tests pass.
- No existing tests fail.

### Phase 3: Build a typed render plan

Status: mostly completed. `SheetConnection` and explicit `render_kind` values drive the main layout path. A compatibility adapter still accepts legacy dictionaries at the layout boundary. Nested child-to-parent nets now use the lowest common sheet as the connection point, and nested branch-to-branch nets create intermediate bridge label plans.

The current implementation exposes this pure function:

```python
def build_connection_plan(
    *,
    traces: list[SourceTrace],
    ports: list[SourcePort],
    nets: list[SourceNet],
    element_to_sheet: dict[str, str],
    element_to_group: dict[str, str],
    groups: list[SourceGroup],
    elements: list[CircuitElement],
    global_resolver: GlobalNetResolver,
) -> tuple[list[CircuitElement], dict[str, list[SheetConnection]]]:
    ...
```

The plan should include:

- Per-sheet `SheetConnection` records.
- Generated hierarchical pins and matching net labels as schematic elements.
- Bridge `SheetConnection` records for intermediate nested sheets.

Keep policy simple:

- Same sheet, same local group, two or more endpoints: `wire`.
- Same sheet, cross local group: `local_label`.
- Any global net: `global_label` on each involved endpoint sheet, even with one endpoint.
- Non-global inter-sheet: child sheets get `hierarchical_label`; parent/root sheet gets hierarchical pins and matching local labels.
- One-port named non-global net should get a `local_label`.
- One-port unnamed net can remain a warning/no-op because it is electrically floating.

Acceptance:

- The render policy is unit-tested without ELK, KiCad, or file I/O.
- Normal render decisions no longer depend on raw `dict[str, Any]`; legacy dictionaries are only compatibility input at the layout boundary and compatibility output from `_process_connectivity()`.

### Phase 4: Migrate layout to consume the render plan

Status: mostly completed. `SourceToLayoutTransform` consumes typed `SheetConnection` objects internally and honors `render_kind`; legacy `dict[str, Any]` input is converted at the transform boundary.

Change `CompileEngine.layout()` to:

1. Build sheet maps.
2. Build logical nets.
3. Build the connection render plan.
4. Convert plan-generated hierarchical pins/root labels into schematic elements.
5. Pass typed per-sheet connection records to `SourceToLayoutTransform`.

Change `SourceToLayoutTransform`:

- Stop deciding high-level connection policy from source/group data.
- Only create ELK edges/nodes from `SheetConnection.render_kind`.
- Replace loose `sheet_connectivity: dict[str, list[dict[str, Any]]]` with a typed structure or with a compatibility adapter that is removed later.

Migration strategy:

- Keep `_process_connectivity()` temporarily as a wrapper over the new module if many tests call it.
- Mark it as compatibility-only in a comment.
- Move tests away from internals over time.

Acceptance:

- LED example produces VCC/GND labels.
- Existing hierarchy tests still pass.
- No KiCad writer code needs to know how the connection plan was made.

### Phase 5: Fix symbol resolution consistently

Status: completed in the first implementation slice.

Update `SchematicToSExprTransform._resolve_lib_id()` to use `get_effective_symbol_id(source)`.

Suggested behavior:

1. `SchematicComponent.symbol_name` wins if it is a full KiCad library ID.
2. `get_effective_symbol_id(source)` comes next.
3. Fallback symbol is used only when neither explicit nor inferred symbol exists.

Also update component value fallback if needed:

- Prefer `SourceComponent.display_value`.
- Then `get_effective_symbol_id(source)`.
- Then empty string.

Acceptance:

- `examples/simple_led/circuit.json` emits inferred resistor/LED symbols when KiCad libraries are available.
- Tests do not rely on local KiCad libraries unless injected/mocked.

### Phase 6: Make validation in-memory capable

Status: completed in the first implementation slice.

Extract validation of parsed elements from `validate_circuit_file()`:

```python
def validate_circuit_elements(
    elements: list[CircuitElement],
    *,
    profile: str = "source",
) -> ValidationResult:
    ...
```

Then use it in:

- `validate_circuit_file()`
- `CompileEngine.validate_project()`
- CLI/MCP compile paths where appropriate

Acceptance:

- `CompileEngine.validate_project(CircuitProject(elements=[...]))` actually runs validation.
- File validation behavior remains unchanged.

### Phase 7: Cleanup and documentation

After the connectivity path is stable:

- Reconcile `PLAN.md`, `docs/requirements/target-architecture.md`, and `docs/requirements/implementation-notes-and-gaps.md` so they no longer contradict each other.
- Decide whether `PLAN.md` should be archived, replaced, or renamed as historical context.
- Update `docs/circuit-json-spec.md` to state clearly that user-authored JSON should normally be `source_*` only, while generated schematic JSON is internal/debug output.
- Move generated/internal `schematic_*` details into a separate advanced/internal reference if they still need to be documented.
- Update `README.md` and `docs/mcp-workflow.md` to point LLM users toward the source-only authoring workflow.
- Add a short architecture overview that names the intended boundaries: source model, connectivity model, render plan, layout graph, schematic model, KiCad writer.
- Remove or update requirement status labels that became stale after the connectivity refactor.

Acceptance:

- Requirements docs no longer claim conflicting states for the same behavior.
- Public CLI/MCP workflows remain stable.
- A new contributor or LLM can identify the correct source-only authoring workflow without reading implementation code.

## Guardrails

- Do not start with a full rewrite.
- Do not change public JSON fields unless strictly necessary.
- Do not require KiCad installation for ordinary unit tests.
- Keep ELK-dependent behavior behind existing router injection/mocking patterns.
- Use typed dataclasses for internal plans. Avoid new untyped dictionaries for connectivity.
- Keep source models immutable.
- Preserve deterministic ordering in generated plans and tests.

## Suggested Next Work Item

Phase 7 documentation cleanup, the typed compiler-to-layout handoff, nested hierarchy hardening, typed test cleanup, and legacy adapter deprecation are now started. Continue by removing deprecated connectivity dictionary support once external callers have had a migration window.

Near-term technical cleanup:

- Keep exactly one focused test for deprecated `SourceToLayoutTransform` dictionary normalization until the adapter is removed.
- Remove the adapter in a future breaking cleanup after callers migrate to `SheetConnection`.
- Consider a small public/internal API note that `SheetConnection.endpoint_port_ids` may contain generated hierarchical pin IDs for bridge labels.

## Historical First Work Item

Implement Phase 1 and Phase 2 only:

1. Add `tests/unit/test_connectivity.py`.
2. Add `src/circuitweaver/compiler/connectivity.py`.
3. Prove the canonical netlist merges traces by source net and represents one-port global nets.
4. Keep existing compile behavior untouched until tests for the new pure layer are passing.

This creates a safe foundation for fixing the actual schematic output in the next PR.
