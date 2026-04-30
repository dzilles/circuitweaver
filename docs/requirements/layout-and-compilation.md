# Layout and Compilation Requirements

## Symbol Inference

- [implemented] `LAY-001` `get_effective_symbol_id` shall return `SourceComponent.symbol_id` when present.
- [implemented] `LAY-002` If `symbol_id` is absent, `get_effective_symbol_id` shall infer symbols from `ftype` for `simple_resistor`, `simple_capacitor`, `simple_led`, `simple_diode`, and `simple_transistor`.
- [implemented] `LAY-003` Unknown or absent `ftype` values shall not infer a symbol.

## Source To Layout Transform

- [implemented] `LAY-010` `SourceToLayoutTransform.transform` shall create a root `LayoutNode` whose ID is the requested sheet ID.
- [implemented] `LAY-011` The root layout node shall use ELK algorithm `layered`.
- [implemented] `LAY-012` The root layout node shall include ELK padding `[top=100,left=100,bottom=100,right=100]`.
- [implemented] `LAY-013` The root layout node shall include node spacing `50`.
- [implemented] `LAY-014` `SourceGroup` elements shall become layout box nodes with ID `box_<source_group_id>`.
- [implemented] `LAY-015` Group box nodes shall have minimum width `250` and minimum height `100`.
- [implemented] `LAY-016` Group box nodes shall use fixed port constraints.
- [implemented] `LAY-017` A `SourceGroup` with `is_subcircuit=true` shall create hierarchical ports for matching `SchematicHierarchicalPin` elements.
- [implemented] `LAY-018` Hierarchical ports shall alternate WEST and EAST sides.
- [implemented] `LAY-019` `SourceComponent` elements shall become layout nodes with ID equal to `source_component_id`.
- [implemented] `LAY-020` Component layout nodes shall use fixed port constraints.
- [implemented] `LAY-021` If symbol info is available, component layout node width and height shall come from the symbol bounding box.
- [implemented] `LAY-022` If symbol info is unavailable, component layout node width and height shall default to `40`.
- [implemented] `LAY-023` If symbol info is available, component ports shall be created from symbol pins and registered to matching `SourcePort` by `pin_number`.
- [implemented] `LAY-024` If symbol info is unavailable, component ports shall be created from `SourcePort` elements in order, spaced by `20`, and placed on the WEST side.
- [implemented] `LAY-025` Direct intra-group or same-context connections shall become ELK layout edges.
- [implemented] `LAY-026` Cross-group or inter-sheet connections shall become local label nodes and label edges rather than direct wire edges.
- [implemented] `LAY-027` No-connect markers shall become zero-size layout nodes connected by `e_nc_*` edges when they can be matched to a registered port.

## Compile Engine Layout Flow

- [implemented] `CMP-001` `CompileEngine.compile` shall create the output directory if needed.
- [conflict] `CMP-002` `CompileEngine.compile` shall run auto-layout only when no input element type starts with `schematic_`. This current all-or-nothing heuristic conflicts with planned stage-aware compilation requirement `ARCH-004`.
- [conflict] `CMP-003` If any input element type starts with `schematic_`, `CompileEngine.compile` shall skip auto-layout. This current all-or-nothing heuristic conflicts with planned stage-aware compilation requirement `ARCH-004`.
- [implemented] `CMP-004` If no sheet IDs are present after layout selection, the compiler shall use a root sheet ID of `root`.
- [implemented] `CMP-005` The compiler shall write one `.kicad_sch` file per discovered sheet ID.
- [implemented] `CMP-006` The root sheet shall be written as `<project_name>.kicad_sch`.
- [implemented] `CMP-007` Non-root sheets shall be written as `<sheet_id>.kicad_sch`.
- [implemented] `CMP-008` The compiler shall always write `<project_name>.kicad_pro`.
- [partial] `CMP-009` `CompileEngine.compile` shall return the path to the root schematic file. The returned value is implemented for normal output, but the current internal flow can leave the root path unset in edge cases described by `GAP-022`.

## Sheet Mapping And Connectivity

- [implemented] `CMP-020` Components shall be assigned to sheets based on their `source_group_id` or `subcircuit_id`.
- [implemented] `CMP-021` A subcircuit group with `is_subcircuit=true` and `subcircuit_id` shall own a sheet with ID equal to `subcircuit_id`.
- [implemented] `CMP-022` Groups shall be assigned to the sheet owned by their parent group.
- [implemented] `CMP-023` Component ports shall be assigned to the same sheet as their parent component.
- [implemented] `CMP-024` Source traces and source nets shall not be included directly in per-sheet layout element lists.
- [implemented] `CMP-047` A subcircuit group with `is_subcircuit=true` and no `subcircuit_id` shall own a sheet whose ID is the group's `source_group_id`.
- [implemented] `CMP-048` A component or source port whose `subcircuit_id` matches a subcircuit group's `source_group_id` shall be assigned to that group's owned sheet when the group omits `subcircuit_id`.
- [implemented] `CMP-025` Connectivity preprocessing shall use the first connected source net ID as the net ID when a trace references nets; otherwise it shall use the source trace ID.
- [implemented] `CMP-026` Net labels generated by connectivity preprocessing shall use `NET_<raw_name>`.
- [implemented] `CMP-027` Hierarchical pin labels generated by connectivity preprocessing shall use `HPIN_<raw_name>`.
- [implemented] `CMP-028` Global-net handling shall be resolved through explicit source net metadata, project global-net configuration, and optional KiCad power-symbol defaults rather than generated-name substring matching.
- [implemented] `CMP-029` Non-global traces spanning multiple sheets shall generate `SchematicHierarchicalPin` and `SchematicHierarchicalLabel` elements as needed.
- [implemented] `CMP-049` Circuit JSON shall provide an explicit way to mark a `SourceNet` as global; this global-net declaration shall be the authoritative project-specific definition.
- [implemented] `CMP-050` Global-net detection shall not rely on substring matching such as `GND`, `5V`, or `3V3`.
- [implemented] `CMP-051` KiCad power-symbol names extracted from the configured KiCad `power.kicad_sym` library may be used as a default global-net catalog when a project does not explicitly override global-net detection.
- [partial] `CMP-052` The default KiCad power-symbol global-net catalog shall be treated as advisory and environment-dependent. Missing KiCad symbol libraries are logged, but validation does not yet report this condition.
- [implemented] `CMP-053` A project shall be able to add custom global net names that are not present in KiCad's power symbol library.
- [implemented] `CMP-054` A project shall be able to disable or override the default KiCad power-symbol global-net catalog for deterministic compilation.
- [partial] `CMP-055` Global inter-sheet nets shall be represented in each affected child sheet with KiCad global labels or power symbols, and shall not require parent-sheet hierarchical pins. This is implemented when the affected source ports can be mapped to schematic ports.
- [implemented] `CMP-056` Non-global inter-sheet nets shall create hierarchical pins on each affected child sheet box and matching hierarchical labels inside each child sheet.
- [implemented] `CMP-057` The root sheet shall connect matching non-global hierarchical sheet pins by generated net labels with the same text, not by direct wires between sheet pins.
- [implemented] `CMP-058` Root-sheet labels generated for hierarchical sheet pins shall use the same text as the corresponding child-sheet `SchematicHierarchicalLabel`.
- [implemented] `CMP-059` Root-sheet hierarchical-pin labels shall be placed adjacent to the sheet pin endpoint and shall not create direct wire segments between separate sheet boxes.
- [implemented] `CMP-060` Root-sheet hierarchical-pin labels shall be generated for every sheet pin participating in a non-global inter-sheet net, including nets shared by more than two child sheets.

## ELK Auto-Router

- [implemented] `LAY-040` `AutoRouter` initialization shall fail with `RuntimeError` if `node` is not found on `PATH`.
- [implemented] `LAY-041` `AutoRouter` shall default its helper script to `layout_helper.js` in the compiler package directory.
- [implemented] `LAY-042` `AutoRouter.run` shall pass the layout graph JSON to the Node helper on stdin.
- [implemented] `LAY-043` `AutoRouter.run` shall parse stdout as JSON and return it as a dictionary.
- [implemented] `LAY-044` A non-zero Node process exit shall raise `RuntimeError` containing stderr or stdout.
- [implemented] `LAY-045` Invalid JSON from the Node helper shall raise `RuntimeError`.

## Layout To Schematic Transform

- [implemented] `LAY-050` `snap_to_grid` shall round values to the nearest grid size, default `10.0`.
- [implemented] `LAY-051` `LayoutToSchematicTransform` shall process layout nodes recursively.
- [implemented] `LAY-052` Source component nodes shall become `SchematicComponent` elements with ID `sch_<layout_node_id>`.
- [implemented] `LAY-053` Generated schematic components shall use `sheet_id` from the current transform.
- [implemented] `LAY-054` Generated schematic component centers shall be snapped to the configured grid.
- [implemented] `LAY-055` Generated schematic ports shall have ID `port_<source_port_id>`.
- [implemented] `LAY-056` Generated schematic ports shall be positioned from symbol pin grid offsets when symbol info is available.
- [implemented] `LAY-064` Source ports shall map to symbol pins by matching `pin_number` first and, when `pin_number` is absent, by matching the source port `name` to the KiCad symbol pin name.
- [implemented] `LAY-057` Source group nodes shall become `SchematicBox` elements.
- [implemented] `LAY-058` A group with `is_subcircuit=true` shall generate a hierarchical sheet box with `child_sheet_id` equal to the group's `subcircuit_id`.
- [implemented] `LAY-063` If a group with `is_subcircuit=true` omits `subcircuit_id`, its generated hierarchical sheet box shall use the group's `source_group_id` as `child_sheet_id`.
- [implemented] `LAY-059` Edge sections shall become `SchematicTrace` elements containing non-zero-length `SchematicTraceEdge` segments.
- [implemented] `LAY-060` Label edges shall position `SchematicNetLabel` or `SchematicHierarchicalLabel` elements at the routed edge endpoint.
- [implemented] `LAY-061` Label anchor side shall be inferred from the final edge segment direction.
- [implemented] `LAY-062` Edges beginning with `e_nc_` shall not generate schematic traces.

## Schematic To KiCad S-Expression

- [implemented] `CMP-030` KiCad schematic output shall use a root S-expression named `kicad_sch`.
- [implemented] `CMP-031` KiCad schematic output shall include version `20260306`, generator `eeschema`, generator version `10.0`, a UUID, and paper `A4`.
- [implemented] `CMP-032` Grid units shall convert to millimeters using `1 grid = 0.127 mm`.
- [implemented] `CMP-033` Millimeter values shall be formatted with four decimal places.
- [partial] `CMP-034` Symbol library definitions shall be embedded under `lib_symbols` when component symbols can be loaded. Missing or invalid local KiCad libraries are logged and compilation continues as described by `GAP-031` and `GAP-032`.
- [implemented] `CMP-035` Hierarchical sheet boxes shall become KiCad `sheet` expressions with Sheetname and Sheetfile properties.
- [implemented] `CMP-036` Schematic components shall become KiCad `symbol` expressions.
- [implemented] `CMP-037` Component reference text shall come from `SourceComponent.name` when available, otherwise `U?`.
- [implemented] `CMP-038` Component value text shall come from `SourceComponent.display_value` when present; otherwise from `SourceComponent.symbol_id`; otherwise an empty string.
- [implemented] `CMP-039` Component footprint property shall be emitted only when `SourceComponent.footprint` is present.
- [implemented] `CMP-040` Schematic traces shall become KiCad `wire` expressions.
- [implemented] `CMP-041` Junctions shall be emitted at rounded points used by at least three wires, ports, labels, or hierarchical pins.
- [implemented] `CMP-042` Schematic net labels shall become KiCad `label` expressions.
- [implemented] `CMP-043` Schematic hierarchical labels shall become KiCad `hierarchical_label` expressions.
- [implemented] `CMP-061` Global schematic net labels shall become KiCad `global_label` expressions.
- [implemented] `CMP-044` Schematic no-connects shall become KiCad `no_connect` expressions only when `position` is present.
- [implemented] `CMP-045` Non-hierarchical schematic boxes shall become KiCad `rectangle` expressions.
- [implemented] `CMP-046` Project metadata shall be JSON with `meta.filename`, `meta.version=3`, empty `boards`, and a `sheets` list starting with `["Root", "<project_name>.kicad_sch"]`.
