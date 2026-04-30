# Data Model Requirements

## Circuit Element Union

- [implemented] `DM-001` Circuit JSON files shall be represented as a list of discriminated union elements keyed by the `type` field.
- [implemented] `DM-002` Supported source element types shall be `source_component`, `source_port`, `source_net`, `source_trace`, `source_group`, and `source_project_config`.
- [implemented] `DM-003` Supported schematic element types shall be `schematic_component`, `schematic_port`, `schematic_trace`, `schematic_box`, `schematic_net_label`, `schematic_hierarchical_pin`, `schematic_hierarchical_label`, `schematic_text`, and `schematic_no_connect`.
- [implemented] `DM-004` `get_element_id` shall return the concrete ID field for any supported circuit element.
- [implemented] `DM-005` `get_element_type` shall return the element's `type` string.

## Source Elements

- [implemented] `DM-010` `SourceComponent` shall require `source_component_id` and `name`.
- [implemented] `DM-011` `SourceComponent` shall support optional KiCad mapping via `symbol_id`.
- [implemented] `DM-012` `SourceComponent` shall support optional subtype inference via `ftype`.
- [implemented] `DM-013` `SourceComponent` shall support optional value fields including `resistance`, `capacitance`, `inductance`, `frequency`, `current_rating_amps`, `color`, and `display_value`.
- [implemented] `DM-014` `SourceComponent` shall support optional BOM/PCB fields `footprint`, `manufacturer_part_number`, and `supplier_part_numbers`.
- [implemented] `DM-015` `SourceComponent` shall support optional hierarchy fields `subcircuit_id` and `source_group_id`.
- [implemented] `DM-016` `SourcePort` shall require `source_port_id`, `source_component_id`, and `name`.
- [implemented] `DM-017` `SourcePort` shall support optional `pin_number`, `port_hints`, `is_power`, `is_ground`, `must_be_connected`, `do_not_connect`, and `subcircuit_id`.
- [implemented] `DM-018` `SourceNet` shall require `source_net_id` and `name`.
- [implemented] `DM-019` `SourceNet` shall support optional `is_power`, `is_ground`, `is_digital_signal`, `is_analog_signal`, `trace_width`, and `subcircuit_id`.
- [implemented] `DM-026` `SourceNet` shall support an explicit global-net flag or equivalent project-level global-net declaration used for cross-sheet connectivity decisions.
- [implemented] `DM-027` Circuit JSON shall support project-level global-net configuration, including custom global net names and whether KiCad power-symbol catalog defaults are enabled.
- [implemented] `DM-028` `source_project_config` shall support `global_net_names` and `use_kicad_power_symbols_as_global_nets`.
- [implemented] `DM-020` `SourceTrace` shall require `source_trace_id` and `connected_source_port_ids`.
- [implemented] `DM-021` `SourceTrace.connected_source_net_ids` shall default to an empty list.
- [implemented] `DM-022` `SourceTrace` shall support optional `max_length`, `display_name`, and `subcircuit_id`.
- [implemented] `DM-023` `SourceGroup` shall require `source_group_id`.
- [implemented] `DM-024` `SourceGroup` shall support optional `name`, `subcircuit_id`, `parent_subcircuit_id`, `parent_source_group_id`, and `is_subcircuit`.
- [implemented] `DM-025` Source models shall be frozen Pydantic models.

## Schematic Elements

- [implemented] `DM-030` Every schematic element shall include a required `sheet_id`.
- [implemented] `DM-031` `SchematicComponent` shall require `schematic_component_id`, `source_component_id`, and `center`; `rotation` shall default to `0`.
- [implemented] `DM-032` `SchematicPort` shall require `schematic_port_id`, `source_port_id`, and `center`.
- [implemented] `DM-033` `SchematicTraceEdge` shall represent a single segment with an aliased JSON field `from` mapped to Python attribute `from_`, and a `to` point.
- [implemented] `DM-034` `SchematicTrace` shall require `schematic_trace_id` and `edges`; `source_trace_id` shall be optional.
- [implemented] `DM-035` `SchematicBox` shall require `schematic_box_id`, `x`, `y`, `width`, and `height`.
- [implemented] `DM-036` `SchematicBox.is_hierarchical_sheet` shall default to `False`.
- [implemented] `DM-037` `SchematicBox` shall support optional `child_sheet_id` and `name`.
- [implemented] `DM-038` `SchematicBox.name_offset` shall default to `{x: 0, y: -10}`.
- [implemented] `DM-039` `SchematicBox.file_offset` shall default to `{x: 0, y: 10}`.
- [implemented] `DM-040` `SchematicNetLabel` shall require `schematic_net_label_id`, `source_net_id`, `center`, and `text`.
- [implemented] `DM-041` `SchematicNetLabel.anchor_side` shall default to `left` and shall be one of `left`, `right`, `top`, or `bottom`.
- [implemented] `DM-047` `SchematicNetLabel.is_global` shall default to `false` and shall cause KiCad output to emit a `global_label` instead of a local `label`.
- [implemented] `DM-042` `SchematicHierarchicalPin` shall require `schematic_hierarchical_pin_id`, `source_net_id`, `schematic_box_id`, `center`, and `text`.
- [implemented] `DM-043` `SchematicHierarchicalLabel` shall require `schematic_hierarchical_label_id`, `source_net_id`, `center`, and `text`.
- [implemented] `DM-044` `SchematicHierarchicalLabel.anchor_side` shall default to `left` and shall be one of `left`, `right`, `top`, or `bottom`.
- [implemented] `DM-045` `SchematicText` shall require `schematic_text_id`, `position`, and `text`; `rotation` shall default to `0`.
- [implemented] `DM-046` `SchematicNoConnect` shall require `schematic_no_connect_id` and may reference a schematic/source port by `schematic_port_id` and/or include a `position`.

## Layout Graph

- [implemented] `DM-050` Layout graph data shall be represented by `LayoutNode`.
- [implemented] `DM-051` `LayoutNode` shall contain `id`, coordinates, dimensions, labels, ports, child nodes, edges, and layout options.
- [implemented] `DM-052` `LayoutNode.find_node` shall recursively return the node with a matching ID or `None`.
- [implemented] `DM-053` `LayoutEdge` shall contain `id`, `sources`, `targets`, optional `sections`, and optional `layoutOptions`.
- [implemented] `DM-054` `LayoutEdgeSection` shall contain `id`, `startPoint`, `endPoint`, and optional `bendPoints`.

## S-Expression Model

- [implemented] `DM-060` `SExpr` shall represent a named S-expression with ordered arguments.
- [implemented] `DM-061` `RawString` shall serialize without quoting or escaping.
- [implemented] `DM-062` `SExpr.find` shall return the first direct child expression with the requested name.
- [implemented] `DM-063` `SExpr.find_all` shall return all direct child expressions with the requested name.
- [implemented] `DM-064` `SExpr.get_value` shall return the first argument of the first matching direct child or a default.
